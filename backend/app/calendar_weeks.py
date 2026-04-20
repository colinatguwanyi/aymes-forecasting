"""Calendar week utilities: ISO week start/end dates and ensure calendar_weeks table has rows."""
from __future__ import annotations
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def week_start_end(iso_year: int, iso_week: int) -> tuple[date, date]:
    """Return (week_start_date, week_end_date) for the given ISO year and week (Monday–Sunday)."""
    # Jan 4 is always in ISO week 1
    jan4 = date(iso_year, 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    week_start = week1_monday + timedelta(weeks=iso_week - 1)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def ensure_calendar_week(db: Session, iso_year: int, iso_week: int):
    """Ensure a calendar_weeks row exists for (iso_year, iso_week); create if missing. Return the row."""
    from app.models import CalendarWeek

    row = (
        db.query(CalendarWeek)
        .filter(CalendarWeek.iso_year == iso_year, CalendarWeek.iso_week == iso_week)
        .first()
    )
    if row:
        return row
    start, end = week_start_end(iso_year, iso_week)
    row = CalendarWeek(
        iso_year=iso_year,
        iso_week=iso_week,
        week_start_date=start,
        week_end_date=end,
    )
    db.add(row)
    db.flush()
    return row


def ensure_calendar_weeks_range(db: Session, iso_year_start: int, iso_week_start: int, num_weeks: int) -> None:
    """Ensure calendar_weeks rows exist for a range of weeks (starting at iso_year_start, iso_week_start)."""
    y, w = iso_year_start, iso_week_start
    for _ in range(num_weeks):
        ensure_calendar_week(db, y, w)
        w += 1
        if w > 52:
            w = 1
            y += 1
    db.commit()
