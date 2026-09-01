"""Stage-1 survival labels with explicit censoring and migration semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class SurvivalStatus(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    RIGHT_CENSORED = "RIGHT_CENSORED"
    MIGRATION_UNKNOWN = "MIGRATION_UNKNOWN"
    PROVIDER_GAP = "PROVIDER_GAP"
    TRUE_UNKNOWN = "TRUE_UNKNOWN"


@dataclass(frozen=True)
class SurvivalLabel:
    status: SurvivalStatus
    decision_ms: int
    window_start_ms: int
    window_end_ms: int
    future_trade_count: int
    migration_before_window_end: bool


def future_trade_label(
    *,
    decision_ms: int,
    window_start_ms: int,
    window_end_ms: int,
    collection_end_ms: int,
    trade_times_ms: Iterable[int],
    migration_times_ms: Iterable[int] = (),
    provider_complete: bool = True,
) -> SurvivalLabel:
    """Label a post-horizon activity window without treating gaps as deaths.

    The positive interval is open at its left edge and closed at its right edge.
    It must begin strictly after the decision timestamp.  Migration without a
    validated continuation tape is explicitly unknown, not inactivity.
    """
    if not window_start_ms > decision_ms:
        raise ValueError("outcome window must begin strictly after decision")
    migration_before_end = any(time_ms <= window_end_ms for time_ms in migration_times_ms)
    future_trades = [time_ms for time_ms in trade_times_ms if window_start_ms < time_ms <= window_end_ms and time_ms > decision_ms]
    if not provider_complete:
        status = SurvivalStatus.PROVIDER_GAP
    elif collection_end_ms < window_end_ms:
        status = SurvivalStatus.RIGHT_CENSORED
    elif migration_before_end:
        status = SurvivalStatus.MIGRATION_UNKNOWN
    elif future_trades:
        status = SurvivalStatus.POSITIVE
    else:
        status = SurvivalStatus.NEGATIVE
    return SurvivalLabel(status, decision_ms, window_start_ms, window_end_ms, len(future_trades), migration_before_end)
