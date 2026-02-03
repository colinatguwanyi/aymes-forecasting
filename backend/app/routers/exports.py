from __future__ import annotations
import csv
import logging
from datetime import date, timedelta
from io import StringIO
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PlanRun, PlannedOrder, PlanningPolicy, ProjectedInventory

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
            "start_qty": getattr(r, "start_qty", None),
            "receipts_qty": getattr(r, "receipts_qty", None),
            "demand_qty": getattr(r, "demand_qty", None),
            "projected_qty": r.projected_qty,
            "weeks_of_cover": r.weeks_of_cover,
            "stockout": r.stockout,
        }
        for r in rows
    ]
    cols = [
        "scenario_name", "week_start", "sku", "warehouse_code",
        "start_qty", "receipts_qty", "demand_qty", "projected_qty",
        "weeks_of_cover", "stockout",
    ]
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


@router.get("/exceptions")
def export_exceptions(
    plan_run_id: int = Query(...),
    within_weeks: int = Query(12, ge=1, le=52),
    include_low_cover: bool = Query(True),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    run_at: date = cast(date, run.run_at)
    cutoff = run_at + timedelta(weeks=within_weeks)
    rows = (
        db.query(ProjectedInventory)
        .filter(
            ProjectedInventory.plan_run_id == plan_run_id,
            ProjectedInventory.week_start >= run_at,
            ProjectedInventory.week_start <= cutoff,
        )
        .order_by(ProjectedInventory.week_start, ProjectedInventory.sku)
        .all()
    )
    data: list[dict[str, Any]] = []
    for r in rows:
        r_stockout: bool = cast(bool, r.stockout)
        r_woc: Any = r.weeks_of_cover
        if r_stockout:
            data.append({
                "type": "stockout",
                "severity": "error",
                "sku": r.sku,
                "warehouse_code": r.warehouse_code,
                "week_start": r.week_start,
                "message": f"Projected stockout week {r.week_start}",
                "projected_qty": r.projected_qty,
                "weeks_of_cover": r.weeks_of_cover,
            })
        elif include_low_cover and r_woc is not None:
            try:
                if float(r_woc) < 2:
                    data.append({
                        "type": "low_cover",
                        "severity": "warning",
                        "sku": r.sku,
                        "warehouse_code": r.warehouse_code,
                        "week_start": r.week_start,
                        "message": f"Low cover ({r.weeks_of_cover} weeks) week {r.week_start}",
                        "projected_qty": r.projected_qty,
                        "weeks_of_cover": r.weeks_of_cover,
                    })
            except (TypeError, ValueError):
                pass
    cols = ["type", "severity", "sku", "warehouse_code", "week_start", "message", "projected_qty", "weeks_of_cover"]
    buf = _stream_csv(data, cols)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=exceptions_{run.scenario_name}.csv"},
    )


@router.get("/sku-explanation-report")
def export_sku_explanation_report(
    plan_run_id: int = Query(...),
    sku: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    q = (
        db.query(ProjectedInventory)
        .filter(ProjectedInventory.plan_run_id == plan_run_id)
        .order_by(ProjectedInventory.week_start, ProjectedInventory.sku)
    )
    if sku:
        q = q.filter(ProjectedInventory.sku == sku)
    if warehouse_code:
        q = q.filter(ProjectedInventory.warehouse_code == warehouse_code)
    rows = q.all()
    policies_by_key: dict[tuple[str, str], Any] = {}
    for pol in db.query(PlanningPolicy).all():
        key = (cast(str, pol.sku), cast(str, pol.warehouse_code))
        policies_by_key[key] = pol
    data = []
    for r in rows:
        key = (cast(str, r.sku), cast(str, r.warehouse_code))
        pol = policies_by_key.get(key)
        data.append({
            "scenario_name": run.scenario_name,
            "sku": r.sku,
            "warehouse_code": r.warehouse_code,
            "week_start": r.week_start,
            "forecast_method": "trailing_mean",
            "mode": getattr(pol.mode, "value", None) if pol and pol.mode else None,
            "target_weeks": pol.target_weeks if pol else None,
            "safety_stock_weeks": pol.safety_stock_weeks if pol else None,
            "start_qty": r.start_qty,
            "receipts_qty": r.receipts_qty,
            "demand_qty": r.demand_qty,
            "projected_qty": r.projected_qty,
            "weeks_of_cover": r.weeks_of_cover,
            "stockout": r.stockout,
        })
    cols = [
        "scenario_name", "sku", "warehouse_code", "week_start", "forecast_method",
        "mode", "target_weeks", "safety_stock_weeks",
        "start_qty", "receipts_qty", "demand_qty", "projected_qty", "weeks_of_cover", "stockout",
    ]
    buf = _stream_csv(data, cols)
    name = f"sku_explanation_{run.scenario_name}"
    if sku:
        name += f"_{sku}"
    if warehouse_code:
        name += f"_{warehouse_code}"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}.csv"},
    )
