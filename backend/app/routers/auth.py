"""Auth API: /me endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.security.auth import CurrentUserContext, get_current_user

router = APIRouter()


@router.get("/me")
def get_me(ctx: CurrentUserContext = Depends(get_current_user)) -> dict:
    """Return current user, roles, and auth mode."""
    return {
        "authenticated": True,
        "auth_mode": ctx.auth_mode,
        "user": {
            "id": str(ctx.user.id),
            "email": ctx.user.email,
            "display_name": ctx.user.display_name,
        },
        "roles": ctx.roles,
    }
