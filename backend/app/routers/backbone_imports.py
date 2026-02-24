"""Backbone CSV import endpoints: stock positions, inbound orders, demand weekly."""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_admin_or_operator
from app.services.backbone_import import (
    import_stock_positions,
    import_inbound_orders,
    import_demand_weekly,
)

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_admin_or_operator)])


@router.post("/stock-positions")
async def upload_stock_positions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload CSV: warehouse_code, sku, iso_year, iso_week, on_hand_units. Returns rows_processed, rows_failed, errors."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return {"rows_processed": 0, "rows_failed": 0, "errors": [{"row_number": 0, "message": "File must be CSV"}]}
    content = await file.read()
    result = import_stock_positions(db, content)
    return {
        "rows_processed": result.rows_processed,
        "rows_failed": result.rows_failed,
        "errors": result.errors,
    }


@router.post("/inbound-orders")
async def upload_inbound_orders(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload CSV: warehouse_code, sku, iso_year, iso_week, inbound_units, supplier_code (optional)."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return {"rows_processed": 0, "rows_failed": 0, "errors": [{"row_number": 0, "message": "File must be CSV"}]}
    content = await file.read()
    result = import_inbound_orders(db, content)
    return {
        "rows_processed": result.rows_processed,
        "rows_failed": result.rows_failed,
        "errors": result.errors,
    }


@router.post("/demand-weekly")
async def upload_demand_weekly(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload CSV: warehouse_code, sku, iso_year, iso_week, demand_units."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return {"rows_processed": 0, "rows_failed": 0, "errors": [{"row_number": 0, "message": "File must be CSV"}]}
    content = await file.read()
    result = import_demand_weekly(db, content)
    return {
        "rows_processed": result.rows_processed,
        "rows_failed": result.rows_failed,
        "errors": result.errors,
    }
