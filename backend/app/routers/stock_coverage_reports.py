"""Stock coverage report: weeks_cover = on_hand / avg_demand from actuals only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_any_auth
from app.services.stock_coverage import compute_stock_coverage

router = APIRouter(dependencies=[Depends(require_any_auth)])


@router.get("")
def get_stock_coverage(
    warehouse_code: str | None = Query(None, description="Filter by warehouse (AAH, BLP); omit for all"),
    weeks_window: int = Query(13, ge=1, le=52, description="Weeks for avg demand calculation"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Stock coverage report by warehouse.
    - Latest SOH per warehouse from inventory_snapshots_weekly.
    - Avg weekly demand from demand_actuals (AAH: CUSTOMER only; BLP: CUSTOMER+SAMPLES).
    - weeks_cover = on_hand_qty / avg_weekly_demand.
    - status_bucket: Critical <2, Low <4, Monitor <8, Healthy ≥8, No demand when avg=0.
    """
    return compute_stock_coverage(db, warehouse_code=warehouse_code, weeks_window=weeks_window)
