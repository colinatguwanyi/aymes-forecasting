"""Tests: forecast_metrics WAPE/Bias math, missing actuals excluded, actual=0 excluded from WAPE."""
from datetime import date
from decimal import Decimal

import pytest

from app.services.forecast_metrics import compute_wape_bias_per_key


def test_wape_bias_math_fixed_fixture() -> None:
    """Verify WAPE and Bias formulas with fixed data: 2 weeks, actuals 10 and 20, forecasts 12 and 18."""
    w1 = date(2025, 1, 28)
    w2 = date(2025, 2, 4)
    sku, wh = "SKU-A", "WH1"
    actuals = {(sku, wh): {w1: Decimal("10"), w2: Decimal("20")}}
    forecasts = {(sku, wh): {w1: Decimal("12"), w2: Decimal("18")}}

    result = compute_wape_bias_per_key(actuals, forecasts)

    assert len(result) == 1
    key, wape, bias, n_weeks = result[0]
    assert key == (sku, wh)
    assert n_weeks == 2
    # WAPE = sum(|f-a|)/sum(a) = (2+2)/30 = 4/30
    assert abs(float(wape) - (4 / 30)) < 1e-5
    # Bias = sum(f-a)/sum(a) = (2-2)/30 = 0
    assert abs(float(bias)) < 1e-5


def test_missing_actuals_weeks_excluded() -> None:
    """Weeks with forecast but no actuals are excluded; only weeks with both and actual>0 count."""
    w1 = date(2025, 1, 28)
    w2 = date(2025, 2, 4)
    sku, wh = "SKU-B", "WH1"
    actuals = {(sku, wh): {w1: Decimal("100")}}  # only w1
    forecasts = {(sku, wh): {w1: Decimal("90"), w2: Decimal("50")}}

    result = compute_wape_bias_per_key(actuals, forecasts)

    assert len(result) == 1
    _, wape, bias, n_weeks = result[0]
    assert n_weeks == 1
    assert abs(float(wape) - 0.1) < 1e-5   # |90-100|/100
    assert abs(float(bias) - (-0.1)) < 1e-5  # -10/100


def test_actual_zero_weeks_excluded_from_wape_denominator() -> None:
    """Weeks with actual=0 are excluded from WAPE denominator."""
    w1 = date(2025, 1, 28)
    w2 = date(2025, 2, 4)
    sku, wh = "SKU-C", "WH1"
    actuals = {(sku, wh): {w1: Decimal("0"), w2: Decimal("20")}}
    forecasts = {(sku, wh): {w1: Decimal("5"), w2: Decimal("22")}}

    result = compute_wape_bias_per_key(actuals, forecasts)

    assert len(result) == 1
    _, wape, bias, n_weeks = result[0]
    assert n_weeks == 1
    assert abs(float(wape) - 0.1) < 1e-5   # |22-20|/20
    assert abs(float(bias) - 0.1) < 1e-5   # 2/20


def test_no_actuals_gt_zero_skipped() -> None:
    """SKU/wh with only actual=0 weeks is not scored (no entry in result)."""
    w1 = date(2025, 1, 28)
    sku, wh = "SKU-D", "WH1"
    actuals = {(sku, wh): {w1: Decimal("0")}}
    forecasts = {(sku, wh): {w1: Decimal("10")}}

    result = compute_wape_bias_per_key(actuals, forecasts)

    assert len(result) == 0


def test_forecast_only_key_not_scored() -> None:
    """Key with only forecasts (no actuals) is not in result."""
    w1 = date(2025, 1, 28)
    sku, wh = "SKU-E", "WH1"
    actuals = {}
    forecasts = {(sku, wh): {w1: Decimal("10")}}

    result = compute_wape_bias_per_key(actuals, forecasts)

    assert len(result) == 0
