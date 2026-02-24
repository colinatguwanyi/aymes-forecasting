"""
Forecast health metrics: WAPE and Bias over an eval window.
Canonical actuals: demand_facts_weekly (W-TUE week_start). Only score weeks where actuals exist and actual > 0.
Deterministic and reproducible.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.orm import Session

from app.models import BaselineForecastWeekly, DemandFactsWeekly, ForecastRunMetrics

logger = logging.getLogger(__name__)


def _actuals_by_week_sku_wh(
    db: Session,
    from_week: date,
    to_week: date,
) -> dict[tuple[str, str], dict[date, Decimal]]:
    """(sku, warehouse_code) -> { week_start: total_qty } from demand_facts_weekly (sum over demand_type)."""
    rows = (
        db.query(
            DemandFactsWeekly.sku,
            DemandFactsWeekly.warehouse_code,
            DemandFactsWeekly.week_start,
            DemandFactsWeekly.qty,
        )
        .filter(
            DemandFactsWeekly.week_start >= from_week,
            DemandFactsWeekly.week_start <= to_week,
        )
        .all()
    )
    out: dict[tuple[str, str], dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for r in rows:
        out[(r.sku, r.warehouse_code)][cast(date, r.week_start)] += cast(Decimal, r.qty)
    return dict(out)


def _forecasts_by_week_sku_wh(
    db: Session,
    model_name: str,
    model_version: str,
    train_end_week_start: date,
    from_week: date,
    to_week: date,
) -> dict[tuple[str, str], dict[date, Decimal]]:
    """(sku, warehouse_code) -> { week_start: forecast_qty } from baseline_forecasts_weekly."""
    rows = (
        db.query(
            BaselineForecastWeekly.sku,
            BaselineForecastWeekly.warehouse_code,
            BaselineForecastWeekly.week_start,
            BaselineForecastWeekly.forecast_qty,
        )
        .filter(
            BaselineForecastWeekly.model_name == model_name,
            BaselineForecastWeekly.model_version == model_version,
            BaselineForecastWeekly.train_window_end == train_end_week_start,
            BaselineForecastWeekly.week_start >= from_week,
            BaselineForecastWeekly.week_start <= to_week,
        )
        .all()
    )
    out: dict[tuple[str, str], dict[date, Decimal]] = defaultdict(dict)
    for r in rows:
        out[(r.sku, r.warehouse_code)][cast(date, r.week_start)] = cast(Decimal, r.forecast_qty)
    return dict(out)


def compute_wape_bias_per_key(
    actuals: dict[tuple[str, str], dict[date, Decimal]],
    forecasts: dict[tuple[str, str], dict[date, Decimal]],
) -> list[tuple[tuple[str, str], Decimal, Decimal, int]]:
    """
    Pure function: for each (sku, warehouse_code) with both actuals and forecasts,
    only count weeks where actual > 0. Return [(key, wape, bias, n_weeks), ...].
    WAPE = sum(|f-a|)/sum(a), Bias = sum(f-a)/sum(a).
    """
    keys_with_forecast = set(forecasts.keys())
    keys_with_actuals = set(actuals.keys())
    all_keys = keys_with_forecast | keys_with_actuals
    result: list[tuple[tuple[str, str], Decimal, Decimal, int]] = []
    for (sku, warehouse_code) in all_keys:
        act = actuals.get((sku, warehouse_code), {})
        fc = forecasts.get((sku, warehouse_code), {})
        weeks_with_both = [w for w in act if w in fc and act[w] > 0]
        if not weeks_with_both:
            continue
        sum_actual = sum(act[w] for w in weeks_with_both)
        if sum_actual <= 0:
            continue
        sum_abs_err = sum(abs(fc[w] - act[w]) for w in weeks_with_both)
        sum_err = sum(fc[w] - act[w] for w in weeks_with_both)
        wape = (sum_abs_err / sum_actual).quantize(Decimal("0.000001"))
        bias = (sum_err / sum_actual).quantize(Decimal("0.000001"))
        result.append(((sku, warehouse_code), wape, bias, len(weeks_with_both)))
    return result


def compute_metrics(
    db: Session,
    model_name: str,
    model_version: str,
    train_end_week_start: date,
    eval_window_weeks: int = 12,
) -> tuple[int, int]:
    """
    Compute WAPE and Bias for each (sku, warehouse) that has forecasts and actuals in the eval window.
    Eval window: [train_end_week_start - eval_window_weeks*7, train_end_week_start - 7] (inclusive).
    Only weeks where actuals exist and actual_qty > 0 contribute to WAPE denominator.
    WAPE = sum(|f - a|) / sum(a); Bias (ratio) = sum(f - a) / sum(a).
    Upsert forecast_run_metrics. Returns (count_scored, count_missing).
    """
    from_week = train_end_week_start - timedelta(days=eval_window_weeks * 7)
    to_week = train_end_week_start - timedelta(days=7)
    if to_week < from_week:
        return 0, 0

    actuals = _actuals_by_week_sku_wh(db, from_week, to_week)
    forecasts = _forecasts_by_week_sku_wh(
        db, model_name, model_version, train_end_week_start, from_week, to_week
    )
    scored = compute_wape_bias_per_key(actuals, forecasts)
    keys_scored = {k for k, _w, _b, _n in scored}
    keys_with_forecast = set(forecasts.keys())
    keys_with_actuals = set(actuals.keys())
    all_keys = keys_with_forecast | keys_with_actuals
    count_missing = len(all_keys - keys_scored)
    count_scored = 0

    for (sku, warehouse_code), wape, bias, n_weeks in scored:
        existing = (
            db.query(ForecastRunMetrics)
            .filter(
                ForecastRunMetrics.model_name == model_name,
                ForecastRunMetrics.model_version == model_version,
                ForecastRunMetrics.train_end_week_start == train_end_week_start,
                ForecastRunMetrics.sku == sku,
                ForecastRunMetrics.warehouse_code == warehouse_code,
            )
            .first()
        )
        if existing:
            existing.eval_weeks = n_weeks
            existing.wape = wape
            existing.bias = bias
        else:
            db.add(
                ForecastRunMetrics(
                    model_name=model_name,
                    model_version=model_version,
                    train_end_week_start=train_end_week_start,
                    sku=sku,
                    warehouse_code=warehouse_code,
                    eval_weeks=n_weeks,
                    wape=wape,
                    bias=bias,
                )
            )
        count_scored += 1

    return count_scored, count_missing
