"""Forecast API: run baseline forecast, query baseline forecasts, forecast metrics. No planning integration."""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from sqlalchemy import func

from app.database import get_db
from app.models import BaselineForecastWeekly, ForecastRunMetrics, PublishedBaselineForecastWeekly
from app.services.forecasting.baseline import run_baseline_forecast
from app.services.forecast_metrics import compute_metrics
from app.services.time_bucketing import week_start_for_date

router = APIRouter()


class RecomputeMetricsBody(BaseModel):
    model_name: str
    model_version: str
    train_end_week_start: date
    eval_window_weeks: int = 12


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


@router.get("/runs")
def list_forecast_runs(
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List published forecast runs: train_end_week_start, models, and row counts (from published_baseline_forecasts_weekly)."""
    subq = (
        db.query(
            PublishedBaselineForecastWeekly.train_end_week_start,
            PublishedBaselineForecastWeekly.selected_model_name,
            PublishedBaselineForecastWeekly.selected_model_version,
            func.count(PublishedBaselineForecastWeekly.id).label("count"),
        )
        .group_by(
            PublishedBaselineForecastWeekly.train_end_week_start,
            PublishedBaselineForecastWeekly.selected_model_name,
            PublishedBaselineForecastWeekly.selected_model_version,
        )
    ).subquery()
    runs = (
        db.query(
            subq.c.train_end_week_start,
            func.sum(subq.c.count).label("total_rows"),
        )
        .group_by(subq.c.train_end_week_start)
        .order_by(subq.c.train_end_week_start.desc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for train_end, total in runs:
        models_q = (
            db.query(
                PublishedBaselineForecastWeekly.selected_model_name,
                PublishedBaselineForecastWeekly.selected_model_version,
                func.count(PublishedBaselineForecastWeekly.id).label("cnt"),
            )
            .filter(PublishedBaselineForecastWeekly.train_end_week_start == train_end)
            .group_by(
                PublishedBaselineForecastWeekly.selected_model_name,
                PublishedBaselineForecastWeekly.selected_model_version,
            )
            .all()
        )
        out.append({
            "train_end_week_start": train_end.isoformat(),
            "total_rows": total,
            "models": [{"model_name": m, "model_version": v, "count": c} for m, v, c in models_q],
        })
    return out


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


@router.get("/published-baseline")
def get_published_baseline(
    train_end_week_start: date | None = Query(None, description="Which run (inference date)"),
    sku: str | None = Query(None),
    weeks: int = Query(52, ge=1, le=104),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return published baseline series used by planning when demand_source=baseline. Filter by train_end_week_start, sku; limit to N weeks from min week."""
    q = db.query(PublishedBaselineForecastWeekly).order_by(
        PublishedBaselineForecastWeekly.sku,
        PublishedBaselineForecastWeekly.warehouse_code,
        PublishedBaselineForecastWeekly.week_start,
    )
    if train_end_week_start is not None:
        q = q.filter(PublishedBaselineForecastWeekly.train_end_week_start == train_end_week_start)
    if sku is not None:
        q = q.filter(PublishedBaselineForecastWeekly.sku == sku)
    rows = q.all()
    if not rows:
        return []
    min_week = min(cast(date, r.week_start) for r in rows)
    max_week = min_week + timedelta(days=7 * (weeks - 1))
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.week_start > max_week:
            continue
        out.append({
            "sku": r.sku,
            "warehouse_code": r.warehouse_code,
            "week_start": r.week_start.isoformat(),
            "forecast_qty": float(cast(Decimal, r.forecast_qty)),
            "train_end_week_start": r.train_end_week_start.isoformat(),
            "selected_model_name": r.selected_model_name,
            "selected_model_version": r.selected_model_version,
        })
    return out


@router.post("/metrics/recompute")
def recompute_forecast_metrics(
    body: RecomputeMetricsBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Recompute WAPE and Bias for a forecast run; persist to forecast_run_metrics. Eval window: last N weeks before train_end."""
    count_scored, count_missing = compute_metrics(
        db,
        model_name=body.model_name,
        model_version=body.model_version,
        train_end_week_start=body.train_end_week_start,
        eval_window_weeks=body.eval_window_weeks,
    )
    db.commit()
    return {
        "model_name": body.model_name,
        "model_version": body.model_version,
        "train_end_week_start": body.train_end_week_start.isoformat(),
        "eval_window_weeks": body.eval_window_weeks,
        "count_scored": count_scored,
        "count_missing": count_missing,
    }


@router.get("/metrics")
def get_forecast_metrics(
    sku: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    model_name: str | None = Query(None),
    train_end_week_start: date | None = Query(None, description="Train end week (YYYY-MM-DD)"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get WAPE and Bias for forecast runs (eval over weeks with actuals; only actual>0 in WAPE denominator)."""
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
            "eval_weeks": r.eval_weeks,
            "wape": float(cast(Decimal, r.wape)) if r.wape is not None else None,
            "bias": float(cast(Decimal, r.bias)) if r.bias is not None else None,
        })
    return out


@router.get("/metrics/summary")
def get_forecast_metrics_summary(
    model_name: str | None = Query(None),
    train_end_week_start: date | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Aggregate: avg_wape, avg_bias, count_scored, count_missing (rows with null wape)."""
    q = db.query(ForecastRunMetrics)
    if model_name is not None:
        q = q.filter(ForecastRunMetrics.model_name == model_name)
    if train_end_week_start is not None:
        q = q.filter(ForecastRunMetrics.train_end_week_start == train_end_week_start)
    rows = q.all()
    with_wape = [r for r in rows if r.wape is not None]
    count_scored = len(with_wape)
    count_missing = len(rows) - count_scored
    if not with_wape:
        return {
            "avg_wape": None,
            "avg_bias": None,
            "count_scored": 0,
            "count_missing": count_missing,
        }
    avg_wape = sum(float(cast(Decimal, r.wape)) for r in with_wape) / count_scored
    bias_vals = [cast(Decimal, r.bias) for r in with_wape if r.bias is not None]
    avg_bias = sum(float(b) for b in bias_vals) / len(bias_vals) if bias_vals else None
    return {
        "avg_wape": round(avg_wape, 6),
        "avg_bias": round(avg_bias, 6) if avg_bias is not None else None,
        "count_scored": count_scored,
        "count_missing": count_missing,
    }
