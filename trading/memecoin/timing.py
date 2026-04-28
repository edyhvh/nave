"""Entry timing tagger for memecoin candidates."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from trading.memecoin.data_provider import TokenMarket


class EntryTiming(str, Enum):
    EARLY = "EARLY"
    MID = "MID"
    LATE = "LATE"
    EXTENDED = "EXTENDED"



def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None



def classify_entry_timing(
    *,
    market: TokenMarket | None,
    seen_count: int,
    first_seen_at: str | None,
    now: datetime | None = None,
) -> EntryTiming:
    """Classify entry timing from momentum + repeat appearances.

    ``seen_count`` is the trailing-24h appearance count *including* the
    current scan.
    """
    now_dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    first_seen_dt = _parse_iso(first_seen_at)

    m5 = (market.price_change_5m_pct if market else None) or 0.0
    h1 = (market.price_change_1h_pct if market else None) or 0.0

    if m5 >= 80 or h1 >= 250:
        return EntryTiming.EXTENDED

    minutes_since_first = None
    if first_seen_dt is not None:
        minutes_since_first = max(0.0, (now_dt - first_seen_dt).total_seconds() / 60.0)

    if seen_count <= 1:
        if m5 >= 25 or h1 >= 80:
            return EntryTiming.MID
        return EntryTiming.EARLY

    if seen_count == 2:
        if m5 >= 60 or h1 >= 170:
            return EntryTiming.LATE
        return EntryTiming.MID

    if minutes_since_first is not None and minutes_since_first <= 90:
        if m5 >= 60 or h1 >= 170:
            return EntryTiming.LATE
        return EntryTiming.MID

    if m5 <= -15 or h1 <= -30:
        return EntryTiming.LATE

    return EntryTiming.LATE
