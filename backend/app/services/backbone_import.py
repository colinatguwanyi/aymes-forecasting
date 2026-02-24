"""Backbone CSV import: stock positions, inbound orders, demand weekly. Validation and apply."""
from __future__ import annotations
import csv
import io
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.calendar_weeks import ensure_calendar_week
from app.models import (
    CalendarWeek,
    DemandWeekly,
    DemandSourceEnum,
    InboundOrderWeekly,
    InboundSourceEnum,
    Product,
    StockPositionWeekly,
    StockSourceEnum,
    Supplier,
    Warehouse,
)

logger = logging.getLogger(__name__)


def read_csv_bytes(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _parse_int(s: str, min_val: int = 0) -> tuple[bool, Optional[int], str]:
    s = (s or "").strip()
    if s == "":
        return False, None, "Missing value"
    try:
        v = int(s)
        if v < min_val:
            return False, None, f"Must be >= {min_val}"
        return True, v, ""
    except ValueError:
        return False, None, "Invalid integer"


def _parse_iso_week(s_year: str, s_week: str) -> tuple[bool, Optional[int], Optional[int], str]:
    try:
        y = int((s_year or "").strip())
        w = int((s_week or "").strip())
        if not (1 <= w <= 53):
            return False, None, None, "iso_week must be 1-53"
        if y < 2000 or y > 2100:
            return False, None, None, "iso_year out of range"
        return True, y, w, ""
    except ValueError:
        return False, None, None, "iso_year and iso_week must be integers"


class ImportResult:
    def __init__(self) -> None:
        self.rows_processed = 0
        self.rows_failed = 0
        self.errors: list[dict[str, Any]] = []  # {"row_number": int, "message": str}


def import_stock_positions(db: Session, content: bytes) -> ImportResult:
    """Import stock positions weekly CSV: warehouse_code, sku, iso_year, iso_week, on_hand_units."""
    result = ImportResult()
    rows = read_csv_bytes(content)
    required = {"warehouse_code", "sku", "iso_year", "iso_week", "on_hand_units"}
    seen: set[tuple[str, str, int, int]] = set()

    for i, row in enumerate(rows, start=2):
        row_errors: list[str] = []
        if required - set(k.strip().lower() for k in row.keys()):
            row_errors.append("Missing columns: warehouse_code, sku, iso_year, iso_week, on_hand_units")
        else:
            wc = (row.get("warehouse_code") or "").strip()
            sku = (row.get("sku") or "").strip()
            ok_week, iso_y, iso_w, err_week = _parse_iso_week(row.get("iso_year", ""), row.get("iso_week", ""))
            if not ok_week:
                row_errors.append(err_week)
            ok_units, units, err_units = _parse_int(row.get("on_hand_units", ""), 0)
            if not ok_units:
                row_errors.append(err_units)

            key = (wc, sku, iso_y or 0, iso_w or 0)
            if key in seen:
                row_errors.append("Duplicate row in upload (same warehouse+sku+week)")
            seen.add(key)

            if not row_errors:
                wh = db.query(Warehouse).filter(Warehouse.code == wc).first()
                prod = db.query(Product).filter(Product.sku == sku).first()
                if not wh:
                    row_errors.append(f"Unknown warehouse_code: {wc}")
                if not prod:
                    row_errors.append(f"Unknown sku: {sku}")
                if not row_errors and wh and prod and iso_y is not None and iso_w is not None and units is not None:
                    cw = ensure_calendar_week(db, iso_y, iso_w)
                    existing = (
                        db.query(StockPositionWeekly)
                        .filter(
                            StockPositionWeekly.warehouse_id == wh.id,
                            StockPositionWeekly.product_id == prod.id,
                            StockPositionWeekly.calendar_week_id == cw.id,
                        )
                        .first()
                    )
                    if existing:
                        existing.on_hand_units = units
                    else:
                        db.add(
                            StockPositionWeekly(
                                warehouse_id=wh.id,
                                product_id=prod.id,
                                calendar_week_id=cw.id,
                                on_hand_units=units,
                                source=StockSourceEnum.IMPORT,
                            )
                        )
                    result.rows_processed += 1
                    continue

        if row_errors:
            result.rows_failed += 1
            result.errors.append({"row_number": i, "message": "; ".join(row_errors)})

    db.commit()
    return result


def import_inbound_orders(db: Session, content: bytes) -> ImportResult:
    """Import inbound orders weekly: warehouse_code, sku, iso_year, iso_week, inbound_units, supplier_code (optional)."""
    result = ImportResult()
    rows = read_csv_bytes(content)
    required = {"warehouse_code", "sku", "iso_year", "iso_week", "inbound_units"}
    seen: set[tuple[str, str, int, int]] = set()

    for i, row in enumerate(rows, start=2):
        row_errors: list[str] = []
        row_keys = {k.strip().lower(): k for k in row.keys()}
        if not all((r in row_keys for r in ["warehouse_code", "sku", "iso_year", "iso_week", "inbound_units"])):
            row_errors.append("Missing columns: warehouse_code, sku, iso_year, iso_week, inbound_units")
        else:
            wc = (row.get("warehouse_code") or "").strip()
            sku = (row.get("sku") or "").strip()
            ok_week, iso_y, iso_w, err_week = _parse_iso_week(row.get("iso_year", ""), row.get("iso_week", ""))
            if not ok_week:
                row_errors.append(err_week)
            ok_units, units, err_units = _parse_int(row.get("inbound_units", ""), 0)
            if not ok_units:
                row_errors.append(err_units)

            key = (wc, sku, iso_y or 0, iso_w or 0)
            if key in seen:
                row_errors.append("Duplicate row in upload")
            seen.add(key)

            if not row_errors:
                wh = db.query(Warehouse).filter(Warehouse.code == wc).first()
                prod = db.query(Product).filter(Product.sku == sku).first()
                if not wh:
                    row_errors.append(f"Unknown warehouse_code: {wc}")
                if not prod:
                    row_errors.append(f"Unknown sku: {sku}")
                supplier_id = None
                sc = (row.get("supplier_code") or "").strip()
                if sc:
                    sup = db.query(Supplier).filter(Supplier.code == sc).first()
                    if not sup:
                        row_errors.append(f"Unknown supplier_code: {sc}")
                    else:
                        supplier_id = sup.id
                if not row_errors and wh and prod and iso_y is not None and iso_w is not None and units is not None:
                    cw = ensure_calendar_week(db, iso_y, iso_w)
                    db.add(
                        InboundOrderWeekly(
                            warehouse_id=wh.id,
                            product_id=prod.id,
                            supplier_id=supplier_id,
                            calendar_week_id=cw.id,
                            inbound_units=units,
                            source=InboundSourceEnum.IMPORT,
                        )
                    )
                    result.rows_processed += 1
                    continue

        if row_errors:
            result.rows_failed += 1
            result.errors.append({"row_number": i, "message": "; ".join(row_errors)})

    db.commit()
    return result


def import_demand_weekly(db: Session, content: bytes) -> ImportResult:
    """Import demand weekly: warehouse_code, sku, iso_year, iso_week, demand_units."""
    result = ImportResult()
    rows = read_csv_bytes(content)
    required = {"warehouse_code", "sku", "iso_year", "iso_week", "demand_units"}
    seen: set[tuple[str, str, int, int]] = set()

    for i, row in enumerate(rows, start=2):
        row_errors: list[str] = []
        if required - set(k.strip().lower() for k in row.keys()):
            row_errors.append("Missing columns: warehouse_code, sku, iso_year, iso_week, demand_units")
        else:
            wc = (row.get("warehouse_code") or "").strip()
            sku = (row.get("sku") or "").strip()
            ok_week, iso_y, iso_w, err_week = _parse_iso_week(row.get("iso_year", ""), row.get("iso_week", ""))
            if not ok_week:
                row_errors.append(err_week)
            ok_units, units, err_units = _parse_int(row.get("demand_units", ""), 0)
            if not ok_units:
                row_errors.append(err_units)

            key = (wc, sku, iso_y or 0, iso_w or 0)
            if key in seen:
                row_errors.append("Duplicate row in upload")
            seen.add(key)

            if not row_errors:
                wh = db.query(Warehouse).filter(Warehouse.code == wc).first()
                prod = db.query(Product).filter(Product.sku == sku).first()
                if not wh:
                    row_errors.append(f"Unknown warehouse_code: {wc}")
                if not prod:
                    row_errors.append(f"Unknown sku: {sku}")
                if not row_errors and wh and prod and iso_y is not None and iso_w is not None and units is not None:
                    cw = ensure_calendar_week(db, iso_y, iso_w)
                    existing = (
                        db.query(DemandWeekly)
                        .filter(
                            DemandWeekly.warehouse_id == wh.id,
                            DemandWeekly.product_id == prod.id,
                            DemandWeekly.calendar_week_id == cw.id,
                        )
                        .first()
                    )
                    if existing:
                        existing.demand_units = units
                    else:
                        db.add(
                            DemandWeekly(
                                warehouse_id=wh.id,
                                product_id=prod.id,
                                calendar_week_id=cw.id,
                                demand_units=units,
                                source=DemandSourceEnum.IMPORT,
                            )
                        )
                    result.rows_processed += 1
                    continue

        if row_errors:
            result.rows_failed += 1
            result.errors.append({"row_number": i, "message": "; ".join(row_errors)})

    db.commit()
    return result
