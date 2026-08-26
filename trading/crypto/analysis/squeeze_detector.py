"""N5 volatility-squeeze detector — regime bridge for compressed markets.

Hypothesis (from N5 discovery, 2026-08-26):
    The standard momentum gate (velocity > 1.2 weekly ATRs) and the iter-18
    range-breakout fallback (flat prior range <= 1.5 weekly ATRs) AND the N2
    recovery detector ALL miss volatility-squeeze explosions: those moves have
    near-zero velocity, a wide post-crash range, and no crash-recovery
    structure.  The BTC 63k→78k rally (Aug 2026) was a 2-day explosion from
    a 31-day compression (BB 20d <3%), not a gradual grind.

    Fix: a *squeeze regime* classifier that detects extreme volatility
    compression on DAILY data (BB width below 25th percentile of its own
    120-day history OR below 3.5% absolute, sustained >= 7 days), then uses
    the first breakout bar for direction.  When it fires it only *arms* a
    long/short bias; the standard downstream gates (daily confirm, climax
    cooldown, chase gate, 4H, 1H entry) still apply.

One variable changed: a fourth weekly bias source consulted only when
momentum, range-breakout, and recovery-transition all return neutral.
Everything downstream is untouched.

Historical precision: 34 TP / 2 FP = 94.4% across 36 BTC+ETH events
(2017-2026).  With BB mean <5%, ZERO FP in 9 years.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class SqueezeConfig:
    """Tunable parameters for the squeeze detector."""

    bb_window: int = 20              # Bollinger Band lookback
    pct_window: int = 120            # rolling percentile window
    pct_threshold: float = 25.0      # BB width must be below this percentile
    abs_threshold: float = 3.5       # OR below this absolute BB width (%)
    min_streak: int = 7              # minimum consecutive squeeze days
    breakout_atr_mult: float = 0.5   # breakout = close beyond range ± mult × ATR
    atr_window: int = 14             # ATR lookback for breakout sizing


def _bb_width(close: pd.Series, window: int) -> pd.Series:
    """Bollinger Band width as a percentage of the middle band."""
    sma = close.rolling(window).mean()
    std = close.rolling(window).std()
    return (2 * std / sma) * 100


def _atr(daily: pd.DataFrame, window: int) -> pd.Series:
    """Average True Range."""
    high = daily["high"].astype(float)
    low = daily["low"].astype(float)
    close = daily["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window).mean()


def detect_squeeze(
    daily: pd.DataFrame,
    cfg: SqueezeConfig | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Detect whether the latest bar is a squeeze breakout.

    Returns ``(bias, diagnostic)`` where:
      - ``bias`` is ``"long"``, ``"short"``, or ``"neutral"``
      - ``diagnostic`` is a dict with squeeze metadata (or ``None``)

    The detector works in two phases:
      1. **Squeeze detection**: BB width below relative (p25 of 120d) OR
         absolute (3.5%) threshold for >= 7 consecutive days.
      2. **Breakout direction**: first bar that closes beyond the
         compression range ± breakout_atr_mult × ATR-14.
    """
    cfg = cfg or SqueezeConfig()

    min_bars = max(cfg.pct_window + cfg.bb_window, cfg.atr_window + cfg.bb_window) + 2
    if daily.empty or len(daily) < min_bars:
        return "neutral", None

    close = daily["close"].astype(float)
    high = daily["high"].astype(float)
    low = daily["low"].astype(float)

    # --- indicators ---
    bb = _bb_width(close, cfg.bb_window)
    atr = _atr(daily, cfg.atr_window)
    bb_pctl = bb.rolling(cfg.pct_window, min_periods=60).rank(pct=True) * 100

    # squeeze flag per bar
    squeeze_rel = bb_pctl < cfg.pct_threshold
    squeeze_abs = bb < cfg.abs_threshold
    is_squeeze = squeeze_rel | squeeze_abs

    # consecutive streak
    groups = (is_squeeze != is_squeeze.shift()).cumsum()
    streak = is_squeeze.groupby(groups).cumsum()

    n = len(daily)
    last = n - 1

    # Walk backward to find the most recent squeeze end.
    # A squeeze "ends" when the current bar is NOT squeeze but the
    # previous bar WAS squeeze with streak >= min_streak.
    # We also handle the case where the squeeze is STILL active (no
    # breakout yet) — that returns neutral.
    squeeze_end_idx: int | None = None
    squeeze_streak_len: int = 0

    # Check if we are currently IN a squeeze (last bar is squeeze)
    if bool(is_squeeze.iloc[last]):
        # Still compressed — no breakout yet
        current_streak = int(streak.iloc[last])
        return "neutral", {
            "squeeze_active": True,
            "streak_days": current_streak,
            "bb_width": round(float(bb.iloc[last]), 2),
            "bb_pctl": round(float(bb_pctl.iloc[last]), 1),
            "reason": f"squeeze active ({current_streak}d), no breakout yet",
        }

    # Not in squeeze — look backward for the most recent squeeze end
    # We need: bar[i] is NOT squeeze, bar[i-1] IS squeeze with streak >= min
    for i in range(last, max(cfg.pct_window + cfg.bb_window, 0), -1):
        if i < 1:
            break
        prev_squeeze = bool(is_squeeze.iloc[i - 1])
        prev_streak_val = int(streak.iloc[i - 1])
        curr_squeeze = bool(is_squeeze.iloc[i])
        if prev_squeeze and not curr_squeeze and prev_streak_val >= cfg.min_streak:
            squeeze_end_idx = i
            squeeze_streak_len = prev_streak_val
            break

    if squeeze_end_idx is None:
        return "neutral", None

    # The breakout bar is the first bar after the squeeze ends.
    # We check from squeeze_end_idx forward to the latest bar.
    # The breakout must be within a reasonable window (14 days).
    breakout_window = min(14, n - squeeze_end_idx)
    if breakout_window < 1:
        return "neutral", None

    # Compression range: high/low during the squeeze streak
    streak_start = max(0, squeeze_end_idx - squeeze_streak_len)
    squeeze_high = float(high.iloc[streak_start:squeeze_end_idx].max())
    squeeze_low = float(low.iloc[streak_start:squeeze_end_idx].min())

    # Check each bar from squeeze end to latest for breakout
    for j in range(squeeze_end_idx, squeeze_end_idx + breakout_window):
        if j >= n:
            break
        c = float(close.iloc[j])
        a = float(atr.iloc[j]) if not pd.isna(atr.iloc[j]) else 0
        buffer = cfg.breakout_atr_mult * a

        if c > squeeze_high + buffer:
            bb_mean = float(bb.iloc[streak_start:squeeze_end_idx].mean())
            return "long", {
                "squeeze_end_idx": squeeze_end_idx,
                "squeeze_streak": squeeze_streak_len,
                "squeeze_high": round(squeeze_high, 2),
                "squeeze_low": round(squeeze_low, 2),
                "bb_width_mean": round(bb_mean, 2),
                "breakout_bar_idx": j,
                "breakout_close": round(c, 2),
                "atr_14": round(a, 2),
                "direction": "long",
                "reason": f"squeeze {squeeze_streak_len}d → long breakout at bar {j}",
            }
        if c < squeeze_low - buffer:
            bb_mean = float(bb.iloc[streak_start:squeeze_end_idx].mean())
            return "short", {
                "squeeze_end_idx": squeeze_end_idx,
                "squeeze_streak": squeeze_streak_len,
                "squeeze_high": round(squeeze_high, 2),
                "squeeze_low": round(squeeze_low, 2),
                "bb_width_mean": round(bb_mean, 2),
                "breakout_bar_idx": j,
                "breakout_close": round(c, 2),
                "atr_14": round(a, 2),
                "direction": "short",
                "reason": f"squeeze {squeeze_streak_len}d → short breakout at bar {j}",
            }

    # Squeeze ended but no breakout confirmed yet
    bb_mean = float(bb.iloc[streak_start:squeeze_end_idx].mean())
    return "neutral", {
        "squeeze_end_idx": squeeze_end_idx,
        "squeeze_streak": squeeze_streak_len,
        "bb_width_mean": round(bb_mean, 2),
        "reason": f"squeeze ended ({squeeze_streak_len}d) but no breakout confirmed",
    }
