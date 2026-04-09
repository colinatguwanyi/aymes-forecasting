"""Stock On Hand (SOH) ingestion: stage -> daily canonical -> weekly canonical (W-TUE)."""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

# SOH_INGESTION_VERSION: used to confirm hot-reload picked up this file
SOH_INGESTION_VERSION = "v2-snapshot-date-fix"

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    IngestionMode,
    IngestionRejection,
    IngestionRun,
    IngestionStatus,
    InventorySnapshotDaily,
    InventorySnapshotWeekly,
    StockOnHandStage,
    Warehouse,
    WarehouseBranchMapping,
)
from app.services.time_bucketing import week_start_for_date

logger = logging.getLogger(__name__)
logger.warning("SOH_INGESTION_LOADED: %s", SOH_INGESTION_VERSION)

SOH_SOURCE_TYPE = "soh"
CHUNK_SIZE = 5000
HISTORICAL_BATCH_DAYS = 60
DEFAULT_AAH_WAREHOUSE = "AAH"


def _get(row: dict[str, Any], *keys: str) -> Any:
    def _norm(k: str) -> str:
        return str(k).strip().lower().replace(" ", "_")

    row_map = {_norm(k): v for k, v in row.items()}
    for k in keys:
        nk = _norm(k)
        if nk in row_map:
            v = row_map[nk]
            if v is not None and str(v).strip() != "":
                return v
    return None


def _branch_to_warehouse_code(db: Session) -> dict[str, str]:
    """Return mapping branch_name (normalized upper) -> warehouse_code."""
    rows = db.query(WarehouseBranchMapping).all()
    out: dict[str, str] = {}
    for r in rows:
        bn = (getattr(r, "branch_name", None) or "").strip().upper()
        if bn:
            out[bn] = cast(str, r.warehouse_code)
    return out


def _parse_date_soh(s: str) -> tuple[bool, date | str]:
    """Parse date from SOH 'Stock at' - try DD/MM/YYYY, then YYYY-MM-DD."""
    s = (s or "").strip()
    if not s:
        return False, "Empty date"
    try:
        from datetime import datetime as dt
        if "/" in s:
            d = dt.strptime(s, "%d/%m/%Y").date()
        else:
            d = dt.strptime(s, "%Y-%m-%d").date()
        return True, d
    except ValueError:
        return False, "Invalid date (use DD/MM/YYYY or YYYY-MM-DD)"


def _parse_int_soh(s: Any, default: int = 0) -> tuple[bool, int, str | None]:
    """Parse integer; blanks -> default. Reject negative for STOCK."""
    if s is None or s == "" or (isinstance(s, str) and not s.strip()):
        return True, default, None
    try:
        val = int(float(str(s).strip()))
        return True, val, None
    except (ValueError, TypeError):
        return False, default, "Invalid number"


def validate_and_stage_soh_row(
    db: Session,
    run_id: UUID,
    row: dict[str, Any],
    row_number: int,
    branch_to_wh: dict[str, str],
    warehouse_code_override: str | None = None,
    snapshot_date_override: date | None = None,
) -> tuple[bool, str | None]:
    """Validate one row; always insert into stock_on_hand_stage (set reject_reason if invalid). Returns (staged_ok, reason_if_rejected).
    When warehouse_code_override is provided, branch column is ignored and all rows use that warehouse (roll-up by product).
    When snapshot_date_override is provided it is used when the row has no 'Stock at' date column."""
    stock_at_raw = _get(row, "Stock at", "stock_at", "Stock at (date)")
    branch_raw = _get(row, "Branch Name", "branch_name", "Branch Name")
    aah_raw = _get(row, "AAH Code", "aah_code", "AAH Code")
    stock_raw = _get(row, "ON STOCK", "STOCK", "stock")
    on_order_raw = _get(row, "ON ORDER", "on_order")

    if row_number == 2:  # first data row only
        logger.warning(
            "SOH_ROW_DEBUG row=%d keys=%s stock_at_raw=%r aah_raw=%r snapshot_override=%r",
            row_number, list(row.keys())[:8], stock_at_raw, aah_raw, snapshot_date_override,
        )

    reject_reason: str | None = None
    warehouse_code: str | None = None
    if not aah_raw or not str(aah_raw).strip():
        reject_reason = "AAH Code required"
    else:
        # Use file-level date if present; fall back to the snapshot_date_override from the upload form
        if stock_at_raw:
            date_ok, date_val = _parse_date_soh(str(stock_at_raw))
        elif snapshot_date_override is not None:
            date_ok, date_val = True, snapshot_date_override
        else:
            date_ok, date_val = False, "Empty date (provide snapshot_date when file has no 'Stock at' column)"
        if not date_ok:
            reject_reason = str(date_val)
        else:
            if warehouse_code_override:
                warehouse_code = warehouse_code_override.strip().upper()
            else:
                # AAH format: roll all branches to ONE warehouse (AAH); branch read but not persisted
                warehouse_code = DEFAULT_AAH_WAREHOUSE
            if not warehouse_code:
                reject_reason = "unknown branch mapping" if not warehouse_code_override else "warehouse_code required"
            else:
                stock_ok, stock_val, stock_err = _parse_int_soh(stock_raw, 0)
                if not stock_ok:
                    reject_reason = stock_err or "Invalid STOCK"
                elif stock_val < 0:
                    reject_reason = "STOCK cannot be negative"
                else:
                    on_order_ok, on_order_val, on_order_err = _parse_int_soh(on_order_raw, 0)
                    if not on_order_ok:
                        reject_reason = on_order_err or "Invalid ON ORDER"

    sku = str(aah_raw).strip() if aah_raw else ""
    # Store warehouse_code for build_daily (AAH or override); rejected rows use None
    warehouse_for_storage: str | None = None
    if not reject_reason and warehouse_code:
        warehouse_for_storage = warehouse_code.strip().upper()
    branch_to_store = warehouse_for_storage
    # When file has no 'Stock at' column, persist the override date so build_daily_from_stage can read it
    effective_stock_at_raw = str(stock_at_raw) if stock_at_raw is not None else (
        snapshot_date_override.strftime("%Y-%m-%d") if snapshot_date_override is not None else None
    )
    stock_val = 0
    on_order_val = 0
    if not reject_reason:
        _, stock_val, _ = _parse_int_soh(stock_raw, 0)
        _, on_order_val, _ = _parse_int_soh(on_order_raw, 0)
    row_hash = hashlib.sha256(f"{effective_stock_at_raw}|{branch_to_store or ''}|{sku}|{stock_val}|{on_order_val}".encode()).hexdigest()[:64]

    db.add(
        StockOnHandStage(
            ingestion_run_id=run_id,
            stock_at_raw=effective_stock_at_raw,
            branch_name_raw=branch_to_store,
            aah_code_raw=sku or None,
            stock_raw=str(stock_raw) if stock_raw is not None else None,
            on_order_raw=str(on_order_raw) if on_order_raw is not None else None,
            description_raw=str(_get(row, "description", "Description")) if _get(row, "description", "Description") else None,
            reject_reason=reject_reason,
            row_hash=row_hash,
        )
    )
    return (reject_reason is None, reject_reason)


def stage_blp_soh(
    db: Session,
    run_id: UUID,
    rows: list[dict[str, Any]],
    warehouse_code: str,
    snapshot_date: date,
) -> tuple[int, int, dict[str, Any]]:
    """
    Stage BLP-AYMES format: normalize, resolve Code to canonical sku, aggregate, write to stock_on_hand_stage.
    Location and Expiry Date ignored for stock totals. Returns (staged_count, rejected_count, summary).
    """
    from app.ingestion.soh.adapters.blp_aymes_report import normalize
    from app.ingestion.soh.product_resolution import resolve_code_to_sku

    wh_upper = warehouse_code.strip().upper()
    resolved_by_mapping_table = 0
    resolved_by_sku = 0
    resolved_by_aah_code = 0
    resolved_by_hs_code = 0
    rejected = 0
    # Coverage: unique codes and units
    codes_mapped: set[str] = set()
    codes_missing: set[str] = set()
    units_total = 0
    units_missing = 0
    # (resolved_sku, qty) for aggregation
    resolved_rows: list[tuple[str, int]] = []

    for i, row in enumerate(rows, start=2):
        nr = normalize(row, i)
        if nr.reject_reason:
            rejected += 1
            db.add(
                IngestionRejection(
                    ingestion_run_id=run_id,
                    row_number=i,
                    raw_payload=dict(row),
                    reason=nr.reject_reason or "validation failed",
                )
            )
            continue
        ext_code = (nr.sku or "").strip()
        qty = nr.qty_on_hand
        units_total += qty
        desc = _get(row, "Description", "description") or ""
        desc_str = str(desc).strip() if desc else ""
        sku, method = resolve_code_to_sku(db, nr.sku, desc_str, warehouse_code=wh_upper)
        if not sku:
            rejected += 1
            if ext_code:
                codes_missing.add(ext_code)
            units_missing += qty
            db.add(
                IngestionRejection(
                    ingestion_run_id=run_id,
                    row_number=i,
                    raw_payload=dict(row),
                    reason="product_not_found",
                )
            )
            continue
        if ext_code:
            codes_mapped.add(ext_code)
        if method == "mapping_table":
            resolved_by_mapping_table += 1
        elif method == "sku":
            resolved_by_sku += 1
        elif method == "aah_code":
            resolved_by_aah_code += 1
        elif method == "hs_code":
            resolved_by_hs_code += 1
        resolved_rows.append((sku, nr.qty_on_hand))

    # Aggregate by (warehouse, resolved_sku) with SUM
    by_key: dict[tuple[str, str], int] = {}
    for sku, qty in resolved_rows:
        key = (wh_upper, sku)
        by_key[key] = by_key.get(key, 0) + qty

    snapshot_str = snapshot_date.isoformat()
    for (wh, sku), qty in by_key.items():
        row_hash = hashlib.sha256(
            f"{snapshot_str}|{wh}|{sku}|{qty}|0".encode()
        ).hexdigest()[:64]
        db.add(
            StockOnHandStage(
                ingestion_run_id=run_id,
                stock_at_raw=snapshot_str,
                branch_name_raw=wh,
                aah_code_raw=sku,
                stock_raw=str(qty),
                on_order_raw="0",
                description_raw=None,
                reject_reason=None,
                row_hash=row_hash,
            )
        )
    staged = len(by_key)
    total_qty = sum(by_key.values())
    distinct_skus = len({sku for (_, sku) in by_key})
    total_unique_codes = len(codes_mapped) + len(codes_missing)
    pct_coverage = (len(codes_mapped) / total_unique_codes * 100) if total_unique_codes else 100.0
    pct_units_missing = (units_missing / units_total * 100) if units_total else 0.0
    summary = {
        "distinct_skus": distinct_skus,
        "total_qty": total_qty,
        "row_count": len(rows),
        "parsing_errors": rejected,
        "resolved_by_mapping_table": resolved_by_mapping_table,
        "resolved_by_sku": resolved_by_sku,
        "resolved_by_aah_code": resolved_by_aah_code,
        "resolved_by_hs_code": resolved_by_hs_code,
        "rejected_rows": rejected,
        "total_units_imported": total_qty,
        "coverage": {
            "total_unique_codes": total_unique_codes,
            "mapped_codes": len(codes_mapped),
            "missing_codes": len(codes_missing),
            "pct_coverage_codes": round(pct_coverage, 2),
            "units_total": units_total,
            "units_missing": units_missing,
            "pct_units_missing": round(pct_units_missing, 2),
        },
    }
    return staged, rejected, summary


def build_daily_from_stage(db: Session, run_id: UUID) -> tuple[int, int]:
    """
    Transform stock_on_hand_stage (valid rows only, reject_reason IS NULL) into inventory_snapshots_daily.
    Idempotent: delete from inventory_snapshots_daily where source_type='soh' AND source_run_id=run_id, then insert.
    Returns (rows_inserted, rows_rejected).
    """
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        raise ValueError(f"Ingestion run not found: {run_id}")
    if getattr(run, "entity", None) and getattr(run.entity, "value", None) != "stock_on_hand":
        raise ValueError(f"Run entity is {getattr(run.entity, 'value', run.entity)}, expected stock_on_hand")

    run.status = IngestionStatus.RUNNING
    db.flush()

    mode = getattr(run, "mode", None)
    is_historical = mode == IngestionMode.HISTORICAL

    stage_rows = (
        db.query(StockOnHandStage)
        .filter(StockOnHandStage.ingestion_run_id == run_id, StockOnHandStage.reject_reason.is_(None))
        .all()
    )

    branch_to_wh = _branch_to_warehouse_code(db)
    # Fallback: if branch not in mapping, treat as direct warehouse code (e.g. BLP format)
    def _resolve_warehouse(branch_raw: str) -> str | None:
        wh = branch_to_wh.get(branch_raw)
        if wh:
            return wh
        # Direct warehouse code (e.g. BLP)
        w = db.query(Warehouse).filter(func.upper(Warehouse.code) == branch_raw).first()
        return cast(str, w.code) if w else None

    # (warehouse_code, sku, as_of_date) -> (on_hand, on_order); sum when duplicate (roll up to product in warehouse)
    aggregated: dict[tuple[str, str, date], tuple[int, int]] = {}
    rejected = 0
    for row in stage_rows:
        branch_raw = (getattr(row, "branch_name_raw", None) or "").strip().upper()
        wh = _resolve_warehouse(branch_raw)
        if not wh:
            rejected += 1
            continue
        sku = (getattr(row, "aah_code_raw", None) or "").strip()
        date_ok, date_val = _parse_date_soh(str(getattr(row, "stock_at_raw", "") or ""))
        if not date_ok:
            rejected += 1
            continue
        as_of_date = cast(date, date_val)
        try:
            on_hand = int(float(str(getattr(row, "stock_raw", 0) or 0)))
        except (ValueError, TypeError):
            on_hand = 0
        try:
            on_order = int(float(str(getattr(row, "on_order_raw", 0) or 0)))
        except (ValueError, TypeError):
            on_order = 0
        key = (wh, sku, as_of_date)
        if key in aggregated:
            existing_oh, existing_oo = aggregated[key]
            aggregated[key] = (existing_oh + on_hand, existing_oo + on_order)
        else:
            aggregated[key] = (on_hand, on_order)

    # Idempotent: remove any existing daily rows for this run
    db.query(InventorySnapshotDaily).filter(
        InventorySnapshotDaily.source_type == SOH_SOURCE_TYPE,
        InventorySnapshotDaily.source_run_id == run_id,
    ).delete(synchronize_session=False)

    inserted = 0
    items = list(aggregated.items())
    if is_historical and len(items) > 100:
        # Chunk by date range
        dates_sorted = sorted({k[2] for k in aggregated.keys()})
        for i in range(0, len(dates_sorted), HISTORICAL_BATCH_DAYS):
            batch_dates = set(dates_sorted[i : i + HISTORICAL_BATCH_DAYS])
            batch_items = [(k, v) for k, v in items if k[2] in batch_dates]
            for (warehouse_code, sku, as_of_date), (on_hand_units, on_order_units) in batch_items:
                db.add(
                    InventorySnapshotDaily(
                        warehouse_code=warehouse_code,
                        sku=sku,
                        as_of_date=as_of_date,
                        on_hand_units=Decimal(str(on_hand_units)),
                        on_order_units=Decimal(str(on_order_units)),
                        source_type=SOH_SOURCE_TYPE,
                        source_run_id=run_id,
                    )
                )
                inserted += 1
            db.flush()
            _pm = getattr(run, "progress_meta", None)
            _run_pm = _pm if isinstance(_pm, dict) else {}
            run.progress_meta = {**_run_pm, "daily_batches_done": (i // HISTORICAL_BATCH_DAYS) + 1}
    else:
        for (warehouse_code, sku, as_of_date), (on_hand_units, on_order_units) in items:
            db.add(
                InventorySnapshotDaily(
                    warehouse_code=warehouse_code,
                    sku=sku,
                    as_of_date=as_of_date,
                    on_hand_units=Decimal(str(on_hand_units)),
                    on_order_units=Decimal(str(on_order_units)),
                    source_type=SOH_SOURCE_TYPE,
                    source_run_id=run_id,
                )
            )
            inserted += 1

    run.inserted_count = inserted
    run.updated_count = 0
    run.rejected_count = rejected
    run.status = IngestionStatus.SUCCESS
    run.error_summary = None
    run.finished_at = datetime.now(timezone.utc)
    db.flush()
    logger.info("build_daily_from_stage: run_id=%s inserted=%s rejected=%s", run_id, inserted, rejected)
    return inserted, rejected


def build_weekly_from_daily(db: Session, run_id: UUID) -> int:
    """
    Roll up inventory_snapshots_daily (source_type=soh, source_run_id=run_id) to inventory_snapshots_weekly.
    For each (warehouse_code, sku, week_start): take latest as_of_date in that week, use its on_hand_units.
    Idempotent: delete from inventory_snapshots_weekly where source_type='soh' AND source_run_id=run_id, then insert.
    Returns weeks_written.
    """
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        raise ValueError(f"Ingestion run not found: {run_id}")

    db.query(InventorySnapshotWeekly).filter(
        InventorySnapshotWeekly.source_type == SOH_SOURCE_TYPE,
        InventorySnapshotWeekly.source_run_id == run_id,
    ).delete(synchronize_session=False)

    daily_rows = (
        db.query(InventorySnapshotDaily)
        .filter(
            InventorySnapshotDaily.source_type == SOH_SOURCE_TYPE,
            InventorySnapshotDaily.source_run_id == run_id,
        )
        .all()
    )

    # (week_start, warehouse_code, sku) -> (as_of_date, on_hand_qty) - keep latest as_of_date per week
    by_week: dict[tuple[date, str, str], tuple[date, Decimal]] = {}
    for r in daily_rows:
        as_of = cast(date, r.as_of_date)
        week_start = week_start_for_date(as_of)
        wh = cast(str, r.warehouse_code)
        sku = cast(str, r.sku)
        qty = cast(Decimal, r.on_hand_units)
        key = (week_start, wh, sku)
        if key not in by_week or as_of > by_week[key][0]:
            by_week[key] = (as_of, qty)

    weeks_written = 0
    for (week_start, warehouse_code, sku), (_as_of, on_hand_qty) in by_week.items():
        db.add(
            InventorySnapshotWeekly(
                week_start=week_start,
                sku=sku,
                warehouse_code=warehouse_code,
                on_hand_qty=on_hand_qty,
                source_type=SOH_SOURCE_TYPE,
                source_run_id=run_id,
            )
        )
        weeks_written += 1

    db.flush()
    logger.info("build_weekly_from_daily: run_id=%s weeks_written=%s", run_id, weeks_written)
    return weeks_written
