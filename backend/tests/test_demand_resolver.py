"""Tests: demand composition — include_samples, breakdown_json, override wins."""
from decimal import Decimal

import pytest

from app.services.demand_resolver import build_actuals_breakdown, DEMAND_TYPES


def test_build_actuals_breakdown_include_samples_true() -> None:
    """When include_samples=True, SAMPLES is included in total and in 'included' list."""
    by_type = {"CUSTOMER": 100.0, "SAMPLES": 20.0, "ADJUSTMENT": 5.0}
    total, breakdown = build_actuals_breakdown(by_type, include_samples=True)
    assert total == Decimal("125.0")
    assert "SAMPLES" in breakdown["included"]
    assert breakdown["excluded"] == []
    assert breakdown["CUSTOMER"] == 100.0
    assert breakdown["SAMPLES"] == 20.0
    assert breakdown["ADJUSTMENT"] == 5.0


def test_build_actuals_breakdown_include_samples_false_excludes_samples() -> None:
    """When include_samples=False, SAMPLES excluded from total and in 'excluded' list."""
    by_type = {"CUSTOMER": 100.0, "SAMPLES": 20.0, "ADJUSTMENT": 5.0}
    total, breakdown = build_actuals_breakdown(by_type, include_samples=False)
    assert total == Decimal("105.0")  # CUSTOMER + ADJUSTMENT only
    assert "SAMPLES" in breakdown["excluded"]
    assert "SAMPLES" not in breakdown["included"]
    assert breakdown["CUSTOMER"] == 100.0
    assert breakdown["SAMPLES"] == 20.0
    assert breakdown["ADJUSTMENT"] == 5.0


def test_build_actuals_breakdown_matches_totals() -> None:
    """Breakdown type values sum (for included types) equals returned total."""
    by_type = {"CUSTOMER": 10.5, "SAMPLES": 2.0, "ADJUSTMENT": 0.5}
    total, breakdown = build_actuals_breakdown(by_type, include_samples=True)
    summed = sum(breakdown[t] for t in DEMAND_TYPES if t in breakdown["included"])
    assert abs(float(total) - summed) < 1e-6
    total2, breakdown2 = build_actuals_breakdown(by_type, include_samples=False)
    summed2 = sum(breakdown2[t] for t in DEMAND_TYPES if t in breakdown2["included"])
    assert abs(float(total2) - summed2) < 1e-6


def test_build_actuals_breakdown_empty_types() -> None:
    """Missing types are 0 and excluded when include_samples=False."""
    by_type = {"CUSTOMER": 50.0}
    total, breakdown = build_actuals_breakdown(by_type, include_samples=False)
    assert total == Decimal("50.0")
    assert breakdown["SAMPLES"] == 0.0
    assert breakdown["ADJUSTMENT"] == 0.0
    assert breakdown["excluded"] == ["SAMPLES"]
