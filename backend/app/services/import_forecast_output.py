"""
Forecast output ingestion: parse Excel/CSV (Demand forecast example output.xlsx style),
stage into forecast_run_output_stage, validate (aah_product_code -> products.sku via aah_code),
build baseline_forecasts_weekly, publish selected baseline into published_baseline_forecasts_weekly.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.orm import Session

from app.models import (
    BaselineForecastWeekly,
    ForecastRunOutputStage,
    Product,
    PublishedBaselineForecastWeekly,
    Warehouse,
)

logger = logging.getLogger(__name__)

DEFAULT_WAREHOUSE = "AAH"

# Excel column names (strip when reading)
COL_AAH = "AAH_Product_Code"
COL_PRODUCT_NAME = "Product_Name"
COL_INFERENCE_DATE = "Inference_Date"
COL_FORECAST_WEEK = "Forecast_Week"
COL_ACTUAL = "Actual"
COL_INTERPOLATED = "Interpolated_Values"
COL_FORECAST = "Forecast"
COL_MODEL = "Model"
COL_MODEL_DETAILS = "Model_Details"
COL_MAE = "Mean_Absolute_Error"
COL_MAPE = "Mean_Absolute_Percentage_Error"
COL_IS_BEST = "Is_Best_Model"
COL_OUTLIER = "Outlier"
COL_PREDICTED_BEST = "Predicted_Best_Model_Bool"


def _get_cell(row: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = row.get(k)
        if v is not None and (not isinstance(v, str) or v.strip() != ""):
            return v
    return None


def _parse_date(s: Any) -> date | None:
    if s is None:
        return None
    if isinstance(s, date):
        return s
    if isinstance(s, datetime):
        return s.date()
    s = (str(s).strip() if s else "") or ""
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.strptime(s[:10], "%d/%m/%Y").date()
        except ValueError:
            return None


def _parse_decimal(s: Any) -> Decimal | None:
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    try:
        return Decimal(str(s).strip())
    except Exception:
        return None


def _parse_bool(s: Any) -> bool | None:
    if s is None:
        return None
    if isinstance(s, bool):
        return s
    v = str(s).strip().lower()
    if v in ("true", "1", "yes", "y"):
        return True
    if v in ("false", "0", "no", "n", ""):
        return False
    return None


def _parse_int(s: Any) -> int | None:
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    try:
        return int(float(str(s).strip()))
    except Exception:
        return None


def _aah_to_sku_map(db: Session) -> dict[str, str]:
    """Build map aah_code -> sku for products that have aah_code set. First wins if duplicate aah_code."""
    rows = db.query(Product.sku, Product.aah_code).filter(Product.aah_code.isnot(None)).all()
    out: dict[str, str] = {}
    for sku, aah in rows:
        aah = (aah or "").strip()
        if aah and aah not in out:
            out[aah] = cast(str, sku)
    return out


def _ensure_warehouse(db: Session, code: str) -> None:
    """Create warehouse with code if it does not exist."""
    existing = db.query(Warehouse).filter(Warehouse.code == code).first()
    if not existing:
        db.add(Warehouse(code=code, name=code, timezone="Europe/London", active=True))
        db.flush()


def validate_and_stage_row(
    db: Session,
    run_id: Any,
    row: dict[str, Any],
    row_number: int,
    aah_to_sku: dict[str, str],
) -> tuple[bool, str | None]:
    """
    Validate one row and insert into forecast_run_output_stage or return (False, reason).
    Returns (True, None) if staged, (False, reason) if rejected.
    """
    from app.models import IngestionRejection

    aah_raw = _get_cell(row, COL_AAH, "aah_product_code")
    aah = (str(aah_raw).strip() if aah_raw is not None else "") or ""
    if not aah:
        db.add(
            IngestionRejection(
                ingestion_run_id=run_id,
                row_number=row_number,
                raw_payload=dict(row),
                reason="aah_product_code required",
            )
        )
        return False, "aah_product_code required"

    inference_d = _parse_date(_get_cell(row, COL_INFERENCE_DATE, "Inference_Date"))
    if not inference_d:
        db.add(
            IngestionRejection(
                ingestion_run_id=run_id,
                row_number=row_number,
                raw_payload=dict(row),
                reason="inference_date required (Inference_Date)",
            )
        )
        return False, "inference_date required"

    forecast_week_d = _parse_date(_get_cell(row, COL_FORECAST_WEEK, "Forecast_Week"))
    if not forecast_week_d:
        db.add(
            IngestionRejection(
                ingestion_run_id=run_id,
                row_number=row_number,
                raw_payload=dict(row),
                reason="forecast_week required (Forecast_Week)",
            )
        )
        return False, "forecast_week required"

    model_raw = _get_cell(row, COL_MODEL, "Model")
    model = (str(model_raw).strip() if model_raw is not None else "") or ""
    if not model:
        db.add(
            IngestionRejection(
                ingestion_run_id=run_id,
                row_number=row_number,
                raw_payload=dict(row),
                reason="model required (Model)",
            )
        )
        return False, "model required"

    forecast_val = _parse_decimal(_get_cell(row, COL_FORECAST, "Forecast"))
    actual_val = _parse_decimal(_get_cell(row, COL_ACTUAL, "Actual"))
    interp_val = _parse_decimal(_get_cell(row, COL_INTERPOLATED, "Interpolated_Values"))
    if forecast_val is None and actual_val is None and interp_val is None:
        db.add(
            IngestionRejection(
                ingestion_run_id=run_id,
                row_number=row_number,
                raw_payload=dict(row),
                reason="at least one of forecast, actual, interpolated_values required",
            )
        )
        return False, "at least one of forecast, actual, interpolated_values required"

    sku = aah_to_sku.get(aah)
    if not sku:
        db.add(
            IngestionRejection(
                ingestion_run_id=run_id,
                row_number=row_number,
                raw_payload=dict(row),
                reason="unknown_aah_code",
            )
        )
        return False, "unknown_aah_code"

    product_name = _get_cell(row, COL_PRODUCT_NAME, "Product_Name")
    product_name = str(product_name).strip() if product_name is not None else None
    model_details = _get_cell(row, COL_MODEL_DETAILS, "Model_Details")
    model_details = str(model_details).strip() if model_details is not None else None
    mae = _parse_decimal(_get_cell(row, COL_MAE, "Mean_Absolute_Error"))
    mape = _parse_decimal(_get_cell(row, COL_MAPE, "Mean_Absolute_Percentage_Error"))
    is_best = _parse_bool(_get_cell(row, COL_IS_BEST, "Is_Best_Model"))
    outlier = _parse_int(_get_cell(row, COL_OUTLIER, "Outlier"))
    predicted_best = _parse_bool(_get_cell(row, COL_PREDICTED_BEST, "Predicted_Best_Model_Bool"))

    db.add(
        ForecastRunOutputStage(
            ingestion_run_id=run_id,
            aah_product_code=aah,
            product_name=product_name,
            inference_date=inference_d,
            forecast_week=forecast_week_d,
            actual=actual_val,
            interpolated_values=interp_val,
            forecast=forecast_val,
            model=model,
            model_details=model_details,
            mae=mae,
            mape=mape,
            is_best_model=is_best,
            outlier=outlier,
            predicted_best_model_bool=predicted_best,
            raw_json=dict(row),
        )
    )
    return True, None


def build_baseline_from_stage(db: Session, run_id: Any, warehouse_code: str = DEFAULT_WAREHOUSE) -> int:
    """
    For each staged row with forecast not null: upsert baseline_forecasts_weekly.
    Returns count of baseline rows written.
    """
    _ensure_warehouse(db, warehouse_code)
    rows = (
        db.query(ForecastRunOutputStage)
        .filter(
            ForecastRunOutputStage.ingestion_run_id == run_id,
            ForecastRunOutputStage.forecast.isnot(None),
        )
        .all()
    )
    written = 0
    trained_at = datetime.now(timezone.utc)
    for r in rows:
        aah_raw = getattr(r, "aah_product_code", None)
        aah = (aah_raw or "").strip() if aah_raw else ""
        sku = aah_to_sku_from_stage(db, aah)
        if not sku:
            continue
        metrics = {}
        mae_val = getattr(r, "mae", None)
        if mae_val is not None:
            metrics["mae"] = float(cast(Decimal, mae_val))
        mape_val = getattr(r, "mape", None)
        if mape_val is not None:
            metrics["mape"] = float(cast(Decimal, mape_val))
        if getattr(r, "outlier", None) is not None:
            metrics["outlier"] = r.outlier
        md = getattr(r, "model_details", None)
        model_version = (md or "")[:64] if md else "1.0"
        inference_d = cast(date, r.inference_date)
        forecast_week_d = cast(date, r.forecast_week)
        model_name = cast(str, getattr(r, "model", None) or "")
        existing = (
            db.query(BaselineForecastWeekly)
            .filter(
                BaselineForecastWeekly.sku == sku,
                BaselineForecastWeekly.warehouse_code == warehouse_code,
                BaselineForecastWeekly.week_start == forecast_week_d,
                BaselineForecastWeekly.model_name == model_name,
                BaselineForecastWeekly.model_version == model_version,
                BaselineForecastWeekly.train_end_week_start == inference_d,
            )
            .first()
        )
        if existing:
            existing.forecast_qty = cast(Decimal, r.forecast)
            existing.trained_at = trained_at
            existing.train_window_start = inference_d
            existing.train_window_end = inference_d
            existing.metrics_json = metrics or None
        else:
            db.add(
                BaselineForecastWeekly(
                    sku=sku,
                    warehouse_code=warehouse_code,
                    week_start=forecast_week_d,
                    forecast_qty=cast(Decimal, r.forecast),
                    model_name=model_name,
                    model_version=model_version,
                    trained_at=trained_at,
                    train_window_start=inference_d,
                    train_window_end=inference_d,
                    train_end_week_start=inference_d,
                    horizon_week_index=None,
                    metrics_json=metrics or None,
                )
            )
        written += 1
    return written


def aah_to_sku_from_stage(db: Session, aah_code: str) -> str | None:
    """Resolve aah_product_code to products.sku."""
    m = _aah_to_sku_map(db)
    return m.get((aah_code or "").strip())


def _select_best_model_per_sku_wh(
    db: Session, run_id: Any
) -> dict[tuple[str, str, date], tuple[str, str]]:
    """
    For each (sku, warehouse_code, train_end_week_start) in stage, choose one (model_name, model_version).
    Rule: if any row has is_best_model true or predicted_best_model_bool true -> that model;
    else lowest MAE (if present), else lowest MAPE, else Prophet + 'without_outliers' in details.
    Returns (sku, wh, train_end) -> (model_name, model_version).
    """
    rows = (
        db.query(ForecastRunOutputStage)
        .filter(ForecastRunOutputStage.ingestion_run_id == run_id)
        .all()
    )
    aah_to_sku = _aah_to_sku_map(db)
    # Group by (sku, warehouse_code, train_end_week_start)
    groups: dict[tuple[str, str, date], list[ForecastRunOutputStage]] = {}
    def _aah_strip(row: ForecastRunOutputStage) -> str:
        v = getattr(row, "aah_product_code", None)
        return (v or "").strip() if v else ""

    def _mae_float(row: ForecastRunOutputStage) -> float:
        m = getattr(row, "mae", None)
        return float(cast(Decimal, m)) if m is not None else 0.0

    def _mape_float(row: ForecastRunOutputStage) -> float:
        m = getattr(row, "mape", None)
        return float(cast(Decimal, m)) if m is not None else 0.0

    for r in rows:
        sku = aah_to_sku.get(_aah_strip(r))
        if not sku:
            continue
        wh = DEFAULT_WAREHOUSE
        inf_d = cast(date, r.inference_date)
        key = (sku, wh, inf_d)
        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    result: dict[tuple[str, str, date], tuple[str, str]] = {}
    for (sku, wh, train_end), group in groups.items():
        key = (sku, wh, train_end)
        best_row = None
        best_is_flag = [x for x in group if (getattr(x, "is_best_model", None) is True) or (getattr(x, "predicted_best_model_bool", None) is True)]
        if best_is_flag:
            best_row = best_is_flag[0]
        else:
            with_mae = [x for x in group if getattr(x, "mae", None) is not None]
            if with_mae:
                best_row = min(with_mae, key=_mae_float)
            else:
                with_mape = [x for x in group if getattr(x, "mape", None) is not None]
                if with_mape:
                    best_row = min(with_mape, key=_mape_float)
                else:
                    prophet_no_out = [
                        x for x in group
                        if (getattr(x, "model", None) or "") and "Prophet" in (getattr(x, "model", None) or "")
                        and (getattr(x, "model_details", None) or "") and "without_outliers" in (getattr(x, "model_details", None) or "")
                    ]
                    if prophet_no_out:
                        best_row = prophet_no_out[0]
                    else:
                        best_row = group[0] if group else None
        if best_row:
            details = (getattr(best_row, "model_details", None) or "").strip()
            model_version = details[:256] if details else "1.0"
            result[key] = (cast(str, getattr(best_row, "model", None) or ""), model_version)
    return result


def publish_baseline_from_stage(db: Session, run_id: Any, warehouse_code: str = DEFAULT_WAREHOUSE) -> int:
    """
    Build published_baseline_forecasts_weekly for this ingestion run: one row per (sku, warehouse, week_start, train_end_week_start)
    using the selected model per (sku, train_end). Selection rule applied in _select_best_model_per_sku_wh.
    Returns count of published rows written.
    """
    _ensure_warehouse(db, warehouse_code)
    selection = _select_best_model_per_sku_wh(db, run_id)
    if not selection:
        return 0
    # Get all staged rows for this run that have forecast
    rows = (
        db.query(ForecastRunOutputStage)
        .filter(
            ForecastRunOutputStage.ingestion_run_id == run_id,
            ForecastRunOutputStage.forecast.isnot(None),
        )
        .all()
    )
    aah_to_sku = _aah_to_sku_map(db)
    # Build (sku, wh, train_end) -> (model_name, model_version)
    # For each staged row with forecast: if (sku, wh, train_end) matches selection, emit published row
    written = 0
    seen: set[tuple[str, str, date, date]] = set()
    for r in rows:
        aah_raw = getattr(r, "aah_product_code", None)
        sku = aah_to_sku.get((aah_raw or "").strip() if aah_raw else "")
        if not sku:
            continue
        wh = warehouse_code
        inf_d = cast(date, r.inference_date)
        key = (sku, wh, inf_d)
        chosen = selection.get(key)
        if not chosen:
            continue
        model_name, model_version = chosen
        r_model = getattr(r, "model", None) or ""
        if r_model != model_name:
            continue
        r_version = ((getattr(r, "model_details", None) or "").strip() or "1.0")[:256]
        if r_version != model_version:
            continue
        week_d = cast(date, r.forecast_week)
        pub_key = (sku, wh, week_d, inf_d)
        if pub_key in seen:
            continue
        seen.add(pub_key)
        existing = (
            db.query(PublishedBaselineForecastWeekly)
            .filter(
                PublishedBaselineForecastWeekly.sku == sku,
                PublishedBaselineForecastWeekly.warehouse_code == wh,
                PublishedBaselineForecastWeekly.week_start == week_d,
                PublishedBaselineForecastWeekly.train_end_week_start == inf_d,
            )
            .first()
        )
        if existing is not None:
            existing.forecast_qty = cast(Decimal, r.forecast)
            existing.selected_model_name = model_name
            existing.selected_model_version = model_version[:256]
        else:
            db.add(
                PublishedBaselineForecastWeekly(
                    sku=sku,
                    warehouse_code=wh,
                    week_start=week_d,
                    forecast_qty=cast(Decimal, r.forecast),
                    train_end_week_start=inf_d,
                    selected_model_name=model_name,
                    selected_model_version=(model_version or "1.0")[:256],
                )
            )
        written += 1
    return written


def import_from_stage(db: Session, run_id: Any) -> tuple[int, int]:
    """
    Run full pipeline: build_baseline_from_stage then publish_baseline_from_stage.
    Returns (baseline_rows_written, published_rows_written).
    """
    baseline_count = build_baseline_from_stage(db, run_id)
    published_count = publish_baseline_from_stage(db, run_id)
    return baseline_count, published_count
