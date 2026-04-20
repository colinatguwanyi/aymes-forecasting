"""Unit tests: W-TUE week_start_for_date correctness."""
from datetime import date

import pytest

from app.services.time_bucketing import WEEK_START_DAY, week_start_for_date


def test_week_start_tuesday_is_self() -> None:
    """Tuesday returns itself as week_start."""
    tue = date(2025, 2, 4)
    assert tue.weekday() == 1
    assert week_start_for_date(tue) == tue


def test_week_start_monday_returns_previous_tuesday() -> None:
    """Monday returns the previous Tuesday."""
    mon = date(2025, 2, 3)
    assert mon.weekday() == 0
    expected = date(2025, 1, 28)
    assert expected.weekday() == 1
    assert week_start_for_date(mon) == expected


def test_week_start_wednesday_returns_same_week_tuesday() -> None:
    """Wednesday returns the Tuesday of the same week."""
    wed = date(2025, 2, 5)
    assert wed.weekday() == 2
    assert week_start_for_date(wed) == date(2025, 2, 4)


def test_week_start_sunday_returns_previous_tuesday() -> None:
    """Sunday returns the Tuesday of that week (6 days back)."""
    sun = date(2025, 2, 9)
    assert sun.weekday() == 6
    assert week_start_for_date(sun) == date(2025, 2, 4)


def test_week_start_policy_constant() -> None:
    assert WEEK_START_DAY == "TUESDAY"
