"""Calendar rules for the human-gated portfolio review."""
from __future__ import annotations

from datetime import date, timedelta


def next_business_day_for_monthly_review(year: int, month: int) -> date:
    """Return the 26th, or the next Monday-Friday when it falls on a weekend."""
    candidate = date(year, month, 26)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def review_is_due(today: date) -> bool:
    return today == next_business_day_for_monthly_review(today.year, today.month)
