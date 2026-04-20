"""RBAC bootstrap: first-admin allowlist for non-dev environments."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Role, User, UserRole


def parse_email_allowlist(raw: str | None) -> frozenset[str]:
    """Parse comma-separated emails: trimmed, lowercased, deduplicated. Never logs content."""
    if not raw or not raw.strip():
        return frozenset()
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip().lower())


def bootstrap_admin_if_allowed(db: Session, user: User, email: str) -> bool:
    """If user has zero DB roles and email is in allowlist, persist Admin role. Idempotent.
    Returns True if Admin was assigned. Does NOT log email or identity.
    """
    allowlist = parse_email_allowlist(settings.rbac_bootstrap_admin_emails)
    if not allowlist:
        return False
    if email.strip().lower() not in allowlist:
        return False
    if user.roles:
        return False
    admin_role = db.query(Role).filter(Role.name == "Admin").first()
    if not admin_role:
        return False
    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == user.id, UserRole.role_id == admin_role.id)
        .first()
    )
    if existing:
        return False
    db.add(UserRole(user_id=user.id, role_id=admin_role.id))
    return True
