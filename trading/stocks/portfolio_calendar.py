"""Calendar rules for the human-gated portfolio review."""
from __future__ import annotations

from datetime import date, timedelta


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return date(year, month, 1 + offset + (n - 1) * 7)


def default_review_holidays(year: int) -> frozenset[date]:
    """Weekday market closures that should delay the monthly review.

    Includes US Thanksgiving and a small fixed Argentine/US set. Callers can
    pass a different collection into the calendar functions.
    """
    return frozenset(
        {
            date(year, 1, 1),
            date(year, 5, 1),
            date(year, 5, 25),
            date(year, 7, 4),
            date(year, 7, 9),
            _nth_weekday(year, 11, 3, 4),
            date(year, 12, 8),
            date(year, 12, 25),
        }
    )


def next_business_day_for_monthly_review(
    year: int,
    month: int,
    review_day: int = 26,
    holidays: frozenset[date] | set[date] | None = None,
) -> date:
    """Return the funding date, or the next weekday that is not a holiday."""
    if not 1 <= review_day <= 28:
        raise ValueError("review_day must be between 1 and 28")
    skipped = default_review_holidays(year) if holidays is None else holidays
    candidate = date(year, month, review_day)
    while candidate.weekday() >= 5 or candidate in skipped:
        candidate += timedelta(days=1)
    return candidate


def review_is_due(
    today: date,
    *,
    review_day: int = 26,
    holidays: frozenset[date] | set[date] | None = None,
    last_report_date: date | None = None,
) -> bool:
    """True on or after this month's review day until a report exists."""
    scheduled = next_business_day_for_monthly_review(
        today.year, today.month, review_day=review_day, holidays=holidays
    )
    if last_report_date is not None and last_report_date >= scheduled:
        return False
    return today >= scheduled
