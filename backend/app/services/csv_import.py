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


def parse_date_ddmmyyyy(s: str) -> tuple[bool, Any]:
    """Parse UK-style dates; return (ok, date or error message).

    Accepts DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, or ISO YYYY-MM-DD (common Excel exports).
    """
    s = (s or "").strip()
    if not s:
        return False, "Empty date"
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return True, datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return True, datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return False, "Invalid date (use DD/MM/YYYY, DD-MM-YYYY, or YYYY-MM-DD)"


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
    """Decode CSV bytes to text; try UTF-8 (with BOM) first, then Windows-1252 (common for Excel)."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = file_content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Could not decode file as UTF-8, CP1252, or Latin-1")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def read_csv_chunked(
    file_content: bytes,
    chunk_size: int = 5000,
) -> Any:
    """Yield CSV rows in chunks to avoid loading large files fully into memory."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = file_content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Could not decode file as UTF-8, CP1252, or Latin-1")
    reader = csv.DictReader(io.StringIO(text))
    chunk: list[dict[str, Any]] = []
    for row in reader:
        chunk.append(row)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def read_csv_or_xlsx(file_content: bytes, filename: str | None = None) -> list[dict[str, Any]]:
    """Parse CSV or XLSX into list of dicts. Keys are stripped. For XLSX uses pandas (openpyxl)."""
    fn = (filename or "").lower()
    if fn.endswith(".xlsx") or fn.endswith(".xls"):
        import pandas as pd  # noqa: PLC0415

        df = pd.read_excel(io.BytesIO(file_content), engine="openpyxl" if fn.endswith(".xlsx") else None)
        # Normalize: strip column names, replace NaN with None
        df = df.rename(columns=lambda c: (c.strip() if isinstance(c, str) else str(c)))
        rows = df.to_dict("records")
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append({str(k): (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in r.items()})
        return out
    return read_csv(file_content)
