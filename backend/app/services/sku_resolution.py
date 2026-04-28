"""Resolve CSV / stage SKU codes via sku_code_map and validate against active products."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, SkuCodeMap
from app.schemas import ImportRowError
from app.services.time_bucketing import week_start_for_date

logger = logging.getLogger(__name__)


def resolve_sku_code_map(db: Session, sku_raw: str, week_start: date) -> str:
    """Apply sku_code_map: old_sku -> new_sku for week_start. Return mapped sku or sku_raw."""
    row = (
        db.query(SkuCodeMap)
        .filter(
            SkuCodeMap.old_sku == sku_raw,
            (SkuCodeMap.effective_from_week_start.is_(None)) | (SkuCodeMap.effective_from_week_start <= week_start),
            (SkuCodeMap.effective_to_week_start.is_(None)) | (SkuCodeMap.effective_to_week_start >= week_start),
        )
        .first()
    )
    return str(row.new_sku) if row else sku_raw


def active_sku_set(db: Session) -> set[str]:
    """Set of sku where products.active = true."""
    rows = db.execute(select(Product.sku).where(Product.active.is_(True)))
    return {cast(str, r[0]) for r in rows}


def import_row_catalog_errors_demand_like(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    source: str,
) -> list[ImportRowError]:
    """For rows with valid week_start + sku + warehouse_code, reject if mapped SKU is not active."""
    from app.services.csv_import import parse_date

    active = active_sku_set(db)
    out: list[ImportRowError] = []
    for i, row in enumerate(rows, start=2):
        week_ok, week_val = parse_date(row.get("week_start", ""))
        sku_raw = (row.get("sku") or "").strip()
        wh = (row.get("warehouse_code") or "").strip()
        if not week_ok or not sku_raw or not wh:
            continue
        ws = week_start_for_date(cast(date, week_val))
        mapped = resolve_sku_code_map(db, sku_raw, ws)
        if mapped not in active:
            msg = f"Unmapped SKU: {sku_raw} in {source}"
            logger.error(msg)
            out.append(ImportRowError(row=i, errors=[msg]))
    return out


def import_row_catalog_errors_product_update_only(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    source: str,
) -> list[ImportRowError]:
    """Reject product CSV rows whose sku does not already exist in products (update-only import)."""
    existing = {cast(str, r[0]) for r in db.query(Product.sku).all()}
    out: list[ImportRowError] = []
    for i, row in enumerate(rows, start=2):
        sku = (row.get("sku") or "").strip()
        if not sku:
            continue
        if sku not in existing:
            msg = f"Unmapped SKU: {sku} in {source}"
            logger.error(msg)
            out.append(ImportRowError(row=i, errors=[msg]))
    return out
