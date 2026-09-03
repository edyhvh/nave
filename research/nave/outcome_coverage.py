"""Pure, provider-neutral coverage masks for NAVE historical outcomes.

Coverage is evaluated for each token and horizon.  A missing provider interval
therefore censors only trajectories that cross that interval; it does not
invalidate an entire calendar day.  This module performs no I/O or provider
calls and deliberately keeps unresolved observations distinct from
right-censoring and internal gaps.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping


UTC = timezone.utc
COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
MISSING = "MISSING"
FAILED = "FAILED"
RIGHT_CENSORED = "RIGHT_CENSORED"
INTERNAL_GAP = "INTERNAL_GAP"
UNRESOLVED = "UNRESOLVED"

HORIZON_LABELS = {
    900: "FULL_15M",
    1800: "FULL_30M",
    3600: "FULL_60M",
    14_400: "FULL_4H",
    28_800: "FULL_8H",
    43_200: "FULL_12H",
    86_400: "FULL_24H",
    172_800: "FULL_48H",
    259_200: "FULL_72H",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def required_hour_keys(start: datetime, end: datetime) -> tuple[str, ...]:
    """Return UTC hours touched by the inclusive ``[start, end]`` interval."""
    start = _utc(start)
    end = _utc(end)
    if end < start:
        raise ValueError("end must not precede start")
    cursor = start.replace(minute=0, second=0, microsecond=0)
    final = end.replace(minute=0, second=0, microsecond=0)
    keys: list[str] = []
    while cursor <= final:
        keys.append(cursor.strftime("%Y-%m-%dT%H"))
        cursor += timedelta(hours=1)
    return tuple(keys)


def decision_time_eligible(*, available_at: datetime | None, decision_time: datetime) -> bool:
    """Enforce the frozen point-in-time feature rule."""
    return available_at is not None and _utc(available_at) <= _utc(decision_time)


def token_horizon_status(
    *,
    launch_time: datetime,
    horizon_seconds: int,
    hour_status: Mapping[str, str],
    collection_end: datetime,
    has_horizon_observation: bool,
) -> str:
    """Classify one token/horizon without silently filling missing data.

    ``hour_status`` uses UTC keys produced by :func:`required_hour_keys`.
    Partial/failed/missing hours are internal gaps unless the target is beyond
    collection, in which case the trajectory is right-censored first.
    """
    launch_time = _utc(launch_time)
    collection_end = _utc(collection_end)
    target = launch_time + timedelta(seconds=horizon_seconds)
    if target > collection_end:
        return RIGHT_CENSORED
    for key in required_hour_keys(launch_time, target):
        status = hour_status.get(key)
        if status in {None, MISSING, FAILED, PARTIAL}:
            return INTERNAL_GAP
    if not has_horizon_observation:
        return UNRESOLVED
    return HORIZON_LABELS.get(horizon_seconds, f"FULL_{horizon_seconds}S")


def classify_provider_hours(
    *,
    complete_hours: set[str],
    partial_hours: set[str] | None = None,
) -> dict[str, str]:
    """Build an explicit mask; absent hours remain ``MISSING``."""
    partial_hours = partial_hours or set()
    all_hours = complete_hours | partial_hours
    return {
        hour: (PARTIAL if hour in partial_hours else COMPLETE)
        for hour in sorted(all_hours)
    }


def filter_selected_events(events: list[Mapping[str, object]], selected_mints: set[str]) -> list[dict[str, object]]:
    """Retain only frozen-mint events without changing event values."""
    return [dict(event) for event in events if str(event.get("mint") or "") in selected_mints]
