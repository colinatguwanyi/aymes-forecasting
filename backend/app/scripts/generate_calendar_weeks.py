"""Ensure calendar_weeks has at least 5 years past + 5 years future.

Uses existing ISO week semantics (Monday-based) for backbone compatibility.
The W-TUE bucket rule is enforced in app.services.time_bucketing for
demand_facts_weekly and ingestion; this script only populates calendar_weeks.
"""
from __future__ import annotations
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Add backend root so app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.calendar_weeks import ensure_calendar_week, week_start_end
from app.database import SessionLocal
from app.models import CalendarWeek

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

YEARS_PAST = 5
YEARS_FUTURE = 5


def iso_weeks_in_range(start_date: date, end_date: date) -> list[tuple[int, int]]:
    """Return list of (iso_year, iso_week) for every week overlapping [start_date, end_date]."""
    out: list[tuple[int, int]] = []
    d = start_date
    while d <= end_date:
        iso = d.isocalendar()
        out.append((iso.year, iso.week))
        d += timedelta(days=7)
    # Deduplicate preserving order
    seen: set[tuple[int, int]] = set()
    result: list[tuple[int, int]] = []
    for yw in out:
        if yw not in seen:
            seen.add(yw)
            result.append(yw)
    return result


def main() -> None:
    today = date.today()
    start_date = today - timedelta(days=YEARS_PAST * 365)
    end_date = today + timedelta(days=YEARS_FUTURE * 365)
    weeks = iso_weeks_in_range(start_date, end_date)
    db = SessionLocal()
    try:
        added = 0
        for iso_year, iso_week in weeks:
            existing = (
                db.query(CalendarWeek)
                .filter(CalendarWeek.iso_year == iso_year, CalendarWeek.iso_week == iso_week)
                .first()
            )
            if not existing:
                start, end = week_start_end(iso_year, iso_week)
                db.add(
                    CalendarWeek(
                        iso_year=iso_year,
                        iso_week=iso_week,
                        week_start_date=start,
                        week_end_date=end,
                    )
                )
                added += 1
        db.commit()
        logger.info("generate_calendar_weeks: ensured %s weeks, added %s", len(weeks), added)
    finally:
        db.close()


if __name__ == "__main__":
    main()
