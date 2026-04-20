"""Single weekly time bucket policy for the platform.

All weekly tables store week_start as date (the week start date).
Weeks are Tuesday-based (W-TUE) in company timezone.
"""
from datetime import date, timedelta

COMPANY_TIMEZONE = "Europe/London"
WEEK_START_DAY = "TUESDAY"

# Python weekday: Monday=0, Tuesday=1, ..., Sunday=6
_TUESDAY_WEEKDAY = 1


def week_start_for_date(d: date) -> date:
    """Return the W-TUE week_start (London-local) for the given date.

    Week runs Tuesday (inclusive) to Monday (inclusive).
    The input d is treated as a calendar date in the company timezone.
    """
    days_since_tuesday = (d.weekday() - _TUESDAY_WEEKDAY) % 7
    return d - timedelta(days=days_since_tuesday)
