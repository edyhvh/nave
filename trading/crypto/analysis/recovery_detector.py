"""N2 regime-transition detector — post-crash recovery classification.

Hypothesis (from N1 post-mortem, 2026-08-25):
    The standard momentum gate (velocity > 1.2 weekly ATRs) and the iter-18
    range-breakout fallback (flat prior range <= 1.5 weekly ATRs) BOTH miss
    gradual post-crash recoveries: those moves have near-zero velocity and a
    3+ ATR wide range (the crash itself made the range wide). N1 confirmed the
    BTC 63k->78k rally (Mar-Apr 2026) fired only at the peak.

    Fix: a structural *regime-transition* classifier that detects the
    crash -> recovery transition on DAILY structure (higher low, reclaimed
    fast EMA, rising fast-EMA slope) WITHOUT requiring velocity or a flat
    range. When it fires it only *arms* a long bias; the standard downstream
    gates (daily confirm, climax cooldown, chase gate, 4H, 1H entry) still
    apply, so a real entry still needs a clean pullback. This is additive:
    it can only create trades the baseline would have stood aside on.

One variable changed: a third weekly bias source consulted only when momentum
and range-breakout both return neutral. Everything downstream is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class RecoveryTransitionConfig:
    # Crash identification
    crash_drawdown_min: float = 0.15     # close must fall >= 15% from a swing high
    crash_lookback: int = 60             # daily bars to search for the crash high
    # Recovery confirmation
    min_recovery_off_low: float = 0.08   # close >= 8% above the crash low
    ema_fast: int = 20
    ema_slow: int = 50
    ema_slope_bars: int = 3              # fast EMA must be rising over N bars
    higher_low_lookback: int = 10        # min low over N bars must exceed crash low


def _ema(frame: pd.DataFrame, span: int) -> pd.Series:
    return frame["close"].astype(float).ewm(span=span, adjust=False).mean()


def _crash_low_and_high(
    daily: pd.DataFrame, cfg: RecoveryTransitionConfig
) -> tuple[float | None, float | None]:
    """Return (crash_low, crash_high) for the most recent qualifying crash.

    A crash is: within ``crash_lookback`` bars, close drew down at least
    ``crash_drawdown_min`` from a local swing high. Returns the crash low
    (lowest low of the down-leg) and the swing high it fell from.
    """
    if len(daily) < cfg.crash_lookback + 1:
        return None, None
    closes = daily["close"].astype(float)
    lows = daily["low"].astype(float)
    highs = daily["high"].astype(float)
    n = len(daily)
    lo = n - cfg.crash_lookback

    # Find the most recent drawdown event (last bar that was >=15% below a
    # prior swing high inside the window). We scan from the present backward.
    crash_low: float | None = None
    crash_high: float | None = None
    for i in range(n - 1, lo, -1):
        c_now = closes.iloc[i]
        # highest close (proxy swing high) before this bar in the window
        prior = closes.iloc[lo:i]
        if prior.empty:
            continue
        hi = float(prior.max())
        if hi > 0 and (hi - c_now) / hi >= cfg.crash_drawdown_min:
            crash_high = hi
            # lowest low from the crash high forward to now
            after = lows.iloc[i:]
            crash_low = float(after.min())
            break
    return crash_low, crash_high


def detect_recovery_transition(
    daily: pd.DataFrame,
    cfg: RecoveryTransitionConfig | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Classify whether daily structure shows a post-crash recovery transition.

    Returns ``("long", diagnostics)`` when the transition is confirmed,
    ``("neutral", None)`` otherwise.
    """
    cfg = cfg or RecoveryTransitionConfig()
    if daily.empty or len(daily) < cfg.ema_slow + cfg.ema_slope_bars + 2:
        return "neutral", None

    crash_low, crash_high = _crash_low_and_high(daily, cfg)
    if crash_low is None or crash_high is None:
        return "neutral", {"reason": "no qualifying crash in window"}

    closes = daily["close"].astype(float)
    lows = daily["low"].astype(float)
    close_now = float(closes.iloc[-1])

    # Recovery magnitude: meaningful recovery off the crash low.
    if crash_low <= 0:
        return "neutral", {"reason": "degenerate crash low"}
    recovery_pct = (close_now - crash_low) / crash_low
    if recovery_pct < cfg.min_recovery_off_low:
        return "neutral", {
            "crash_low": crash_low,
            "recovery_pct": round(recovery_pct, 4),
            "reason": "recovery off low below threshold",
        }

    # Structure: fast EMA rising and price above it.
    ema_fast = _ema(daily, cfg.ema_fast)
    ema_slow = _ema(daily, cfg.ema_slow)
    fast_now = float(ema_fast.iloc[-1])
    fast_prev = float(ema_fast.iloc[-cfg.ema_slope_bars - 1]) if len(ema_fast) > cfg.ema_slope_bars else None
    fast_rising = fast_prev is not None and fast_now > fast_prev
    above_fast = close_now > fast_now
    slow_now = float(ema_slow.iloc[-1])

    # Higher low: most recent low must exceed the crash low (not re-testing).
    recent_low = float(lows.tail(cfg.higher_low_lookback).min())

    if not (above_fast and fast_rising):
        return "neutral", {
            "crash_low": crash_low,
            "recovery_pct": round(recovery_pct, 4),
            "above_fast": above_fast,
            "fast_rising": fast_rising,
            "reason": "fast EMA structure not confirmed",
        }
    if recent_low <= crash_low:
        return "neutral", {
            "crash_low": crash_low,
            "recovery_pct": round(recovery_pct, 4),
            "recent_low": recent_low,
            "reason": "re-testing crash low (no higher low yet)",
        }

    return "long", {
        "crash_low": crash_low,
        "crash_high": crash_high,
        "recovery_pct": round(recovery_pct, 4),
        "above_fast": above_fast,
        "fast_rising": fast_rising,
        "fast_ema": round(fast_now, 2),
        "slow_ema": round(slow_now, 2),
        "recent_low": recent_low,
        "reason": "post-crash recovery transition confirmed",
    }
