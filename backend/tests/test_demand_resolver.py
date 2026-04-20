"""Unit tests: demand resolver freeze anchor and breakdown."""
from datetime import date, timedelta

import pytest

from app.services.demand_resolver import _frozen_mondays_for_plan


def test_frozen_mondays_anchor_plan_start() -> None:
    """Freeze window is anchored to plan_start_week_start (W-TUE); first N weeks yield N Mondays."""
    # Tuesday 2025-02-04 (W-TUE week start)
    plan_start = date(2025, 2, 4)
    mondays = _frozen_mondays_for_plan(plan_start, freeze_weeks=4)
    assert len(mondays) == 4
    # Week 1 Tue 2/4 -> Monday of that week = 2/4 + 6 = 2/10
    assert date(2025, 2, 10) in mondays
    assert date(2025, 2, 17) in mondays
    assert date(2025, 2, 24) in mondays
    assert date(2025, 3, 3) in mondays


def test_frozen_mondays_zero_weeks_empty() -> None:
    """Zero freeze weeks => empty set."""
    plan_start = date(2025, 2, 4)
    mondays = _frozen_mondays_for_plan(plan_start, freeze_weeks=0)
    assert mondays == set()


def test_frozen_mondays_deterministic() -> None:
    """Same inputs => same set (deterministic)."""
    plan_start = date(2025, 1, 7)
    a = _frozen_mondays_for_plan(plan_start, 2)
    b = _frozen_mondays_for_plan(plan_start, 2)
    assert a == b
