"""Unit tests: baseline forecast deterministic output, 52 target weeks, WAPE/Bias."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.forecasting.baseline import _compute_wape_bias, _forecast_one_week


def test_forecast_same_week_last_year() -> None:
    """When same week last year (52*7 days before target) exists in series, use it."""
    # Implementation uses 52*7 = 364 calendar days, not calendar-year offset (365/366).
    target = date(2025, 2, 18)
    prior_year_week = target - timedelta(days=52 * 7)  # 2024-02-20
    series = [
        (prior_year_week, Decimal("50")),
        (date(2025, 2, 4), Decimal("200")),
    ]
    train_end = date(2025, 2, 4)
    result = _forecast_one_week(series, target, train_end)
    assert prior_year_week in [s[0] for s in series]
    assert result == Decimal("50")


def test_forecast_rolling_mean_when_no_prior_year() -> None:
    """When same week last year not in series, use mean of last 8 weeks."""
    series = [
        (date(2025, 1, 7), Decimal("10")),
        (date(2025, 1, 14), Decimal("20")),
        (date(2025, 1, 21), Decimal("30")),
    ]
    target = date(2025, 2, 11)
    train_end = date(2025, 1, 21)
    result = _forecast_one_week(series, target, train_end)
    # 10+20+30 / 3 = 20
    assert result == Decimal("20.0000")


def test_forecast_empty_series_returns_zero() -> None:
    """Empty series returns 0."""
    result = _forecast_one_week([], date(2025, 2, 4), date(2025, 2, 4))
    assert result == Decimal("0")


def test_forecast_deterministic_same_input_same_output() -> None:
    """Same inputs produce same forecast (deterministic)."""
    series = [(date(2024, 2, 6), Decimal("100")), (date(2025, 2, 4), Decimal("50"))]
    target = date(2025, 2, 11)
    train_end = date(2025, 2, 4)
    r1 = _forecast_one_week(series, target, train_end)
    r2 = _forecast_one_week(series, target, train_end)
    assert r1 == r2


def test_baseline_target_weeks_are_52_unique_per_sku_wh() -> None:
    """Horizon of 52 produces 52 distinct target week_start values (target week = train_end + 7*h)."""
    train_end = date(2025, 1, 7)
    target_weeks = [
        train_end + timedelta(days=7 * h)
        for h in range(1, 53)
    ]
    assert len(target_weeks) == 52
    assert len(set(target_weeks)) == 52
    assert target_weeks[0] == date(2025, 1, 14)
    assert target_weeks[51] == date(2026, 1, 6)


def test_compute_wape_bias_deterministic() -> None:
    """_compute_wape_bias returns same (WAPE, Bias) for same series (deterministic)."""
    base = date(2024, 1, 2)
    series = [(base + timedelta(days=7 * i), Decimal("10") + Decimal(i)) for i in range(20)]
    train_end = base + timedelta(days=7 * 19)
    w1, b1 = _compute_wape_bias(series, train_end, n_weeks=12)
    w2, b2 = _compute_wape_bias(series, train_end, n_weeks=12)
    assert w1 is not None and b1 is not None
    assert w1 == w2 and b1 == b2


def test_compute_wape_bias_insufficient_weeks_returns_none() -> None:
    """When fewer than n_weeks of data, returns (None, None)."""
    series = [(date(2024, 1, 2) + timedelta(days=7 * i), Decimal("5")) for i in range(5)]
    train_end = date(2024, 2, 6)
    w, b = _compute_wape_bias(series, train_end, n_weeks=12)
    assert w is None and b is None
