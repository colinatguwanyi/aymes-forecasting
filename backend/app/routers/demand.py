from __future__ import annotations
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DemandActual as DemandActualModel
from app.schemas import DemandActual

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[DemandActual])
def list_demand_actuals(
    week_start: str | None = Query(None),
    sku: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    demand_type: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[DemandActualModel]:
    q = db.query(DemandActualModel)
    if week_start:
        q = q.filter(DemandActualModel.week_start == datetime.fromisoformat(week_start).date())
    if sku:
        q = q.filter(DemandActualModel.sku == sku)
    if warehouse_code:
        q = q.filter(DemandActualModel.warehouse_code == warehouse_code)
    if demand_type:
        q = q.filter(DemandActualModel.demand_type == demand_type)
    return q.order_by(DemandActualModel.week_start, DemandActualModel.sku).all()
