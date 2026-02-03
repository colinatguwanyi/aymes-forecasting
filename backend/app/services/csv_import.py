"""CSV import with validation and dry-run."""
from __future__ import annotations
import csv
import io
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas import ImportDryRunResult, ImportRowError

logger = logging.getLogger(__name__)


def parse_date(s: str) -> tuple[bool, Any]:
    """Parse YYYY-MM-DD; return (ok, date or error)."""
    s = (s or "").strip()
    if not s:
        return False, "Empty date"
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
        if d.weekday() != 0:
            return False, "week_start must be a Monday"
        return True, d
    except ValueError:
        return False, "Invalid date (use YYYY-MM-DD, Monday)"


def parse_decimal(s: str) -> tuple[bool, Decimal | str]:
    s = (s or "0").strip()
    try:
        return True, Decimal(s)
    except (InvalidOperation, ValueError):
        return False, "Invalid number"


def validate_inventory_snapshots(rows: list[dict[str, Any]]) -> ImportDryRunResult:
    errors: list[ImportRowError] = []
    preview: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=2):  # row 2 = header+1
        errs: list[str] = []
        if len(row) < 4:
            errs.append("Missing columns")
        else:
            week_ok, week_val = parse_date(row.get("week_start", ""))
            if not week_ok:
                errs.append(str(week_val))
            qty_ok, qty_val = parse_decimal(row.get("on_hand_qty", ""))
            if not qty_ok:
                errs.append(str(qty_val))
            sku = (row.get("sku") or "").strip()
            wh = (row.get("warehouse_code") or "").strip()
            if not sku:
                errs.append("sku required")
            if not wh:
                errs.append("warehouse_code required")
        if errs:
            errors.append(ImportRowError(row=i, errors=errs))
        else:
            if len(preview) < 5:
                preview.append({**row, "week_start": str(week_val) if week_ok else row.get("week_start"), "on_hand_qty": str(qty_val) if qty_ok else row.get("on_hand_qty")})
    valid_rows = len(rows) - len(errors)
    return ImportDryRunResult(
        valid=len(errors) == 0,
        total_rows=len(rows),
        valid_rows=valid_rows,
        errors=errors,
        preview=preview[:5] if preview else None,
    )


def validate_receipts(rows: list[dict[str, Any]]) -> ImportDryRunResult:
    errors: list[ImportRowError] = []
    preview: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=2):
        errs: list[str] = []
        week_ok, week_val = parse_date(row.get("week_start", ""))
        if not week_ok:
            errs.append(str(week_val))
        qty_ok, qty_val = parse_decimal(row.get("qty", ""))
        if not qty_ok:
            errs.append(str(qty_val))
        sku = (row.get("sku") or "").strip()
        wh = (row.get("warehouse_code") or "").strip()
        if not sku:
            errs.append("sku required")
        if not wh:
            errs.append("warehouse_code required")
        if errs:
            errors.append(ImportRowError(row=i, errors=errs))
        else:
            if len(preview) < 5:
                preview.append({**row, "week_start": str(week_val), "qty": str(qty_val)})
    return ImportDryRunResult(
        valid=len(errors) == 0,
        total_rows=len(rows),
        valid_rows=len(rows) - len(errors),
        errors=errors,
        preview=preview[:5] if preview else None,
    )


def validate_demand_actuals(rows: list[dict[str, Any]]) -> ImportDryRunResult:
    allowed: set[str] = {"CUSTOMER", "SAMPLES", "ADJUSTMENT"}
    errors: list[ImportRowError] = []
    preview: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=2):
        errs: list[str] = []
        week_ok, week_val = parse_date(row.get("week_start", ""))
        if not week_ok:
            errs.append(str(week_val))
        qty_ok, qty_val = parse_decimal(row.get("qty", ""))
        if not qty_ok:
            errs.append(str(qty_val))
        sku = (row.get("sku") or "").strip()
        wh = (row.get("warehouse_code") or "").strip()
        dt = (row.get("demand_type") or "").strip().upper()
        if not sku:
            errs.append("sku required")
        if not wh:
            errs.append("warehouse_code required")
        if dt not in allowed:
            errs.append("demand_type must be CUSTOMER, SAMPLES, or ADJUSTMENT")
        if errs:
            errors.append(ImportRowError(row=i, errors=errs))
        else:
            if len(preview) < 5:
                preview.append({**row, "week_start": str(week_val), "qty": str(qty_val), "demand_type": dt})
    return ImportDryRunResult(
        valid=len(errors) == 0,
        total_rows=len(rows),
        valid_rows=len(rows) - len(errors),
        errors=errors,
        preview=preview[:5] if preview else None,
    )


def validate_samples_withdrawals(rows: list[dict[str, Any]]) -> ImportDryRunResult:
    """Same as demand_actuals but demand_type fixed to SAMPLES."""
    errors: list[ImportRowError] = []
    preview: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=2):
        errs: list[str] = []
        week_ok, week_val = parse_date(row.get("week_start", ""))
        if not week_ok:
            errs.append(str(week_val))
        qty_ok, qty_val = parse_decimal(row.get("qty", ""))
        if not qty_ok:
            errs.append(str(qty_val))
        sku = (row.get("sku") or "").strip()
        wh = (row.get("warehouse_code") or "").strip()
        if not sku:
            errs.append("sku required")
        if not wh:
            errs.append("warehouse_code required")
        if errs:
            errors.append(ImportRowError(row=i, errors=errs))
        else:
            if len(preview) < 5:
                preview.append({**row, "week_start": str(week_val), "qty": str(qty_val), "demand_type": "SAMPLES"})
    return ImportDryRunResult(
        valid=len(errors) == 0,
        total_rows=len(rows),
        valid_rows=len(rows) - len(errors),
        errors=errors,
        preview=preview[:5] if preview else None,
    )


def validate_products(rows: list[dict[str, Any]]) -> ImportDryRunResult:
    errors: list[ImportRowError] = []
    preview: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=2):
        errs: list[str] = []
        sku = (row.get("sku") or "").strip()
        if not sku:
            errs.append("sku required")
        if errs:
            errors.append(ImportRowError(row=i, errors=errs))
        else:
            if len(preview) < 5:
                preview.append(row)
    return ImportDryRunResult(
        valid=len(errors) == 0,
        total_rows=len(rows),
        valid_rows=len(rows) - len(errors),
        errors=errors,
        preview=preview[:5] if preview else None,
    )


def read_csv(file_content: bytes) -> list[dict[str, Any]]:
    text = file_content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)
