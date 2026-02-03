from __future__ import annotations
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DemandType, InventorySnapshotWeekly, Product, Receipt, DemandActual
from app.schemas import ImportDryRunResult, ImportRowError
from app.services.csv_import import (
    parse_date,
    parse_decimal,
    read_csv,
    validate_demand_actuals,
    validate_inventory_snapshots,
    validate_products,
    validate_receipts,
    validate_samples_withdrawals,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _apply_inventory(rows: list[dict[str, Any]], db: Session) -> None:
    for row in rows:
        ok, week = parse_date(row.get("week_start", ""))
        ok2, qty = parse_decimal(row.get("on_hand_qty", "0"))
        if ok and ok2:
            sku = (row.get("sku") or "").strip()
            wh = (row.get("warehouse_code") or "").strip()
            existing = (
                db.query(InventorySnapshotWeekly)
                .filter(
                    InventorySnapshotWeekly.week_start == week,
                    InventorySnapshotWeekly.sku == sku,
                    InventorySnapshotWeekly.warehouse_code == wh,
                )
                .first()
            )
            if existing:
                existing.on_hand_qty = qty
            else:
                db.add(
                    InventorySnapshotWeekly(
                        week_start=week,
                        sku=sku,
                        warehouse_code=wh,
                        on_hand_qty=qty,
                    )
                )
    db.commit()


def _apply_receipts(rows: list[dict[str, Any]], db: Session) -> None:
    for row in rows:
        ok, week = parse_date(row.get("week_start", ""))
        ok2, qty = parse_decimal(row.get("qty", "0"))
        if ok and ok2:
            sku = (row.get("sku") or "").strip()
            wh = (row.get("warehouse_code") or "").strip()
            src_raw = (row.get("source_type") or "").strip()
            src = src_raw or ""
            q = db.query(Receipt).filter(
                Receipt.week_start == week,
                Receipt.sku == sku,
                Receipt.warehouse_code == wh,
            )
            if src == "":
                existing = q.filter(Receipt.source_type.is_(None)).first()
            else:
                existing = q.filter(Receipt.source_type == src).first()
            if existing:
                existing.qty = qty
                if src != "":
                    existing.source_type = src
            else:
                db.add(
                    Receipt(
                        week_start=week,
                        sku=sku,
                        warehouse_code=wh,
                        qty=qty,
                        source_type=src_raw or None,
                    )
                )
    db.commit()


def _apply_demand(rows: list[dict[str, Any]], demand_type_override: str | None, db: Session) -> None:
    for row in rows:
        ok, week = parse_date(row.get("week_start", ""))
        ok2, qty = parse_decimal(row.get("qty", "0"))
        if ok and ok2:
            sku = (row.get("sku") or "").strip()
            wh = (row.get("warehouse_code") or "").strip()
            dt_str = demand_type_override or (row.get("demand_type") or "").strip().upper()
            if dt_str in ("CUSTOMER", "SAMPLES", "ADJUSTMENT"):
                dt_enum = DemandType[dt_str]
                existing = (
                    db.query(DemandActual)
                    .filter(
                        DemandActual.week_start == week,
                        DemandActual.sku == sku,
                        DemandActual.warehouse_code == wh,
                        DemandActual.demand_type == dt_enum,
                    )
                    .first()
                )
                if existing:
                    existing.qty = qty
                else:
                    db.add(
                        DemandActual(
                            week_start=week,
                            sku=sku,
                            warehouse_code=wh,
                            demand_type=dt_enum,
                            qty=qty,
                        )
                    )
    db.commit()


def _apply_products(rows: list[dict[str, Any]], db: Session) -> None:
    for row in rows:
        sku = (row.get("sku") or "").strip()
        if not sku:
            continue
        name = (row.get("name") or "").strip() or None
        desc = (row.get("description") or "").strip() or None
        existing = db.query(Product).filter(Product.sku == sku).first()
        if existing:
            existing.name = name
            existing.description = desc
        else:
            db.add(Product(sku=sku, name=name, description=desc))
    db.commit()


@router.post("/inventory-snapshots", response_model=ImportDryRunResult)
async def import_inventory_snapshots(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="If true, only validate and return errors"),
    db: Session = Depends(get_db),
) -> ImportDryRunResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file required")
    content = await file.read()
    rows = read_csv(content)
    if not rows:
        return ImportDryRunResult(valid=False, total_rows=0, valid_rows=0, errors=[ImportRowError(row=1, errors=["No data rows"])])
    result = validate_inventory_snapshots(rows)
    if not dry_run and result.valid_rows > 0:
        valid_rows = [r for i, r in enumerate(rows) if not any(e.row == i + 2 for e in result.errors)]
        _apply_inventory(valid_rows, db)
    return result


@router.post("/receipts", response_model=ImportDryRunResult)
async def import_receipts(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="If true, only validate and return errors"),
    db: Session = Depends(get_db),
) -> ImportDryRunResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file required")
    content = await file.read()
    rows = read_csv(content)
    if not rows:
        return ImportDryRunResult(valid=False, total_rows=0, valid_rows=0, errors=[ImportRowError(row=1, errors=["No data rows"])])
    result = validate_receipts(rows)
    if not dry_run and result.valid_rows > 0:
        valid_rows = [r for i, r in enumerate(rows) if not any(e.row == i + 2 for e in result.errors)]
        _apply_receipts(valid_rows, db)
    return result


@router.post("/demand-actuals", response_model=ImportDryRunResult)
async def import_demand_actuals(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="If true, only validate and return errors"),
    db: Session = Depends(get_db),
) -> ImportDryRunResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file required")
    content = await file.read()
    rows = read_csv(content)
    if not rows:
        return ImportDryRunResult(valid=False, total_rows=0, valid_rows=0, errors=[ImportRowError(row=1, errors=["No data rows"])])
    result = validate_demand_actuals(rows)
    if not dry_run and result.valid_rows > 0:
        valid_rows = [r for i, r in enumerate(rows) if not any(e.row == i + 2 for e in result.errors)]
        _apply_demand(valid_rows, None, db)
    return result


@router.post("/samples-withdrawals", response_model=ImportDryRunResult)
async def import_samples_withdrawals(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="If true, only validate and return errors"),
    db: Session = Depends(get_db),
) -> ImportDryRunResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file required")
    content = await file.read()
    rows = read_csv(content)
    if not rows:
        return ImportDryRunResult(valid=False, total_rows=0, valid_rows=0, errors=[ImportRowError(row=1, errors=["No data rows"])])
    result = validate_samples_withdrawals(rows)
    if not dry_run and result.valid_rows > 0:
        valid_rows = [r for i, r in enumerate(rows) if not any(e.row == i + 2 for e in result.errors)]
        _apply_demand(valid_rows, "SAMPLES", db)
    return result


@router.post("/products", response_model=ImportDryRunResult)
async def import_products(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="If true, only validate and return errors"),
    db: Session = Depends(get_db),
) -> ImportDryRunResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file required")
    content = await file.read()
    rows = read_csv(content)
    if not rows:
        return ImportDryRunResult(valid=False, total_rows=0, valid_rows=0, errors=[ImportRowError(row=1, errors=["No data rows"])])
    result = validate_products(rows)
    if not dry_run and result.valid_rows > 0:
        valid_rows = [r for i, r in enumerate(rows) if not any(e.row == i + 2 for e in result.errors)]
        _apply_products(valid_rows, db)
    return result
