"""Argentina market-operation calendar with a seasonal Shabbat pause."""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
LATITUDE = -34.6037
LONGITUDE = -58.3816
# Conservative operational boundary: pause before Friday sunset and resume
# after Saturday sunset. Fixed fallback preserves the user's current rule.
FIXED_START = time(18, 30)
FIXED_END = time(18, 30)


def _sunset_utc(day: date) -> datetime:
    """Approximate sunset using the NOAA solar calculation, no network needed."""
    n = day.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (n - 1)
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    equation = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    zenith = math.radians(90.833)
    cos_hour = (
        math.cos(zenith) / (math.cos(math.radians(LATITUDE)) * math.cos(decl))
        - math.tan(math.radians(LATITUDE)) * math.tan(decl)
    )
    if not -1 < cos_hour < 1:
        raise ValueError("sunset unavailable for date")
    hour_angle = math.degrees(math.acos(cos_hour))
    solar_minutes = 720 - 4 * LONGITUDE + 4 * hour_angle - equation
    # Argentina is UTC-3 year-round.
    return datetime.combine(day, time.min, tzinfo=ZoneInfo("UTC")) + timedelta(
        minutes=solar_minutes
    )


def shabbat_boundaries(day: date) -> tuple[datetime, datetime]:
    """Return Friday-start and Saturday-end boundaries in Argentina time."""
    friday = day - timedelta(days=(day.weekday() - 4) % 7)
    try:
        start = _sunset_utc(friday).astimezone(ARGENTINA_TZ) - timedelta(minutes=18)
        end = _sunset_utc(friday + timedelta(days=1)).astimezone(ARGENTINA_TZ) + timedelta(minutes=42)
        return start, end
    except (ValueError, OverflowError):
        return (
            datetime.combine(friday, FIXED_START, tzinfo=ARGENTINA_TZ),
            datetime.combine(friday + timedelta(days=1), FIXED_END, tzinfo=ARGENTINA_TZ),
        )


def is_shabbat(now: datetime | None = None) -> bool:
    current = (now or datetime.now(ARGENTINA_TZ)).astimezone(ARGENTINA_TZ)
    start, end = shabbat_boundaries(current.date())
    return start <= current < end


def operational_now(now: datetime | None = None) -> bool:
    return not is_shabbat(now)
