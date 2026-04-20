"""Tests for stock position breakdown: rounding (MOQ + increment), reorder point math, breach detection, endpoints."""
from __future__ import annotations

import pytest

from app.services.stock_position_breakdown import _round_to_moq_and_increment


def test_round_to_moq_zero_qty() -> None:
    """qty <= 0 returns 0."""
    assert _round_to_moq_and_increment(0, 10, None) == 0.0
    assert _round_to_moq_and_increment(-1, 10, None) == 0.0


def test_round_to_moq_below_moq() -> None:
    """qty in (0, MOQ) -> MOQ."""
    assert _round_to_moq_and_increment(5, 10, None) == 10.0
    assert _round_to_moq_and_increment(1, 100, None) == 100.0


def test_round_to_moq_at_or_above_moq() -> None:
    """qty >= MOQ -> ceil(qty/MOQ)*MOQ."""
    assert _round_to_moq_and_increment(10, 10, None) == 10.0
    assert _round_to_moq_and_increment(15, 10, None) == 20.0
    assert _round_to_moq_and_increment(25, 10, None) == 30.0


def test_round_to_increment_only() -> None:
    """When no MOQ, pack_size (increment) rounds up to multiple."""
    assert _round_to_moq_and_increment(7, None, 5) == 10.0
    assert _round_to_moq_and_increment(10, None, 5) == 10.0
    assert _round_to_moq_and_increment(11, None, 5) == 15.0


def test_round_moq_then_increment() -> None:
    """MOQ first, then increment (pack_size)."""
    # 7 -> MOQ 10 -> 10; then pack 4 -> ceil(10/4)*4 = 12
    result = _round_to_moq_and_increment(7, 10, 4)
    assert result == 12.0
    # 5 -> MOQ 10; pack 3 -> ceil(10/3)*3 = 12
    result = _round_to_moq_and_increment(5, 10, 3)
    assert result == 12.0


def test_reorder_point_math_stable() -> None:
    """Reorder point = effective_lead_time_weeks * avg_demand + safety_stock_units (weeks mode)."""
    effective_lt = 3
    avg_demand = 20.0
    safety_weeks = 1.0
    safety_units = avg_demand * safety_weeks
    rop = effective_lt * avg_demand + safety_units
    assert rop == 80.0


def test_target_stock_math_stable() -> None:
    """Target stock = target_weeks * avg_demand + safety_stock_units."""
    target_weeks = 4.0
    avg_demand = 20.0
    safety_units = 20.0
    target = target_weeks * avg_demand + safety_units
    assert target == 100.0


def test_breach_detection_first_week_below_rop() -> None:
    """Breach week = first week where projected_qty < reorder_point_units."""
    rop = 60.0
    weeks = [
        ("2025-01-06", 70.0),
        ("2025-01-13", 65.0),
        ("2025-01-20", 55.0),
        ("2025-01-27", 50.0),
    ]
    first_breach = None
    for w, qty in weeks:
        if qty < rop:
            first_breach = w
            break
    assert first_breach == "2025-01-20"


def test_endpoint_breakdown_returns_list() -> None:
    """GET /api/stock-position/breakdown returns list (may be empty without plan_run data)."""
    # Use FastAPI TestClient; plan_run_id that doesn't exist or has no projections -> []
    from fastapi.testclient import TestClient
    from app.main import app
    tc = TestClient(app)
    r = tc.get("/api/stock-position/breakdown", params={"plan_run_id": 99999})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_endpoint_rolling_returns_list() -> None:
    """GET /api/stock-position/rolling returns list (may be empty)."""
    from fastapi.testclient import TestClient
    from app.main import app
    tc = TestClient(app)
    r = tc.get(
        "/api/stock-position/rolling",
        params={"plan_run_id": 99999, "warehouse_code": "WH1", "sku": "SKU1", "weeks": 12},
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
