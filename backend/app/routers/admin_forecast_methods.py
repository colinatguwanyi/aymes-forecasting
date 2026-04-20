"""Admin forecast methods: descriptor endpoint + acknowledgements."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_admin
from app.services.forecast_methods_descriptor import get_forecast_methods_doc, get_method_version

logger = logging.getLogger(__name__)
router = APIRouter()


class AcknowledgeBody(BaseModel):
    method_version: str
    method_hash: str
    notes: str | None = None
    created_by: str = "user"


@router.get("", dependencies=[Depends(require_admin)])
def get_forecast_methods() -> dict[str, Any]:
    """Return the forecast methods descriptor (single source of truth for governance)."""
    return get_forecast_methods_doc()


@router.post("/acknowledge", dependencies=[Depends(require_admin)])
def acknowledge_forecast_method(
    body: AcknowledgeBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record a user's acknowledgement/sign-off of the forecast method version."""
    doc = get_forecast_methods_doc()
    expected_version = doc.get("method_version")
    expected_hash = (doc.get("audit") or {}).get("hash")
    if body.method_version != expected_version:
        raise HTTPException(
            status_code=400,
            detail=f"Method version mismatch: expected {expected_version}, got {body.method_version}",
        )
    if body.method_hash != expected_hash:
        raise HTTPException(
            status_code=400,
            detail="Method hash mismatch; descriptor may have changed. Refresh the page.",
        )
    db.execute(
        text(
            """
            INSERT INTO forecast_method_acknowledgements (created_by, method_version, method_hash, notes)
            VALUES (:created_by, :method_version, :method_hash, :notes)
            """
        ),
        {
            "created_by": body.created_by,
            "method_version": body.method_version,
            "method_hash": body.method_hash,
            "notes": body.notes,
        },
    )
    db.commit()
    return {"acknowledged": True, "method_version": body.method_version}


@router.get("/acknowledgements", dependencies=[Depends(require_admin)])
def list_acknowledgements(
    method_version: str | None = Query(None, description="Filter by method version"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List who signed off and when. Optionally filter by method_version."""
    try:
        if method_version:
            result = db.execute(
                text(
                    """
                    SELECT id, created_by, method_version, method_hash, acknowledged_at, notes
                    FROM forecast_method_acknowledgements
                    WHERE method_version = :mv
                    ORDER BY acknowledged_at DESC
                    LIMIT :lim
                    """
                ),
                {"mv": method_version, "lim": limit},
            )
        else:
            result = db.execute(
                text(
                    """
                    SELECT id, created_by, method_version, method_hash, acknowledged_at, notes
                    FROM forecast_method_acknowledgements
                    ORDER BY acknowledged_at DESC
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            )
        rows = result.fetchall()
        return [
            {
                "id": r[0],
                "created_by": r[1],
                "method_version": r[2],
                "method_hash": r[3],
                "acknowledged_at": r[4].isoformat() if r[4] else None,
                "notes": r[5],
            }
            for r in rows
        ]
    except Exception as e:
        if "does not exist" in str(e).lower() or "forecast_method_acknowledgements" in str(e):
            return []
        raise
