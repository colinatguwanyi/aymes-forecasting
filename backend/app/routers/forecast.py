"""Forecast API: run baseline forecast, query baseline forecasts, forecast metrics. No planning integration."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BaselineForecastWeekly, ForecastRunMetrics
from app.services.forecasting.baseline import run_baseline_forecast
from app.services.time_bucketing import week_start_for_date

router = APIRouter()


@router.post("/runs")
def create_forecast_run(
    train_end_week_start: date | None = Query(None, description="Last week of training data (week start date)"),
    horizon_weeks: int = Query(52, ge=1, le=104),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run baseline forecast: train up to train_end_week_start, produce horizon_weeks of forecasts."""
    if train_end_week_start is None:
        train_end_week_start = week_start_for_date(date.today())
    rows_written, trained_at = run_baseline_forecast(db, train_end_week_start, horizon_weeks)
    db.commit()
    return {
        "train_end_week_start": train_end_week_start.isoformat(),
        "horizon_weeks": horizon_weeks,
        "rows_written": rows_written,
        "trained_at": trained_at.isoformat(),
    }


@router.get("/baseline")
def get_baseline_forecasts(
    sku: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    from_week: date | None = Query(None),
    to_week: date | None = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List baseline forecasts for comparison (no planning integration)."""
    q = db.query(BaselineForecastWeekly).order_by(
        BaselineForecastWeekly.sku,
        BaselineForecastWeekly.warehouse_code,
        BaselineForecastWeekly.week_start,
    )
    if sku is not None:
        q = q.filter(BaselineForecastWeekly.sku == sku)
    if warehouse_code is not None:
        q = q.filter(BaselineForecastWeekly.warehouse_code == warehouse_code)
    if from_week is not None:
        q = q.filter(BaselineForecastWeekly.week_start >= from_week)
    if to_week is not None:
        q = q.filter(BaselineForecastWeekly.week_start <= to_week)
    rows = q.limit(limit).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        _trained = getattr(r, "trained_at", None)
        out.append({
            "sku": r.sku,
            "warehouse_code": r.warehouse_code,
            "week_start": r.week_start.isoformat(),
            "horizon_week_index": r.horizon_week_index,
            "forecast_qty": float(cast(Decimal, r.forecast_qty)),
            "model_name": r.model_name,
            "model_version": r.model_version,
            "trained_at": _trained.isoformat() if _trained is not None else None,
            "train_window_start": r.train_window_start.isoformat(),
            "train_window_end": r.train_window_end.isoformat(),
        })
    return out


@router.get("/metrics")
def get_forecast_metrics(
    sku: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    model_name: str | None = Query(None),
    train_end_week_start: date | None = Query(None, description="Train end week (YYYY-MM-DD)"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get WAPE and Bias for baseline runs (backtest over last 12 weeks)."""
    q = db.query(ForecastRunMetrics).order_by(
        ForecastRunMetrics.train_end_week_start.desc(),
        ForecastRunMetrics.sku,
        ForecastRunMetrics.warehouse_code,
    )
    if sku is not None:
        q = q.filter(ForecastRunMetrics.sku == sku)
    if warehouse_code is not None:
        q = q.filter(ForecastRunMetrics.warehouse_code == warehouse_code)
    if model_name is not None:
        q = q.filter(ForecastRunMetrics.model_name == model_name)
    if train_end_week_start is not None:
        q = q.filter(ForecastRunMetrics.train_end_week_start == train_end_week_start)
    rows = q.limit(limit).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "model_name": r.model_name,
            "model_version": r.model_version,
            "train_end_week_start": r.train_end_week_start.isoformat(),
            "sku": r.sku,
            "warehouse_code": r.warehouse_code,
            "wape": float(r.wape) if r.wape is not None else None,
            "bias": float(r.bias) if r.bias is not None else None,
        })
    return out
