"""Admin API: data management summary, reset preview, controlled test-data reset."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import CurrentUserContext, require_admin
from app.services import data_management as dm

router = APIRouter()


class ResetBody(BaseModel):
    scope: str = Field(default="full_test_data", description="Reset scope id (allowlisted server-side)")
    confirm_text: str = Field(..., min_length=1, description="Scope-specific confirmation phrase")


@router.get("/summary")
def get_data_management_summary(
    db: Session = Depends(get_db),
    _ctx: CurrentUserContext = Depends(require_admin),
) -> dict[str, Any]:
    """Read-only counts, suspicious-data heuristics, and SKU integrity highlights."""
    return dm.summary(db)


@router.get("/reset-preview")
def get_reset_preview(
    scope: str = Query("full_test_data", description="Reset scope id"),
    db: Session = Depends(get_db),
    _ctx: CurrentUserContext = Depends(require_admin),
) -> dict[str, Any]:
    """Dry run: affected tables, row counts, preserved list, warnings. No writes."""
    try:
        return dm.reset_preview(db, scope)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/reset")
def post_reset(
    body: ResetBody,
    db: Session = Depends(get_db),
    ctx: CurrentUserContext = Depends(require_admin),
) -> dict[str, Any]:
    """Destructive scoped reset (non-production environments only). Requires scope-specific confirmation phrase."""
    actor = getattr(ctx.user, "email", None)
    result = dm.execute_reset(db, body.scope, body.confirm_text, actor_email=actor)
    if not result.ok:
        allowed, _ = dm.reset_allowed()
        if not allowed:
            status_code = 403
        elif result.lock_timeout:
            status_code = 503
        elif result.deleted_tables_committed:
            status_code = 500
        elif "Invalid reset scope" in result.message or "Confirmation for scope" in result.message:
            status_code = 400
        elif "rolled back" in result.message.lower() or "stopped partway" in result.message.lower():
            status_code = 500
        else:
            status_code = 400
        raise HTTPException(
            status_code=status_code,
            detail={
                "message": result.message,
                "scope": result.scope,
                "skipped_tables": result.skipped_tables,
                "warnings": result.warnings,
                "deleted_tables_committed": result.deleted_tables_committed,
                "partial_reset": bool(result.deleted_tables_committed),
                "lock_timeout": result.lock_timeout,
            },
        )
    return {
        "ok": True,
        "scope": result.scope,
        "message": result.message,
        "environment": dm.environment_label(),
        "before_counts": result.before_counts,
        "after_counts": result.after_counts,
        "skipped_tables": result.skipped_tables,
        "warnings": result.warnings,
        "deleted_tables_committed": result.deleted_tables_committed,
    }
