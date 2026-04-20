"""BLP-AYMES Report format: Code, Description, Balance, Location, Expiry Date."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass
class BlpNormalizedRow:
    """Normalized row from BLP format."""
    sku: str
    qty_on_hand: int
    expiry_date: date | None
    expiry_status: str | None  # "EXPIRING" when value was "EXPIRING"
    bin_location: str | None
    reject_reason: str | None


def is_blp_aymes_format(headers: list[str]) -> bool:
    """Detect BLP-AYMES format: must contain Code and Balance (case-insensitive)."""
    lower = {str(h).strip().lower() for h in headers}
    return "code" in lower and "balance" in lower


def _norm_key(k: str) -> str:
    return str(k).strip().lower().replace(" ", "_")


def _get(row: dict[str, Any], *keys: str) -> Any:
    """Case-insensitive lookup; normalizes spaces to underscores."""
    row_map = {_norm_key(k): (k, v) for k, v in row.items()}
    for k in keys:
        nk = _norm_key(k)
        if nk in row_map:
            _, v = row_map[nk]
            return v
    return None


def _parse_date_ddmmyyyy(s: str) -> tuple[bool, date | str]:
    """Parse DD/MM/YYYY. Returns (ok, date_or_error)."""
    s = (s or "").strip()
    if not s:
        return True, None
    try:
        d = datetime.strptime(s, "%d/%m/%Y").date()
        return True, d
    except ValueError:
        return False, "Invalid date (use DD/MM/YYYY)"


def _parse_qty(s: Any) -> tuple[bool, int, str | None]:
    """Parse numeric; blanks -> 0. Returns (ok, value, error)."""
    if s is None or s == "" or (isinstance(s, str) and not s.strip()):
        return True, 0, None
    try:
        val = int(Decimal(str(s).strip()))
        return True, val, None
    except (ValueError, TypeError, ArithmeticError):
        return False, 0, "Invalid number"


def parse_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return rows as-is; used after format detection."""
    return rows


def normalize(
    row: dict[str, Any],
    row_number: int,
) -> BlpNormalizedRow:
    """Normalize one BLP row. Invalid values set reject_reason; qty still parsed for aggregation."""
    code_raw = _get(row, "Code", "code")
    sku = (str(code_raw).strip() if code_raw else "") or ""
    balance_raw = _get(row, "Balance", "balance")
    location_raw = _get(row, "Location", "location")
    expiry_raw = _get(row, "Expiry Date", "Expiry Date", "expiry date")

    reject_reason: str | None = None
    qty_on_hand = 0
    expiry_date: date | None = None
    expiry_status: str | None = None
    bin_location: str | None = None

    if not sku:
        reject_reason = "Code required"
    else:
        qty_ok, qty_val, qty_err = _parse_qty(balance_raw)
        if not qty_ok:
            reject_reason = qty_err or "Invalid Balance"
        else:
            qty_on_hand = qty_val

    if location_raw is not None and str(location_raw).strip():
        bin_location = str(location_raw).strip()

    if expiry_raw is not None and str(expiry_raw).strip():
        expiry_str = str(expiry_raw).strip()
        if expiry_str.upper() == "EXPIRING":
            expiry_status = "EXPIRING"
        else:
            date_ok, date_val = _parse_date_ddmmyyyy(expiry_str)
            if date_ok and date_val is not None:
                expiry_date = date_val
            # Invalid date: ignore (v1), do not reject row

    return BlpNormalizedRow(
        sku=sku,
        qty_on_hand=qty_on_hand,
        expiry_date=expiry_date,
        expiry_status=expiry_status,
        bin_location=bin_location,
        reject_reason=reject_reason,
    )


def aggregate(
    normalized_rows: list[BlpNormalizedRow],
    snapshot_date: date,
    warehouse_code: str,
) -> list[tuple[str, str, date, int]]:
    """Group by (snapshot_date, warehouse_code, sku); sum qty_on_hand. Returns [(warehouse_code, sku, snapshot_date, qty), ...]."""
    by_key: dict[tuple[str, str], int] = {}
    for nr in normalized_rows:
        if nr.reject_reason:
            continue
        if not nr.sku:
            continue
        key = (warehouse_code, nr.sku)
        by_key[key] = by_key.get(key, 0) + nr.qty_on_hand
    return [(wh, sku, snapshot_date, qty) for (wh, sku), qty in by_key.items()]
