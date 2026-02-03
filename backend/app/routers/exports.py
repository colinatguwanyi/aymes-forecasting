from __future__ import annotations
import csv
import logging
from io import StringIO
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PlanRun, PlannedOrder, ProjectedInventory

logger = logging.getLogger(__name__)
router = APIRouter()


def _stream_csv(rows: list[dict[str, Any]], columns: list[str]) -> StringIO:
    buf = StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: str(v) if v is not None else "" for k, v in r.items()})
    buf.seek(0)
    return buf


@router.get("/projected-inventory")
def export_projected_inventory(
    plan_run_id: int = Query(...),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    rows = (
        db.query(ProjectedInventory)
        .filter(ProjectedInventory.plan_run_id == plan_run_id)
        .order_by(ProjectedInventory.week_start, ProjectedInventory.sku)
        .all()
    )
    data = [
        {
            "scenario_name": run.scenario_name,
            "week_start": r.week_start,
            "sku": r.sku,
            "warehouse_code": r.warehouse_code,
            "projected_qty": r.projected_qty,
            "weeks_of_cover": r.weeks_of_cover,
            "stockout": r.stockout,
        }
        for r in rows
    ]
    cols = ["scenario_name", "week_start", "sku", "warehouse_code", "projected_qty", "weeks_of_cover", "stockout"]
    buf = _stream_csv(data, cols)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=projected_inventory_{run.scenario_name}.csv"},
    )


@router.get("/planned-orders")
def export_planned_orders(
    plan_run_id: int = Query(...),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    rows = (
        db.query(PlannedOrder)
        .filter(PlannedOrder.plan_run_id == plan_run_id)
        .order_by(PlannedOrder.week_start, PlannedOrder.sku)
        .all()
    )
    data = [
        {
            "scenario_name": run.scenario_name,
            "week_start": r.week_start,
            "sku": r.sku,
            "warehouse_code": r.warehouse_code,
            "order_qty": r.order_qty,
        }
        for r in rows
    ]
    cols = ["scenario_name", "week_start", "sku", "warehouse_code", "order_qty"]
    buf = _stream_csv(data, cols)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=planned_orders_{run.scenario_name}.csv"},
    )
