"""Stock position breakdown and rolling 12-week view API."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_any_auth
from app.services.stock_position_breakdown import (
    get_rolling_stock_position,
    get_stock_position_breakdown,
)

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_any_auth)])


@router.get("/breakdown")
def get_breakdown(
    plan_run_id: int = Query(..., description="Plan run ID (scenario context)"),
    warehouse_code: str | None = Query(None, description="Filter by warehouse code"),
    sku: str | None = Query(None, description="Filter by SKU"),
    product_family: str | None = Query(None, description="Filter by product family"),
    breach_only: bool = Query(False, description="Only rows with a reorder-point breach"),
    limit: int | None = Query(None, ge=1, le=5000, description="Max rows to return"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Stock position calculation breakdown per SKU x warehouse for the given plan run.
    Returns inputs (on hand, avg demand), policy (target weeks, safety stock, lead time),
    and derived (reorder point, target stock, next breach week, recommended order week/qty).
    """
    return get_stock_position_breakdown(
        db,
        plan_run_id=plan_run_id,
        warehouse_code=warehouse_code,
        sku=sku,
        product_family=product_family,
        breach_only=breach_only,
        limit=limit,
    )


@router.get("/rolling")
def get_rolling(
    plan_run_id: int = Query(..., description="Plan run ID"),
    warehouse_code: str = Query(..., description="Warehouse code"),
    sku: str = Query(..., description="SKU"),
    weeks: int = Query(12, ge=1, le=52, description="Number of weeks"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Rolling N-week stock position for a selected SKU x warehouse: opening, receipts, demand, closing,
    plus planned order qty overlay.
    """
    return get_rolling_stock_position(
        db,
        plan_run_id=plan_run_id,
        warehouse_code=warehouse_code,
        sku=sku,
        weeks=weeks,
    )
