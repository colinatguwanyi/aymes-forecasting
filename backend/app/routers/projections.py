"""Backbone: run projection, get projection by run_id, export CSV."""
from __future__ import annotations
import csv
import io
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_any_auth
from app.models import CalendarWeek, Product, ProjectionWeekly, Warehouse
from app.services.projection_service import run_projection

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_any_auth)])


@router.post("/run")
def run_projection_endpoint(
    warehouse_id: Optional[int] = Query(None),
    start_iso_year: int = Query(2025),
    start_iso_week: int = Query(1),
    horizon_weeks: int = Query(26, ge=1, le=52),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Run projection; returns run_id."""
    run_id = run_projection(
        db,
        warehouse_id=warehouse_id,
        start_iso_year=start_iso_year,
        start_iso_week=start_iso_week,
        horizon_weeks=horizon_weeks,
    )
    return {"run_id": run_id}


@router.get("")
@router.get("/", include_in_schema=False)
def list_projections(
    run_id: str = Query(...),
    warehouse_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get projection rows for run_id (for grid)."""
    q = (
        db.query(ProjectionWeekly, Product, Warehouse, CalendarWeek)
        .join(Product, ProjectionWeekly.product_id == Product.id)
        .join(Warehouse, ProjectionWeekly.warehouse_id == Warehouse.id)
        .join(CalendarWeek, ProjectionWeekly.calendar_week_id == CalendarWeek.id)
        .filter(ProjectionWeekly.run_id == run_id)
    )
    if warehouse_id is not None:
        q = q.filter(ProjectionWeekly.warehouse_id == warehouse_id)
    rows = q.order_by(ProjectionWeekly.warehouse_id, ProjectionWeekly.product_id, ProjectionWeekly.calendar_week_id).all()
    out = []
    for proj, prod, wh, cw in rows:
        out.append({
            "run_id": proj.run_id,
            "warehouse_id": proj.warehouse_id,
            "warehouse_code": wh.code,
            "product_id": proj.product_id,
            "sku": prod.sku,
            "product_name": prod.name,
            "iso_year": cw.iso_year,
            "iso_week": cw.iso_week,
            "week_label": f"{cw.iso_year}-W{cw.iso_week:02d}",
            "opening_units": proj.opening_units,
            "inbound_units": proj.inbound_units,
            "demand_units": proj.demand_units,
            "closing_units": proj.closing_units,
            "weeks_of_supply": float(proj.weeks_of_supply) if proj.weeks_of_supply is not None else None,
            "safety_stock_target_units": proj.safety_stock_target_units,
            "breach_status": proj.breach_status.value if hasattr(proj.breach_status, "value") else str(proj.breach_status),
        })
    return out


@router.get("/export")
def export_projections_csv(
    run_id: str = Query(...),
    warehouse_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Export projection grid as CSV."""
    q = (
        db.query(ProjectionWeekly, Product, Warehouse, CalendarWeek)
        .join(Product, ProjectionWeekly.product_id == Product.id)
        .join(Warehouse, ProjectionWeekly.warehouse_id == Warehouse.id)
        .join(CalendarWeek, ProjectionWeekly.calendar_week_id == CalendarWeek.id)
        .filter(ProjectionWeekly.run_id == run_id)
    )
    if warehouse_id is not None:
        q = q.filter(ProjectionWeekly.warehouse_id == warehouse_id)
    rows = q.order_by(ProjectionWeekly.warehouse_id, ProjectionWeekly.product_id, ProjectionWeekly.calendar_week_id).all()
    cols = [
        "warehouse_code", "sku", "product_name", "iso_year", "iso_week",
        "opening_units", "inbound_units", "demand_units", "closing_units",
        "weeks_of_supply", "safety_stock_target_units", "breach_status",
    ]
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
            "opening_units": proj.opening_units,
            "inbound_units": proj.inbound_units,
            "demand_units": proj.demand_units,
            "closing_units": proj.closing_units,
            "weeks_of_supply": proj.weeks_of_supply if proj.weeks_of_supply is not None else "",
            "safety_stock_target_units": proj.safety_stock_target_units,
            "breach_status": proj.breach_status.value if hasattr(proj.breach_status, "value") else str(proj.breach_status),
        })
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=projections_{run_id[:8]}.csv"},
    )
