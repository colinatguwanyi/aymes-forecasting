"""Ingestion mode detection: weekly vs historical, requires_confirm guardrails."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    DemandStageWeekly,
    IngestionEntity,
    IngestionMode,
    SalesOutStage,
    StockOnHandStage,
)
from app.services.csv_import import parse_date_ddmmyyyy
from app.services.soh_ingestion import _parse_date_soh

logger = logging.getLogger(__name__)

# Thresholds for auto-detecting historical backfill (requires confirmation)
ROW_COUNT_THRESHOLD = 20_000
SPAN_DAYS_THRESHOLD = 120
FILE_SIZE_BYTES_THRESHOLD = 25 * 1024 * 1024  # ~25 MB


def _get_date_from_sales_out_row(row: Any) -> date | None:
    """Extract processed_date from SalesOutStage row."""
    d = getattr(row, "processed_date", None)
    if d is not None:
        return d
    return None


def _get_date_from_soh_row(row: Any) -> date | None:
    """Extract and parse date from StockOnHandStage row."""
    raw = getattr(row, "stock_at_raw", None) or ""
    ok, val = _parse_date_soh(str(raw))
    return val if ok and isinstance(val, date) else None


def _get_date_from_demand_row(row: Any) -> date | None:
    """Extract week_start from DemandStageWeekly row."""
    d = getattr(row, "week_start", None)
    return d if d is not None else None


def compute_date_range_and_mode(
    db: Session,
    run_id: UUID,
    entity: IngestionEntity,
    row_count: int,
    file_size_bytes: int | None,
) -> tuple[date | None, date | None, IngestionMode, bool]:
    """
    Compute date_min, date_max from staged rows; determine mode and requires_confirm.
    Returns (date_min, date_max, mode, requires_confirm).
    """
    date_min: date | None = None
    date_max: date | None = None

    if entity == IngestionEntity.SALES_OUT:
        rows = db.query(SalesOutStage).filter(SalesOutStage.ingestion_run_id == run_id).all()
        get_date = _get_date_from_sales_out_row
    elif entity == IngestionEntity.STOCK_ON_HAND:
        rows = (
            db.query(StockOnHandStage)
            .filter(StockOnHandStage.ingestion_run_id == run_id, StockOnHandStage.reject_reason.is_(None))
            .all()
        )
        get_date = _get_date_from_soh_row
    elif entity == IngestionEntity.DEMAND:
        rows = db.query(DemandStageWeekly).filter(DemandStageWeekly.ingestion_run_id == run_id).all()
        get_date = _get_date_from_demand_row
    else:
        return None, None, IngestionMode.WEEKLY, False

    for row in rows:
        d = get_date(row)
        if d is not None:
            if date_min is None or d < date_min:
                date_min = d
            if date_max is None or d > date_max:
                date_max = d

    span_days = (date_max - date_min).days if date_min and date_max else 0

    is_historical = (
        row_count > ROW_COUNT_THRESHOLD
        or span_days > SPAN_DAYS_THRESHOLD
        or (file_size_bytes is not None and file_size_bytes > FILE_SIZE_BYTES_THRESHOLD)
    )
    mode = IngestionMode.HISTORICAL if is_historical else IngestionMode.WEEKLY
    requires_confirm = is_historical

    logger.info(
        "ingestion_mode: run_id=%s entity=%s row_count=%s span_days=%s file_size=%s -> mode=%s requires_confirm=%s",
        run_id, entity.value, row_count, span_days, file_size_bytes, mode.value, requires_confirm,
    )
    return date_min, date_max, mode, requires_confirm
