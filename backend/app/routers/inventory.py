from __future__ import annotations
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InventorySnapshotWeekly
from app.schemas import InventorySnapshot

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[InventorySnapshot])
def list_inventory_snapshots(
    week_start: str | None = Query(None),
    sku: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[InventorySnapshotWeekly]:
    q = db.query(InventorySnapshotWeekly)
    if week_start:
        q = q.filter(InventorySnapshotWeekly.week_start == datetime.fromisoformat(week_start).date())
    if sku:
        q = q.filter(InventorySnapshotWeekly.sku == sku)
    if warehouse_code:
        q = q.filter(InventorySnapshotWeekly.warehouse_code == warehouse_code)
    return q.order_by(InventorySnapshotWeekly.week_start, InventorySnapshotWeekly.sku).all()
