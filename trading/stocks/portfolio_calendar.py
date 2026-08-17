"""Calendar rules for the human-gated portfolio review."""
from __future__ import annotations

from datetime import date, timedelta


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return date(year, month, 1 + offset + (n - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    return current - timedelta(days=(current.weekday() - weekday) % 7)


def _observed_fixed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _easter_sunday(year: int) -> date:
    """Gregorian Easter date using the Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def default_review_holidays(year: int) -> frozenset[date]:
    """NYSE closures plus the desk's configured Argentine closure dates."""
    holidays = {
        _observed_fixed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed_fixed(date(year, 6, 19)),
        _observed_fixed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed_fixed(date(year, 12, 25)),
        # Local desk closures retained from the original operating policy.
        date(year, 5, 1),
        date(year, 5, 25),
        date(year, 7, 9),
        date(year, 12, 8),
    }
    next_new_year_observed = _observed_fixed(date(year + 1, 1, 1))
    if next_new_year_observed.year == year:
        holidays.add(next_new_year_observed)
    return frozenset(holidays)


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
