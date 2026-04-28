# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportAttributeAccessIssue=false, reportUntypedFunctionDecorator=false
from __future__ import annotations
import logging
from datetime import date
from typing import Any, cast

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_admin_or_operator
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
from app.services.sku_resolution import (
    import_row_catalog_errors_demand_like,
    import_row_catalog_errors_product_update_only,
    resolve_sku_code_map,
)
from app.services.time_bucketing import week_start_for_date

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_admin_or_operator)])


def _merge_import_row_errors(base: ImportDryRunResult, extra: list[ImportRowError]) -> ImportDryRunResult:
    by_row: dict[int, list[str]] = {}
    for e in base.errors:
        by_row[e.row] = list(e.errors)
    for e in extra:
        by_row.setdefault(e.row, []).extend(e.errors)
    merged_errs = [ImportRowError(row=r, errors=errs) for r, errs in sorted(by_row.items())]
    n_err_rows = len(merged_errs)
    return ImportDryRunResult(
        valid=n_err_rows == 0,
        total_rows=base.total_rows,
        valid_rows=max(0, base.total_rows - n_err_rows),
        errors=merged_errs,
        preview=base.preview,
    )


def _apply_inventory(rows: list[dict[str, Any]], db: Session) -> None:
    for row in rows:
        ok, week = parse_date(row.get("week_start", ""))
        ok2, qty = parse_decimal(row.get("on_hand_qty", "0"))
        if ok and ok2:
            sku_raw = (row.get("sku") or "").strip()
            ws = week_start_for_date(cast(date, week))
            sku = resolve_sku_code_map(db, sku_raw, ws)
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
            sku_raw = (row.get("sku") or "").strip()
            ws = week_start_for_date(cast(date, week))
            sku = resolve_sku_code_map(db, sku_raw, ws)
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
            sku_raw = (row.get("sku") or "").strip()
            ws = week_start_for_date(cast(date, week))
            sku = resolve_sku_code_map(db, sku_raw, ws)
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
            logger.warning(
                "Skipped legacy /import/products row: SKU %s is not in catalog (use product master import to create SKUs)",
                sku,
            )
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
    result = _merge_import_row_errors(
        result,
        import_row_catalog_errors_demand_like(db, rows, source="legacy_inventory_import"),
    )
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
    result = _merge_import_row_errors(
        result,
        import_row_catalog_errors_demand_like(db, rows, source="legacy_receipts_import"),
    )
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
    result = _merge_import_row_errors(
        result,
        import_row_catalog_errors_demand_like(db, rows, source="legacy_demand_import"),
    )
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
    result = _merge_import_row_errors(
        result,
        import_row_catalog_errors_demand_like(db, rows, source="legacy_samples_import"),
    )
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
    result = _merge_import_row_errors(
        result,
        import_row_catalog_errors_product_update_only(db, rows, source="legacy_products_import"),
    )
    if not dry_run and result.valid_rows > 0:
        valid_rows = [r for i, r in enumerate(rows) if not any(e.row == i + 2 for e in result.errors)]
        _apply_products(valid_rows, db)
    return result
