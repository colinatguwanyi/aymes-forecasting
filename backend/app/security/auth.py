"""Auth module: Easy Auth (prod) + dev bypass, RBAC dependencies."""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

# Role names (must match DB seed)
ROLE_ADMIN = "Admin"
ROLE_PLANNER = "Planner"
ROLE_VIEWER = "Viewer"
ROLE_OPERATOR = "Operator"

VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_PLANNER, ROLE_VIEWER, ROLE_OPERATOR})


@dataclass
class Identity:
    """Parsed identity from headers (before DB lookup)."""
    entra_oid: str | None
    email: str
    display_name: str | None
    runtime_roles: list[str] | None  # Dev-only: roles from X-Dev-User (not persisted)


def _is_dev_mode() -> bool:
    return settings.environment.lower() in ("dev", "local")


def parse_easy_auth_headers(request: Request) -> Identity | None:
    """Parse Azure Container Apps Easy Auth headers.
    X-MS-CLIENT-PRINCIPAL (base64 JSON) preferred; fallback to NAME/ID headers.
    """
    principal_b64 = request.headers.get("X-MS-CLIENT-PRINCIPAL")
    if principal_b64:
        try:
            raw = base64.b64decode(principal_b64)
            data = json.loads(raw)
            user_id = data.get("userId") or data.get("oid") or data.get("user_id")
            user_details = data.get("userDetails") or data.get("preferred_username") or ""
            if isinstance(user_details, dict):
                email = user_details.get("email") or user_details.get("upn") or str(user_details)
            else:
                email = str(user_details) if user_details else ""
            if not email and not user_id:
                return None
            if not email and user_id:
                email = f"{user_id}@entra.local"
            return Identity(
                entra_oid=str(user_id) if user_id else None,
                email=email.strip() or "unknown@entra.local",
                display_name=data.get("name") or data.get("userDetails") if isinstance(data.get("userDetails"), str) else None,
                runtime_roles=None,
            )
        except Exception as e:
            logger.warning("Failed to parse X-MS-CLIENT-PRINCIPAL: %s", e)
            return None

    name = request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "").strip()
    oid = request.headers.get("X-MS-CLIENT-PRINCIPAL-ID", "").strip()
    if not name and not oid:
        return None
    email = name if "@" in name else (f"{oid}@entra.local" if oid else "unknown@entra.local")
    return Identity(
        entra_oid=oid or None,
        email=email,
        display_name=name or None,
        runtime_roles=None,
    )


def parse_dev_headers(request: Request) -> Identity | None:
    """Parse X-Dev-User header (dev/local only). JSON or plain email.
    Option B: runtime_roles from header used for auth only, not persisted.
    """
    if not _is_dev_mode():
        return None
    raw = request.headers.get("X-Dev-User", "").strip()
    if not raw:
        email = settings.dev_default_user_email
        if not email:
            return None
        return Identity(
            entra_oid=None,
            email=email.strip(),
            display_name=None,
            runtime_roles=None,
        )
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            email = (data.get("email") or data.get("emailAddress") or "").strip()
            if not email:
                return None
            roles_raw = data.get("roles")
            runtime_roles: list[str] | None = None
            if isinstance(roles_raw, list):
                runtime_roles = [str(r) for r in roles_raw if str(r) in VALID_ROLES]
            return Identity(
                entra_oid=None,
                email=email,
                display_name=(data.get("name") or data.get("display_name") or "").strip() or None,
                runtime_roles=runtime_roles if runtime_roles else None,
            )
        except json.JSONDecodeError:
            pass
    if "@" in raw:
        return Identity(entra_oid=None, email=raw, display_name=None, runtime_roles=None)
    return None


@dataclass
class CurrentUserContext:
    """Resolved user + roles for the request."""
    user: User
    roles: list[str]
    auth_mode: str  # "easy_auth" | "dev"


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> CurrentUserContext:
    """Resolve identity, upsert user, load roles. Raises 401 if not authenticated."""
    identity: Identity | None = None
    auth_mode: str = "easy_auth"

    if _is_dev_mode():
        identity = parse_dev_headers(request)
        if identity:
            auth_mode = "dev"
    if not identity:
        identity = parse_easy_auth_headers(request)

    if not identity:
        raise HTTPException(status_code=401, detail="Not authenticated")

    now = datetime.now(timezone.utc)
    user: User | None = None

    if identity.entra_oid:
        user = db.query(User).filter(User.entra_oid == identity.entra_oid).first()
    if not user:
        user = db.query(User).filter(User.email == identity.email).first()

    if not user:
        user = User(
            entra_oid=identity.entra_oid,
            email=identity.email,
            display_name=identity.display_name,
            is_active=True,
        )
        db.add(user)
        db.flush()

    user.last_login_at = now
    user.display_name = identity.display_name or user.display_name
    db.commit()
    db.refresh(user)

    role_names: list[str] = []
    if auth_mode == "dev" and identity.runtime_roles:
        role_names = identity.runtime_roles
    else:
        for r in user.roles:
            role_names.append(r.name)
    if not role_names and auth_mode == "dev":
        role_names = [ROLE_VIEWER]

    return CurrentUserContext(user=user, roles=role_names, auth_mode=auth_mode)


def require_roles(*allowed: str):
    """FastAPI dependency: require user to have at least one of the given roles."""

    def _check(
        ctx: CurrentUserContext = Depends(get_current_user),
    ) -> CurrentUserContext:
        for r in allowed:
            if r in ctx.roles:
                return ctx
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return Depends(_check)


def require_admin(ctx: CurrentUserContext = Depends(get_current_user)) -> CurrentUserContext:
    """Require Admin role."""
    if ROLE_ADMIN not in ctx.roles:
        raise HTTPException(status_code=403, detail="Admin role required")
    return ctx


def require_admin_or_operator(ctx: CurrentUserContext = Depends(get_current_user)) -> CurrentUserContext:
    """Require Admin or Operator."""
    if ROLE_ADMIN in ctx.roles or ROLE_OPERATOR in ctx.roles:
        return ctx
    raise HTTPException(status_code=403, detail="Admin or Operator role required")


def require_admin_or_planner(ctx: CurrentUserContext = Depends(get_current_user)) -> CurrentUserContext:
    """Require Admin or Planner."""
    if ROLE_ADMIN in ctx.roles or ROLE_PLANNER in ctx.roles:
        return ctx
    raise HTTPException(status_code=403, detail="Admin or Planner role required")


def require_any_auth(ctx: CurrentUserContext = Depends(get_current_user)) -> CurrentUserContext:
    """Require any authenticated user (no role check)."""
    return ctx
