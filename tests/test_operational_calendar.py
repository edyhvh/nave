from datetime import date, timedelta

from trading.stocks.operational_calendar import (
    is_shabbat,
    operational_now,
    shabbat_boundaries,
)


def test_shabbat_uses_seasonal_sunset_boundaries() -> None:
    start, end = shabbat_boundaries(date(2026, 8, 21))
    assert start.tzinfo is not None
    assert end > start
    assert start.hour != 18 or start.minute != 30


def test_shabbat_pause_and_resume() -> None:
    start, end = shabbat_boundaries(date(2026, 8, 21))
    assert is_shabbat(start + (end - start) / 2)
    assert operational_now(start - timedelta(minutes=1)) is True
    assert operational_now(end + timedelta(minutes=1)) is True
