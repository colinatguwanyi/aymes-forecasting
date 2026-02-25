"""Ingestion API: upload CSV, stage, execute weekly transform, list runs."""
from __future__ import annotations
import hashlib
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_admin_or_operator
from app.models import (
    DemandStageWeekly,
    DemandType,
    IngestionEntity,
    IngestionMode,
    IngestionRejection,
    IngestionRun,
    IngestionSourceType,
    IngestionStatus,
)
from app.services.csv_import import read_csv, read_csv_or_xlsx
from app.services.import_forecast_output import import_from_stage as import_forecast_output_from_stage
from app.services.import_forecast_output import validate_and_stage_row as validate_and_stage_forecast_output_row
from app.services.import_forecast_output import _aah_to_sku_map
from app.services.import_product_master import import_from_stage as import_product_master_from_stage, validate_and_stage_row as validate_and_stage_product_master_row
from app.services.sales_out_ingestion import build_demand_from_sales_out, validate_and_stage_sales_out_row
from app.ingestion.soh.adapters.blp_aymes_report import is_blp_aymes_format
from app.services.soh_ingestion import (
    CHUNK_SIZE as SOH_CHUNK_SIZE,
    _branch_to_warehouse_code as soh_branch_to_warehouse_code,
    build_daily_from_stage,
    build_weekly_from_daily,
    stage_blp_soh,
    validate_and_stage_soh_row,
)
from app.services.ingestion_mode import compute_date_range_and_mode
from app.services.time_bucketing import week_start_for_date
from app.services.weekly_series_builder import build_weekly_series_from_stage

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_admin_or_operator)])

ALLOWED_DEMAND_TYPES = {"CUSTOMER", "SAMPLES", "ADJUSTMENT"}


def _parse_week_start(s: str) -> tuple[bool, Any]:
    """Parse YYYY-MM-DD and return (ok, week_start_date as W-TUE)."""
    s = (s or "").strip()
    if not s:
        return False, "Empty date"
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
        week_start = week_start_for_date(d)
        return True, week_start
    except ValueError:
        return False, "Invalid date (use YYYY-MM-DD)"


def _parse_decimal(s: str) -> tuple[bool, Decimal | str]:
    s = (s or "0").strip()
    try:
        return True, Decimal(s)
    except Exception:
        return False, "Invalid number"


def _validate_and_stage_demand(
    db: Session,
    run_id: UUID,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """Validate rows, write valid to demand_stage_weekly, rejections to ingestion_rejections. Return (staged_count, rejected_count)."""
    staged = 0
    for i, row in enumerate(rows, start=2):
        errs: list[str] = []
        week_ok, week_val = _parse_week_start(row.get("week_start", ""))
        if not week_ok:
            errs.append(str(week_val))
        qty_ok, qty_val = _parse_decimal(row.get("qty", ""))
        if not qty_ok:
            errs.append(str(qty_val))
        sku_raw = (row.get("sku") or "").strip()
        wh = (row.get("warehouse_code") or "").strip()
        dt = (row.get("demand_type") or "").strip().upper()
        if not sku_raw:
            errs.append("sku required")
        if not wh:
            errs.append("warehouse_code required")
        if dt not in ALLOWED_DEMAND_TYPES:
            errs.append("demand_type must be CUSTOMER, SAMPLES, or ADJUSTMENT")
        if errs:
            db.add(
                IngestionRejection(
                    ingestion_run_id=run_id,
                    row_number=i,
                    raw_payload=dict(row),
                    reason="; ".join(errs),
                )
            )
            continue
        demand_type_enum = DemandType[dt]
        db.add(
            DemandStageWeekly(
                ingestion_run_id=run_id,
                week_start=week_val,
                sku_raw=sku_raw,
                sku=sku_raw,
                warehouse_code=wh,
                demand_type=demand_type_enum,
                qty=qty_val,
                source="CSV",
            )
        )
        staged += 1
    return staged, len(rows) - staged


def _validate_and_stage_product_master(
    db: Session,
    run_id: UUID,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """Validate each row; stage valid to product_master_stage, reject invalid to ingestion_rejections."""
    staged = 0
    for i, row in enumerate(rows, start=2):
        ok, _ = validate_and_stage_product_master_row(db, run_id, row, i)
        if ok:
            staged += 1
    return staged, len(rows) - staged


def _validate_and_stage_forecast_output(
    db: Session,
    run_id: UUID,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """Validate each row; stage valid to forecast_run_output_stage, reject to ingestion_rejections."""
    aah_to_sku = _aah_to_sku_map(db)
    staged = 0
    for i, row in enumerate(rows, start=2):
        ok, _ = validate_and_stage_forecast_output_row(db, run_id, row, i, aah_to_sku)
        if ok:
            staged += 1
    return staged, len(rows) - staged


def _validate_and_stage_sales_out(
    db: Session,
    run_id: UUID,
    rows: list[dict[str, Any]],
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[int, int]:
    """Validate each row; stage valid to sales_out_stage, reject to ingestion_rejections.
    If date_from/date_to provided, rows outside range are rejected."""
    staged = 0
    for i, row in enumerate(rows, start=2):
        ok, reason = validate_and_stage_sales_out_row(db, run_id, row, i, date_from=date_from, date_to=date_to)
        if ok:
            staged += 1
        else:
            db.add(
                IngestionRejection(
                    ingestion_run_id=run_id,
                    row_number=i,
                    raw_payload=dict(row),
                    reason=reason or "validation failed",
                )
            )
    return staged, len(rows) - staged


def _validate_and_stage_soh(
    db: Session,
    run_id: UUID,
    rows_iter: Any,
    warehouse_code: str | None = None,
) -> tuple[int, int]:
    """Validate and stage SOH rows (chunked). All rows go to stock_on_hand_stage; invalid also to ingestion_rejections. Returns (staged_count, rejected_count).
    When warehouse_code is provided, branch column is ignored and all rows use that warehouse (roll-up by product)."""
    branch_to_wh = soh_branch_to_warehouse_code(db)
    wh_override = (warehouse_code or "").strip() or None
    staged = 0
    rejected = 0
    row_number = 2  # header is row 1
    for chunk in rows_iter:
        for row in chunk:
            ok, reason = validate_and_stage_soh_row(db, run_id, row, row_number, branch_to_wh, warehouse_code_override=wh_override)
            if ok:
                staged += 1
            else:
                rejected += 1
                db.add(
                    IngestionRejection(
                        ingestion_run_id=run_id,
                        row_number=row_number,
                        raw_payload=dict(row),
                        reason=reason or "validation failed",
                    )
                )
            row_number += 1
        db.flush()
    return staged, rejected


def _normalize_entity(value: str) -> IngestionEntity | None:
    """Accept entity names (case-insensitive, underscores or spaces)."""
    v = (value or "").strip().lower().replace(" ", "_")
    if v in ("demand",):
        return IngestionEntity.DEMAND
    if v in ("product_master", "productmaster"):
        return IngestionEntity.PRODUCT_MASTER
    if v in ("forecast_output", "forecastoutput"):
        return IngestionEntity.FORECAST_OUTPUT
    if v in ("sales_out", "salesout"):
        return IngestionEntity.SALES_OUT
    if v in ("stock_on_hand", "stockonhand", "soh"):
        return IngestionEntity.STOCK_ON_HAND
    return None


@router.post("/sales-out/upload")
async def upload_sales_out(
    file: UploadFile = File(..., description="CSV or XLSX file (Sales Out columns)"),
    created_by: str | None = Query(None),
    mode: str | None = Query(None, description="weekly (default) or historical"),
    date_from: str | None = Query(None, description="For historical: YYYY-MM-DD; only include rows on or after this date"),
    date_to: str | None = Query(None, description="For historical: YYYY-MM-DD; only include rows on or before this date"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Accept Sales Out CSV/XLSX; parse and stage; create ingestion run. Call build-weekly on run_id to write demand_actuals.
    For historical mode, use date_from/date_to to limit to e.g. last 24 months."""
    return await upload(
        entity="sales_out",
        file=file,
        created_by=created_by,
        mode=mode,
        date_from=date_from,
        date_to=date_to,
        db=db,
    )


def _check_requires_confirm(run: IngestionRun, action: str) -> None:
    """Raise HTTPException 409 if run requires confirmation and is not confirmed."""
    requires = getattr(run, "requires_confirm", False)
    confirmed_at = getattr(run, "confirmed_at", None)
    if requires and not confirmed_at:
        dmin = getattr(run, "date_min", None)
        dmax = getattr(run, "date_max", None)
        span_days = (dmax - dmin).days if dmin and dmax else 0
        raise HTTPException(
            status_code=409,
            detail={
                "code": "confirmation_required",
                "message": (
                    f"This looks like a historical backfill ({run.row_count} rows, {span_days} days). "
                    "Confirm to proceed."
                ),
                "run_id": str(run.id),
            },
        )


@router.post("/runs/{run_id}/confirm")
def confirm_ingestion_run(
    run_id: UUID,
    confirmed_by: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Confirm a historical backfill run. Required before execute when requires_confirm=true."""
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not getattr(run, "requires_confirm", False):
        return {"run_id": str(run_id), "confirmed": True, "message": "Run did not require confirmation."}
    if getattr(run, "confirmed_at", None):
        return {"run_id": str(run_id), "confirmed": True, "message": "Run already confirmed."}
    run.confirmed_at = datetime.now(timezone.utc)
    run.confirmed_by = confirmed_by
    db.commit()
    return {"run_id": str(run_id), "confirmed": True}


@router.post("/sales-out/{run_id}/build-weekly")
def build_sales_out_weekly(
    run_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Transform staged Sales Out for this run into canonical weekly demand (demand_actuals, W-TUE, AAH)."""
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    _check_requires_confirm(run, "build-weekly")
    if getattr(run, "entity", None) and getattr(run.entity, "value", None) != "sales_out":
        raise HTTPException(status_code=400, detail="Run is not a sales_out run")
    try:
        build_demand_from_sales_out(db, run_id)
        db.commit()
    except Exception as e:
        db.rollback()
        run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
        if run:
            run.status = IngestionStatus.FAILED
            run.error_summary = str(e)
            run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))
    run_after = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    return {
        "run_id": str(run_id),
        "status": run_after.status.value if run_after else "success",
        "rows_staged": run_after.row_count if run_after else 0,
        "weeks_written": run_after.inserted_count if run_after else 0,
        "rows_rejected": run_after.rejected_count if run_after else 0,
    }


@router.post("/stock-on-hand/upload")
async def upload_stock_on_hand(
    file: UploadFile = File(..., description="CSV or XLSX (Stock at, Branch Name, AAH Code, STOCK, ON ORDER) or BLP-AYMES (Code, Balance)"),
    created_by: str | None = Query(None),
    mode: str | None = Query(None, description="weekly (default) or historical"),
    warehouse_code: str | None = Query(None, description="Required for BLP-AYMES format (e.g. BLP)"),
    snapshot_date: str | None = Query(None, description="For BLP-AYMES: YYYY-MM-DD; default today"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Accept SOH CSV/XLSX; parse and stage (chunked). Call execute on run_id to build daily and weekly canonical."""
    return await upload(
        entity="stock_on_hand",
        file=file,
        created_by=created_by,
        mode=mode,
        warehouse_code=warehouse_code,
        snapshot_date=snapshot_date,
        db=db,
    )


@router.post("/stock-on-hand/{run_id}/execute")
def execute_stock_on_hand(
    run_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Transform staged SOH for this run: stage -> daily canonical -> weekly canonical (W-TUE)."""
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    _check_requires_confirm(run, "execute")
    if getattr(run, "entity", None) and getattr(run.entity, "value", None) != "stock_on_hand":
        raise HTTPException(status_code=400, detail="Run is not a stock_on_hand run")
    return execute_run(run_id=run_id, db=db)


@router.post("/forecast-output/upload")
async def upload_forecast_output(
    file: UploadFile = File(..., description="XLSX or CSV file (forecast output format)"),
    created_by: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Accept XLSX/CSV forecast output; parse and stage; create ingestion run. Call execute on run_id to build baseline and publish."""
    return await upload(
        entity="forecast_output",
        file=file,
        created_by=created_by,
        db=db,
    )


def _parse_yyyy_mm_dd(s: str | None) -> date | None:
    """Parse YYYY-MM-DD string to date. Returns None if empty or invalid."""
    if not s or not str(s).strip():
        return None
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@router.post("/upload")
async def upload(
    entity: str = Query(..., description="Entity: demand, product_master, or forecast_output"),
    file: UploadFile = File(..., description="CSV file"),
    created_by: str | None = Query(None),
    mode: str | None = Query(None, description="weekly (default) or historical"),
    warehouse_code: str | None = Query(None, description="For SOH BLP-AYMES format"),
    snapshot_date: str | None = Query(None, description="For SOH BLP-AYMES: YYYY-MM-DD"),
    date_from: str | None = Query(None, description="For Sales Out historical: YYYY-MM-DD; only rows on or after"),
    date_to: str | None = Query(None, description="For Sales Out historical: YYYY-MM-DD; only rows on or before"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Accept CSV and entity type; parse and stage; create ingestion run; return run_id.
    Entities: demand (stage -> demand_stage_weekly), product_master (stage -> product_master_stage).
    Idempotency: if an existing run with same entity+file_sha256 has status=success, returns that run_id
    with duplicate_noop message (no new run created).
    """
    logger.info("ingestion/upload: entity=%r filename=%r", entity, file.filename)
    entity_enum = _normalize_entity(entity)
    if entity_enum not in (IngestionEntity.DEMAND, IngestionEntity.PRODUCT_MASTER, IngestionEntity.FORECAST_OUTPUT, IngestionEntity.SALES_OUT, IngestionEntity.STOCK_ON_HAND):
        detail = f"Entity must be demand, product_master, forecast_output, sales_out, or stock_on_hand (got {entity!r})"
        logger.warning("ingestion/upload 400: %s", detail)
        raise HTTPException(status_code=400, detail=detail)
    content = await file.read()
    if not content:
        detail = "Uploaded file is empty"
        logger.warning("ingestion/upload 400: %s", detail)
        raise HTTPException(status_code=400, detail=detail)
    logger.info("ingestion/upload: read %d bytes", len(content))
    file_sha256 = hashlib.sha256(content).hexdigest()

    try:
        existing = (
            db.query(IngestionRun)
            .filter(
                IngestionRun.entity == entity_enum,
                IngestionRun.file_sha256 == file_sha256,
                IngestionRun.status == IngestionStatus.SUCCESS,
            )
            .order_by(IngestionRun.finished_at.desc())
            .first()
        )
        if existing:
            db.commit()
            return {
                "run_id": str(existing.id),
                "row_count": getattr(existing, "row_count", 0),
                "staged_count": 0,
                "rejected_count": 0,
                "duplicate_noop": True,
                "message": "Same file (entity+sha256) already ingested successfully; returning existing run_id.",
            }

        if entity_enum == IngestionEntity.STOCK_ON_HAND:
            try:
                rows_full = read_csv_or_xlsx(content, file.filename)
            except Exception as e:
                detail = f"Invalid file: {e}"
                logger.warning("ingestion/upload 400: %s", detail, exc_info=True)
                raise HTTPException(status_code=400, detail=detail)
            run = IngestionRun(
                source_type=IngestionSourceType.CSV,
                entity=entity_enum,
                file_name=file.filename or None,
                file_sha256=file_sha256,
                started_at=datetime.now(timezone.utc),
                status=IngestionStatus.PENDING,
                row_count=0,
                created_by=created_by,
            )
            db.add(run)
            db.flush()
            run_id = cast(UUID, run.id)
            headers = list(rows_full[0].keys()) if rows_full else []
            if is_blp_aymes_format(headers):
                wh_code = (warehouse_code or "").strip()
                if not wh_code:
                    fn = (file.filename or "")
                    if "BLP" in fn.upper():
                        wh_code = "BLP"
                if not wh_code:
                    raise HTTPException(
                        status_code=400,
                        detail="warehouse_code required for BLP-AYMES format (Code, Balance columns)",
                    )
                snap_date: date
                if snapshot_date and str(snapshot_date).strip():
                    try:
                        snap_date = datetime.strptime(str(snapshot_date).strip(), "%Y-%m-%d").date()
                    except ValueError:
                        raise HTTPException(status_code=400, detail="snapshot_date must be YYYY-MM-DD")
                else:
                    snap_date = datetime.now(timezone.utc).date()
                staged, rejected, blp_summary = stage_blp_soh(
                    db, run_id, rows_full, wh_code, snap_date
                )
                run.row_count = staged + rejected
                run.progress_meta = blp_summary
            else:
                rows_iter_soh: Any = [
                    rows_full[i : i + SOH_CHUNK_SIZE]
                    for i in range(0, len(rows_full), SOH_CHUNK_SIZE)
                ]
                # AAH format: always roll to AAH; warehouse from form only when override desired
                wh_code = (warehouse_code or "").strip() or None
                staged, rejected = _validate_and_stage_soh(db, run_id, rows_iter_soh, warehouse_code=wh_code)
                run.row_count = staged + rejected
        else:
            try:
                if entity_enum in (IngestionEntity.FORECAST_OUTPUT, IngestionEntity.SALES_OUT):
                    rows = read_csv_or_xlsx(content, file.filename)
                else:
                    rows = read_csv(content)
            except Exception as e:
                detail = f"Invalid CSV: {e}"
                logger.warning("ingestion/upload 400: %s", detail, exc_info=True)
                raise HTTPException(status_code=400, detail=detail)
            run = IngestionRun(
                source_type=IngestionSourceType.CSV,
                entity=entity_enum,
                file_name=file.filename or None,
                file_sha256=file_sha256,
                started_at=datetime.now(timezone.utc),
                status=IngestionStatus.PENDING,
                row_count=len(rows),
                created_by=created_by,
            )
            db.add(run)
            db.flush()
            run_id = cast(UUID, run.id)
            if entity_enum == IngestionEntity.DEMAND:
                staged, rejected = _validate_and_stage_demand(db, run_id, rows)
            elif entity_enum == IngestionEntity.PRODUCT_MASTER:
                staged, rejected = _validate_and_stage_product_master(db, run_id, rows)
            elif entity_enum == IngestionEntity.FORECAST_OUTPUT:
                staged, rejected = _validate_and_stage_forecast_output(db, run_id, rows)
            else:
                df = _parse_yyyy_mm_dd(date_from)
                dt = _parse_yyyy_mm_dd(date_to)
                staged, rejected = _validate_and_stage_sales_out(db, run_id, rows, date_from=df, date_to=dt)

        run.inserted_count = 0
        run.updated_count = 0
        run.rejected_count = rejected
        run.file_size_bytes = len(content)

        # Mode detection for sales_out, stock_on_hand, demand
        if entity_enum in (IngestionEntity.SALES_OUT, IngestionEntity.STOCK_ON_HAND, IngestionEntity.DEMAND):
            _rc = getattr(run, "row_count", None)
            _fb = getattr(run, "file_size_bytes", None)
            row_count_val = int(_rc) if _rc is not None else 0
            file_size_val = int(_fb) if _fb is not None else None
            date_min, date_max, detected_mode, requires_confirm = compute_date_range_and_mode(
                db, run_id, entity_enum, row_count_val, file_size_val
            )
            run.date_min = date_min
            run.date_max = date_max
            if mode and mode.strip().lower() == "historical":
                run.mode = IngestionMode.HISTORICAL
                run.requires_confirm = True
            else:
                run.mode = detected_mode
                run.requires_confirm = requires_confirm

        db.commit()
        out: dict[str, Any] = {
            "run_id": str(run_id),
            "row_count": run.row_count,
            "staged_count": staged,
            "rejected_count": rejected,
        }
        if entity_enum in (IngestionEntity.SALES_OUT, IngestionEntity.STOCK_ON_HAND, IngestionEntity.DEMAND):
            _mode = getattr(run, "mode", None)
            out["mode"] = _mode.value if _mode else "weekly"
            out["requires_confirm"] = getattr(run, "requires_confirm", False)
            dmin = getattr(run, "date_min", None)
            dmax = getattr(run, "date_max", None)
            out["date_min"] = dmin.isoformat() if dmin else None
            out["date_max"] = dmax.isoformat() if dmax else None
            _pm = getattr(run, "progress_meta", None)
            if _pm and isinstance(_pm, dict) and "distinct_skus" in _pm:
                out["import_summary"] = _pm
            if out["requires_confirm"] and dmin and dmax:
                span_days = (dmax - dmin).days
                out["confirm_message"] = (
                    f"This looks like a historical backfill ({run.row_count} rows, {span_days} days). "
                    "Confirm to proceed."
                )
        return out
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception("ingestion/upload 500: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{run_id}/execute")
def execute_run(
    run_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Execute: demand -> build_weekly_series_from_stage; product_master -> import_product_master_from_stage. Synchronous."""
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    _check_requires_confirm(run, "execute")
    entity_val = getattr(run, "entity", None)
    try:
        if entity_val == IngestionEntity.DEMAND:
            build_weekly_series_from_stage(db, run_id)
        elif entity_val == IngestionEntity.PRODUCT_MASTER:
            run.status = IngestionStatus.RUNNING
            run.finished_at = None
            db.flush()
            inserted, updated = import_product_master_from_stage(db, run_id)
            run.inserted_count = inserted
            run.updated_count = updated
            run.status = IngestionStatus.SUCCESS
            run.finished_at = datetime.now(timezone.utc)
        elif entity_val == IngestionEntity.FORECAST_OUTPUT:
            run.status = IngestionStatus.RUNNING
            run.finished_at = None
            db.flush()
            baseline_count, published_count = import_forecast_output_from_stage(db, run_id)
            run.inserted_count = baseline_count
            run.updated_count = published_count
            run.status = IngestionStatus.SUCCESS
            run.finished_at = datetime.now(timezone.utc)
        elif entity_val == IngestionEntity.SALES_OUT:
            run.status = IngestionStatus.RUNNING
            run.finished_at = None
            db.flush()
            _staged, weeks_written, _rejected = build_demand_from_sales_out(db, run_id)
            run.inserted_count = weeks_written
            run.updated_count = 0
            run.status = IngestionStatus.SUCCESS
            run.finished_at = datetime.now(timezone.utc)
        elif entity_val == IngestionEntity.STOCK_ON_HAND:
            run.status = IngestionStatus.RUNNING
            run.finished_at = None
            db.flush()
            build_daily_from_stage(db, run_id)
            weeks_written = build_weekly_from_daily(db, run_id)
            run.inserted_count = weeks_written
            run.updated_count = 0
            run.status = IngestionStatus.SUCCESS
            run.finished_at = datetime.now(timezone.utc)
        else:
            raise HTTPException(status_code=400, detail=f"Execute not supported for entity={getattr(entity_val, 'value', entity_val)}")
        db.commit()
    except Exception as e:
        db.rollback()
        run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
        if run:
            run.status = IngestionStatus.FAILED
            run.error_summary = str(e)
            run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))
    run_after = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run_after:
        raise HTTPException(status_code=500, detail="Run not found after execute")
    entity_val = run_after.entity.value if run_after.entity else None
    table_name = {
        "product_master": "products",
        "demand": "demand_facts_weekly",
        "sales_out": "demand_actuals",
        "stock_on_hand": "inventory_snapshots_weekly",
        "forecast_output": "baseline_forecasts_weekly",
    }.get(str(entity_val) if entity_val else "", "data")
    return {
        "run_id": str(run_id),
        "status": run_after.status.value,
        "entity": entity_val,
        "table": table_name,
        "inserted_count": run_after.inserted_count,
        "updated_count": run_after.updated_count,
        "rejected_count": run_after.rejected_count,
    }


@router.get("/runs")
def list_runs(
    status: IngestionStatus | None = Query(None),
    entity: IngestionEntity | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List ingestion runs with status and metrics."""
    q = db.query(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)
    if status is not None:
        q = q.filter(IngestionRun.status == status)
    if entity is not None:
        q = q.filter(IngestionRun.entity == entity)
    runs = q.all()
    out: list[dict[str, Any]] = []
    for r in runs:
        _started = getattr(r, "started_at", None)
        _finished = getattr(r, "finished_at", None)
        out.append({
            "id": str(r.id),
            "source_type": r.source_type.value,
            "entity": r.entity.value,
            "file_name": r.file_name,
            "file_sha256": r.file_sha256,
            "started_at": _started.isoformat() if _started is not None else None,
            "finished_at": _finished.isoformat() if _finished is not None else None,
            "status": r.status.value,
            "row_count": r.row_count,
            "inserted_count": r.inserted_count,
            "updated_count": r.updated_count,
            "rejected_count": r.rejected_count,
            "error_summary": r.error_summary,
            "created_by": r.created_by,
            "mode": r.mode.value if getattr(r, "mode", None) else None,
            "date_min": d.isoformat() if (d := getattr(r, "date_min", None)) else None,
            "date_max": d2.isoformat() if (d2 := getattr(r, "date_max", None)) else None,
            "requires_confirm": getattr(r, "requires_confirm", False),
            "confirmed_at": ca.isoformat() if (ca := getattr(r, "confirmed_at", None)) else None,
        })
    return out


@router.get("/runs/{run_id}")
def get_run(
    run_id: UUID,
    rejections_limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run details and rejections sample."""
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    rej = (
        db.query(IngestionRejection)
        .filter(IngestionRejection.ingestion_run_id == run_id)
        .limit(rejections_limit)
        .all()
    )
    _started = getattr(run, "started_at", None)
    _finished = getattr(run, "finished_at", None)
    return {
        "id": str(run.id),
        "source_type": run.source_type.value,
        "entity": run.entity.value,
        "file_name": run.file_name,
        "file_sha256": run.file_sha256,
        "started_at": _started.isoformat() if _started is not None else None,
        "finished_at": _finished.isoformat() if _finished is not None else None,
        "status": run.status.value,
        "row_count": run.row_count,
        "inserted_count": run.inserted_count,
        "updated_count": run.updated_count,
        "rejected_count": run.rejected_count,
        "error_summary": run.error_summary,
        "created_by": run.created_by,
        "mode": run.mode.value if getattr(run, "mode", None) else None,
        "date_min": dm.isoformat() if (dm := getattr(run, "date_min", None)) else None,
        "date_max": dx.isoformat() if (dx := getattr(run, "date_max", None)) else None,
        "requires_confirm": getattr(run, "requires_confirm", False),
        "confirmed_at": cax.isoformat() if (cax := getattr(run, "confirmed_at", None)) else None,
        "confirmed_by": getattr(run, "confirmed_by", None),
        "rejections_sample": [
            {"row_number": r.row_number, "reason": r.reason, "raw_payload": r.raw_payload}
            for r in rej
        ],
    }
