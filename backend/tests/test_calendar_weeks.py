"""Unit tests: week creation and lookup (ISO week start/end)."""
from datetime import date

import pytest

from app.calendar_weeks import week_start_end


def test_week_start_end_2025_w01() -> None:
    start, end = week_start_end(2025, 1)
    assert start.weekday() == 0  # Monday
    assert end.weekday() == 6  # Sunday
    assert (end - start).days == 6
    assert start.year == 2024 or start.year == 2025  # W01 can span year
    # ISO 2025-W01: Monday 2024-12-30
    assert start == date(2024, 12, 30)
    assert end == date(2025, 1, 5)


def test_week_start_end_2025_w10() -> None:
    start, end = week_start_end(2025, 10)
    assert start.weekday() == 0
    assert end.weekday() == 6
    assert (end - start).days == 6
    assert start == date(2025, 3, 3)
    assert end == date(2025, 3, 9)


def test_week_start_end_iso_year_week_consistency() -> None:
    start, end = week_start_end(2024, 52)
    assert start.isocalendar().week == 52
    assert end.isocalendar().week == 52
