from datetime import date

from trading.stocks.portfolio_calendar import (
    default_review_holidays,
    next_business_day_for_monthly_review,
    review_is_due,
)


def test_review_stays_on_the_26th_when_weekday():
    assert next_business_day_for_monthly_review(2026, 8) == date(2026, 8, 26)
    assert review_is_due(date(2026, 8, 26))


def test_review_is_due_on_or_after_until_a_report_exists():
    assert review_is_due(date(2026, 8, 27))
    assert not review_is_due(date(2026, 8, 27), last_report_date=date(2026, 8, 26))


def test_review_moves_saturday_to_monday():
    assert next_business_day_for_monthly_review(2026, 9) == date(2026, 9, 28)
    assert not review_is_due(date(2026, 9, 26))
    assert review_is_due(date(2026, 9, 28))


def test_review_skips_thanksgiving():
    assert date(2026, 11, 26) in default_review_holidays(2026)
    assert next_business_day_for_monthly_review(2026, 11) == date(2026, 11, 27)
    assert not review_is_due(date(2026, 11, 26))
    assert review_is_due(date(2026, 11, 27))
