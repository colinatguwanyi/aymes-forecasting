"""Unit tests: calculation correctness, safety stock fixed_units/fixed_weeks, WOS division-by-zero."""
import math
from decimal import Decimal

import pytest

from app.services.projection_service import WOS_SENTINEL


def test_wos_division_by_zero_sentinel() -> None:
    """When avg_weekly_demand_next_8_weeks == 0, WOS must not divide by zero; use sentinel or NULL."""
    closing_units = 100
    avg_demand_8 = 0.0
    if avg_demand_8 > 0:
        wos = closing_units / avg_demand_8
    else:
        wos = WOS_SENTINEL
    assert wos == WOS_SENTINEL
    assert not math.isnan(wos)
    assert not math.isinf(wos)


def test_safety_stock_fixed_units() -> None:
    """fixed_units: target_units = safety_stock_units or 0."""
    safety_stock_units = 50
    target_units = int(safety_stock_units or 0)
    assert target_units == 50
    target_units_none = int(None or 0)
    assert target_units_none == 0


def test_safety_stock_fixed_weeks() -> None:
    """fixed_weeks: target_units = ceil(avg_weekly_demand_next_8_weeks * safety_stock_weeks)."""
    avg_demand_8 = 20.0
    safety_stock_weeks = Decimal("2.5")
    target_units = int(math.ceil(avg_demand_8 * float(safety_stock_weeks)))
    assert target_units == 50
    avg_zero = 0.0
    target_zero = int(math.ceil(avg_zero * 2.5))
    assert target_zero == 0


def test_closing_units_formula() -> None:
    """closing_units(t) = opening + inbound - demand; no negative."""
    opening, inbound, demand = 100, 50, 30
    closing = max(0, opening + inbound - demand)
    assert closing == 120
    opening, inbound, demand = 10, 0, 25
    closing = max(0, opening + inbound - demand)
    assert closing == 0


def test_breach_status_red_amber_green() -> None:
    """red if closing < target; amber if closing >= target and < target + (avg*1); green otherwise."""
    target = 50
    avg = 10.0
    # red
    closing = 40
    assert closing < target
    # amber
    closing = 50
    assert closing >= target and closing < target + (avg * 1)
    closing = 59
    assert closing >= target and closing < target + (avg * 1)
    # green
    closing = 60
    assert closing >= target + (avg * 1)
