"""Baseline forecast: seasonal_naive_52 per sku+warehouse.

Forecast week t = actual from same week last year if exists, else rolling mean of last 8 weeks.
week_start in baseline_forecasts_weekly = target week (W-TUE).
Deterministic, no heavy deps.
"""
from __future__ import annotations
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Tuple

from sqlalchemy.orm import Session

from app.models import BaselineForecastWeekly, DemandFactsWeekly, ForecastRunMetrics
from app.services.time_bucketing import week_start_for_date

logger = logging.getLogger(__name__)

MODEL_NAME = "seasonal_naive_52"
MODEL_VERSION = "1.0"
ROLLING_WEEKS = 8
SEASONAL_LAG_WEEKS = 52
BACKTEST_WEEKS = 12


def _series_from_facts(
    db: Session,
    train_window_end: date,
) -> dict[tuple[str, str], list[tuple[date, Decimal]]]:
    """(sku, warehouse_code) -> sorted list of (week_start, total_qty). Total = sum over demand_type."""
    rows = (
        db.query(
            DemandFactsWeekly.sku,
            DemandFactsWeekly.warehouse_code,
            DemandFactsWeekly.week_start,
            DemandFactsWeekly.qty,
        )
        .filter(DemandFactsWeekly.week_start <= train_window_end)
        .all()
    )
    aggregated: dict[tuple[str, str], dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for r in rows:
        aggregated[(r.sku, r.warehouse_code)][r.week_start] += r.qty
    out: dict[tuple[str, str], list[tuple[date, Decimal]]] = {}
    for (sku, wh), week_qty in aggregated.items():
        out[(sku, wh)] = sorted(week_qty.items())
    return out


def _forecast_one_week(
    series: list[tuple[date, Decimal]],
    target_week: date,
    train_end: date,
) -> Decimal:
    """Forecast for target_week: same week last year if in series, else mean of last 8 weeks."""
    by_week = {w: q for w, q in series if w <= train_end}
    if not by_week:
        return Decimal("0")
    # Same week last year (52 weeks before target_week)
    prior_year_week = target_week - timedelta(days=52 * 7)
    if prior_year_week in by_week:
        return by_week[prior_year_week]
    # Rolling mean of last 8 weeks (weeks ending at or before train_end, up to 8)
    sorted_weeks = sorted(by_week.keys(), reverse=True)
    candidates = [w for w in sorted_weeks if w <= train_end][:ROLLING_WEEKS]
    if not candidates:
        return Decimal("0")
    total = sum(by_week[w] for w in candidates)
    return (total / len(candidates)).quantize(Decimal("0.0001"))


def _compute_wape_bias(
    series: list[tuple[date, Decimal]],
    train_end_week_start: date,
    n_weeks: int = BACKTEST_WEEKS,
) -> Tuple[Decimal | None, Decimal | None]:
    """Backtest over last n_weeks (chronological): actual vs forecast (trained up to week-1). Return (WAPE, Bias)."""
    by_week = {w: q for w, q in series if w <= train_end_week_start}
    if len(by_week) < n_weeks:
        return None, None
    # Last n_weeks by date (most recent first, then take last n)
    sorted_weeks = sorted(by_week.keys(), reverse=True)[:n_weeks]
    actuals: list[Decimal] = []
    forecasts: list[Decimal] = []
    for target_week in sorted_weeks:
        actual = by_week[target_week]
        train_end = target_week - timedelta(days=7)
        fc = _forecast_one_week(series, target_week, train_end)
        actuals.append(actual)
        forecasts.append(fc)
    sum_actual = sum(actuals)
    if sum_actual == 0:
        return None, None
    sum_abs_err = sum(abs(a - f) for a, f in zip(actuals, forecasts))
    wape = (sum_abs_err / sum_actual).quantize(Decimal("0.000001"))
    bias = (sum(a - f for a, f in zip(actuals, forecasts)) / len(actuals)).quantize(Decimal("0.0001"))
    return wape, bias


def run_baseline_forecast(
    db: Session,
    train_end_week_start: date,
    horizon_weeks: int = 52,
) -> tuple[int, datetime]:
    """
    Produce baseline_forecasts_weekly rows for each (sku, warehouse_code) in demand_facts_weekly.
    Train window: all data up to train_end_week_start. Horizon: train_end_week_start+1 .. +horizon_weeks.
    Returns (rows_written, trained_at).
    """
    trained_at = datetime.now(timezone.utc)
    series_map = _series_from_facts(db, train_end_week_start)
    rows_written = 0
    for (sku, warehouse_code), series in series_map.items():
        if not series:
            continue
        train_window_start = series[0][0]
        for h in range(1, horizon_weeks + 1):
            target_week = train_end_week_start + timedelta(days=7 * h)
            forecast_qty = _forecast_one_week(series, target_week, train_end_week_start)
            existing = (
                db.query(BaselineForecastWeekly)
                .filter(
                    BaselineForecastWeekly.sku == sku,
                    BaselineForecastWeekly.warehouse_code == warehouse_code,
                    BaselineForecastWeekly.week_start == target_week,
                    BaselineForecastWeekly.model_name == MODEL_NAME,
                    BaselineForecastWeekly.model_version == MODEL_VERSION,
                )
                .first()
            )
            if existing:
                existing.forecast_qty = forecast_qty
                existing.trained_at = trained_at
                existing.train_window_start = train_window_start
                existing.train_window_end = train_end_week_start
                existing.horizon_week_index = h
            else:
                db.add(
                    BaselineForecastWeekly(
                        sku=sku,
                        warehouse_code=warehouse_code,
                        week_start=target_week,
                        horizon_week_index=h,
                        forecast_qty=forecast_qty,
                        model_name=MODEL_NAME,
                        model_version=MODEL_VERSION,
                        trained_at=trained_at,
                        train_window_start=train_window_start,
                        train_window_end=train_end_week_start,
                        metrics_json=None,
                    )
                )
            rows_written += 1
        # Forecast health: WAPE and Bias over last BACKTEST_WEEKS
        wape, bias = _compute_wape_bias(series, train_end_week_start, BACKTEST_WEEKS)
        if wape is not None and bias is not None:
            existing_metric = (
                db.query(ForecastRunMetrics)
                .filter(
                    ForecastRunMetrics.model_name == MODEL_NAME,
                    ForecastRunMetrics.model_version == MODEL_VERSION,
                    ForecastRunMetrics.train_end_week_start == train_end_week_start,
                    ForecastRunMetrics.sku == sku,
                    ForecastRunMetrics.warehouse_code == warehouse_code,
                )
                .first()
            )
            if existing_metric:
                existing_metric.wape = wape
                existing_metric.bias = bias
            else:
                db.add(
                    ForecastRunMetrics(
                        model_name=MODEL_NAME,
                        model_version=MODEL_VERSION,
                        train_end_week_start=train_end_week_start,
                        sku=sku,
                        warehouse_code=warehouse_code,
                        wape=wape,
                        bias=bias,
                    )
                )
    return rows_written, trained_at
