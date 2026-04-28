"""Transform staged demand into canonical demand_facts_weekly.

- Applies SKU mapping (sku_code_map)
- Filters inactive products
- Enforces minimum history per sku+warehouse
- Fills missing weeks with qty=0, is_imputed=true
- UPSERT into demand_facts_weekly
- Records rejections and run metrics
"""
from __future__ import annotations
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.ingestion_progress import merge_ingest_progress
from app.models import (
    DemandFactsWeekly,
    DemandStageWeekly,
    DemandType,
    IngestionRejection,
    IngestionRun,
    IngestionStatus,
)
from app.services.sku_resolution import active_sku_set, resolve_sku_code_map

logger = logging.getLogger(__name__)

MIN_WEEKS_HISTORY = 60  # configurable; per-sku per-warehouse completeness


def build_weekly_series_from_stage(
    db: Session,
    run_id: UUID,
    min_weeks_history: int = MIN_WEEKS_HISTORY,
) -> None:
    """
    Read demand_stage_weekly for run_id; apply mapping, filter, completeness;
    fill missing weeks; UPSERT into demand_facts_weekly. Update ingestion_runs and rejections.
    """
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        raise ValueError(f"Ingestion run not found: {run_id}")
    if run.entity.value != "demand":
        raise ValueError(f"Run entity is {run.entity.value}, expected demand")

    run.status = IngestionStatus.RUNNING
    db.flush()

    stage_rows = (
        db.query(DemandStageWeekly)
        .filter(DemandStageWeekly.ingestion_run_id == run_id)
        .all()
    )
    run.row_count = len(stage_rows)
    merge_ingest_progress(
        db,
        run,
        import_phase="demand_transform",
        import_message="Transforming staged demand into demand_facts_weekly…",
        import_detail=f"{len(stage_rows):,} staged rows",
    )

    active = active_sku_set(db)
    # (week_start, sku, warehouse_code, demand_type) -> sum(qty) from accepted rows
    aggregated: dict[tuple[date, str, str, DemandType], Decimal] = defaultdict(Decimal)
    # Rejections: (stage_row_id, reason) for rows we skip
    rejections: list[tuple[int, str, dict[str, Any]]] = []

    for row in stage_rows:
        w_start = cast(date, row.week_start)
        _raw = getattr(row, "sku_raw", None)
        sku_r = "" if _raw is None else str(_raw)
        mapped_sku = resolve_sku_code_map(db, sku_r, w_start)
        if mapped_sku not in active:
            msg = f"Unmapped SKU: {sku_r} in demand_weekly_transform"
            logger.error(msg)
            rejections.append(
                (
                    cast(int, row.id),
                    msg,
                    {"sku_raw": sku_r, "sku": mapped_sku, "week_start": str(w_start)},
                )
            )
            continue
        wh_code = cast(str, row.warehouse_code)
        dt_enum = cast(DemandType, row.demand_type)
        qty_val = cast(Decimal, row.qty)
        key = (w_start, mapped_sku, wh_code, dt_enum)
        aggregated[key] += qty_val

    # Per (sku, warehouse_code, demand_type) count weeks; if < min_weeks_history, reject that series
    series_weeks: dict[tuple[str, str, DemandType], set[date]] = defaultdict(set)
    for (week_start, sku, wh, dt), _ in aggregated.items():
        series_weeks[(sku, wh, dt)].add(week_start)

    insufficient: set[tuple[str, str, DemandType]] = {
        k for k, weeks in series_weeks.items() if len(weeks) < min_weeks_history
    }

    # Remove aggregated entries that belong to insufficient series; add rejections for those keys
    keys_to_drop = [
        k for k in aggregated
        if (k[1], k[2], k[3]) in insufficient
    ]
    for k in keys_to_drop:
        del aggregated[k]

    # Rejection reason for insufficient history (one per series)
    for (sku, wh, dt) in insufficient:
        rejections.append((
            0,
            f"Insufficient history: {len(series_weeks[(sku, wh, dt)])} weeks < {min_weeks_history}",
            {"sku": sku, "warehouse_code": wh, "demand_type": dt.value},
        ))

    # Fill missing weeks: for each (sku, wh, dt) that passed, add qty=0 for every week in [min_week, max_week]
    for (sku, wh, dt), weeks in series_weeks.items():
        if (sku, wh, dt) in insufficient:
            continue
        min_week = min(weeks)
        max_week = max(weeks)
        w = min_week
        while w <= max_week:
            key = (w, sku, wh, dt)
            if key not in aggregated:
                aggregated[key] = Decimal("0")
            w += timedelta(days=7)

    # Keys that came from stage (after mapping) - for is_imputed
    raw_keys: set[tuple[date, str, str, DemandType]] = set()
    for r in stage_rows:
        r_week = cast(date, r.week_start)
        _raw = getattr(r, "sku_raw", None)
        r_sku_raw = "" if _raw is None else str(_raw)
        r_wh = cast(str, r.warehouse_code)
        r_dt = cast(DemandType, r.demand_type)
        raw_keys.add((r_week, resolve_sku_code_map(db, r_sku_raw, r_week), r_wh, r_dt))

    # UPSERT into demand_facts_weekly
    inserted = 0
    updated = 0
    for (week_start, sku, warehouse_code, demand_type), qty in aggregated.items():
        if (sku, warehouse_code, demand_type) in insufficient:
            continue
        was_in_stage = (week_start, sku, warehouse_code, demand_type) in raw_keys
        is_imputed = not was_in_stage and qty == 0

        existing = (
            db.query(DemandFactsWeekly)
            .filter(
                DemandFactsWeekly.week_start == week_start,
                DemandFactsWeekly.sku == sku,
                DemandFactsWeekly.warehouse_code == warehouse_code,
                DemandFactsWeekly.demand_type == demand_type,
            )
            .first()
        )
        if existing:
            existing.qty = qty
            existing.source_run_id = run_id
            existing.is_imputed = is_imputed
            updated += 1
        else:
            db.add(
                DemandFactsWeekly(
                    week_start=week_start,
                    sku=sku,
                    warehouse_code=warehouse_code,
                    demand_type=demand_type,
                    qty=qty,
                    source_run_id=run_id,
                    is_imputed=is_imputed,
                    is_outlier=False,
                    outlier_method=None,
                )
            )
            inserted += 1

    # Persist rejections (row_number: stage row id or 1-based index for series rejections)
    for idx, (row_id, reason, payload) in enumerate(rejections, start=1):
        db.add(
            IngestionRejection(
                ingestion_run_id=run_id,
                row_number=row_id if row_id else idx,
                raw_payload=payload,
                reason=reason,
            )
        )

    run.inserted_count = inserted
    run.updated_count = updated
    run.rejected_count = len(rejections)
    run.status = IngestionStatus.SUCCESS
    run.error_summary = None
    run.finished_at = datetime.now(timezone.utc)
    db.flush()
    logger.info("weekly_series_builder: run_id=%s inserted=%s updated=%s rejected=%s", run_id, inserted, updated, len(rejections))
