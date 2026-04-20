"""Backbone reports: Breaches, Out of stock risk."""
from __future__ import annotations
import csv
import io
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_any_auth
from app.models import BreachStatusEnum, CalendarWeek, Product, ProjectionWeekly, Warehouse

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_any_auth)])


@router.get("/breaches")
def report_breaches(
    run_id: str = Query(...),
    warehouse_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="red | amber"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List rows where breach_status in (red, amber). Filters: warehouse, status."""
    q = (
        db.query(ProjectionWeekly, Product, Warehouse, CalendarWeek)
        .join(Product, ProjectionWeekly.product_id == Product.id)
        .join(Warehouse, ProjectionWeekly.warehouse_id == Warehouse.id)
        .join(CalendarWeek, ProjectionWeekly.calendar_week_id == CalendarWeek.id)
        .filter(ProjectionWeekly.run_id == run_id)
        .filter(ProjectionWeekly.breach_status.in_(["red", "amber"]))
    )
    if warehouse_id is not None:
        q = q.filter(ProjectionWeekly.warehouse_id == warehouse_id)
    if status:
        status_enum = BreachStatusEnum.RED if status.lower() == "red" else BreachStatusEnum.AMBER
        q = q.filter(ProjectionWeekly.breach_status == status_enum)
    rows = q.order_by(ProjectionWeekly.warehouse_id, ProjectionWeekly.product_id, CalendarWeek.iso_year, CalendarWeek.iso_week).all()
    out = []
    for proj, prod, wh, cw in rows:
        breach_val = proj.breach_status.value if hasattr(proj.breach_status, "value") else str(proj.breach_status)
        out.append({
            "run_id": proj.run_id,
            "warehouse_code": wh.code,
            "sku": prod.sku,
            "product_name": prod.name,
            "iso_year": cw.iso_year,
            "iso_week": cw.iso_week,
            "closing_units": proj.closing_units,
            "safety_stock_target_units": proj.safety_stock_target_units,
            "breach_status": breach_val,
        })
    return out


@router.get("/breaches/export")
def export_breaches_csv(
    run_id: str = Query(...),
    warehouse_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    q = (
        db.query(ProjectionWeekly, Product, Warehouse, CalendarWeek)
        .join(Product, ProjectionWeekly.product_id == Product.id)
        .join(Warehouse, ProjectionWeekly.warehouse_id == Warehouse.id)
        .join(CalendarWeek, ProjectionWeekly.calendar_week_id == CalendarWeek.id)
        .filter(ProjectionWeekly.run_id == run_id)
        .filter(ProjectionWeekly.breach_status.in_([BreachStatusEnum.RED, BreachStatusEnum.AMBER]))
    )
    if warehouse_id is not None:
        q = q.filter(ProjectionWeekly.warehouse_id == warehouse_id)
    if status:
        status_enum = BreachStatusEnum.RED if status.lower() == "red" else BreachStatusEnum.AMBER
        q = q.filter(ProjectionWeekly.breach_status == status_enum)
    rows = q.order_by(ProjectionWeekly.warehouse_id, ProjectionWeekly.product_id, CalendarWeek.iso_year, CalendarWeek.iso_week).all()
    cols = ["warehouse_code", "sku", "product_name", "iso_year", "iso_week", "closing_units", "safety_stock_target_units", "breach_status"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for proj, prod, wh, cw in rows:
        writer.writerow({
            "warehouse_code": wh.code,
            "sku": prod.sku,
            "product_name": prod.name or "",
            "iso_year": cw.iso_year,
            "iso_week": cw.iso_week,
            "closing_units": proj.closing_units,
            "safety_stock_target_units": proj.safety_stock_target_units,
            "breach_status": proj.breach_status.value if hasattr(proj.breach_status, "value") else str(proj.breach_status),
        })
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=breaches.csv"},
    )


@router.get("/out-of-stock-risk")
def report_out_of_stock_risk(
    run_id: str = Query(...),
    warehouse_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List rows where closing_units <= 0 within horizon."""
    q = (
        db.query(ProjectionWeekly, Product, Warehouse, CalendarWeek)
        .join(Product, ProjectionWeekly.product_id == Product.id)
        .join(Warehouse, ProjectionWeekly.warehouse_id == Warehouse.id)
        .join(CalendarWeek, ProjectionWeekly.calendar_week_id == CalendarWeek.id)
        .filter(ProjectionWeekly.run_id == run_id)
        .filter(ProjectionWeekly.closing_units <= 0)
    )
    if warehouse_id is not None:
        q = q.filter(ProjectionWeekly.warehouse_id == warehouse_id)
    rows = q.order_by(ProjectionWeekly.warehouse_id, ProjectionWeekly.product_id, CalendarWeek.iso_year, CalendarWeek.iso_week).all()
    out = []
    for proj, prod, wh, cw in rows:
        out.append({
            "run_id": proj.run_id,
            "warehouse_code": wh.code,
            "sku": prod.sku,
            "product_name": prod.name,
            "iso_year": cw.iso_year,
            "iso_week": cw.iso_week,
            "closing_units": proj.closing_units,
        })
    return out


@router.get("/out-of-stock-risk/export")
def export_out_of_stock_risk_csv(
    run_id: str = Query(...),
    warehouse_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    q = (
        db.query(ProjectionWeekly, Product, Warehouse, CalendarWeek)
        .join(Product, ProjectionWeekly.product_id == Product.id)
        .join(Warehouse, ProjectionWeekly.warehouse_id == Warehouse.id)
        .join(CalendarWeek, ProjectionWeekly.calendar_week_id == CalendarWeek.id)
        .filter(ProjectionWeekly.run_id == run_id)
        .filter(ProjectionWeekly.closing_units <= 0)
    )
    if warehouse_id is not None:
        q = q.filter(ProjectionWeekly.warehouse_id == warehouse_id)
    rows = q.order_by(ProjectionWeekly.warehouse_id, ProjectionWeekly.product_id, CalendarWeek.iso_year, CalendarWeek.iso_week).all()
    cols = ["warehouse_code", "sku", "product_name", "iso_year", "iso_week", "closing_units"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for proj, prod, wh, cw in rows:
        writer.writerow({
            "warehouse_code": wh.code,
            "sku": prod.sku,
            "product_name": prod.name or "",
            "iso_year": cw.iso_year,
            "iso_week": cw.iso_week,
            "closing_units": proj.closing_units,
        })
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=out_of_stock_risk.csv"},
    )
