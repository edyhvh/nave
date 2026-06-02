from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading.crypto.momentum.config import MomentumConfig
from trading.crypto.momentum.filters import atr


@dataclass(frozen=True)
class StructureAssessment:
    passed: bool
    score: float
    last_highs: list[float]
    last_lows: list[float]


def assess_structure(frame: pd.DataFrame, side: str, config: MomentumConfig) -> StructureAssessment:
    lookback = max(config.structure.lookback_bars, config.structure.swing_bars)
    recent = frame.tail(lookback)
    highs = recent["high"].tail(config.structure.swing_bars).tolist()
    lows = recent["low"].tail(config.structure.swing_bars).tolist()
    if len(highs) < config.structure.swing_bars or len(lows) < config.structure.swing_bars:
        return StructureAssessment(False, 0.0, highs, lows)

    if side == "long":
        passed = highs == sorted(highs) and lows == sorted(lows)
    else:
        passed = highs == sorted(
            highs, reverse=True) and lows == sorted(lows, reverse=True)

    dispersion = (max(highs) - min(lows)) / \
        recent["close"].iloc[-1] if recent["close"].iloc[-1] else 0.0
    score = min(dispersion / 0.06, 1.0)
    if not passed:
        score *= 0.35
    return StructureAssessment(passed, score, [float(value) for value in highs], [float(value) for value in lows])


@dataclass(frozen=True)
class RetestAssessment:
    status: str
    confirmed: bool
    entry_price: float | None
    retest_low: float | None
    retest_high: float | None
    close_above_level: bool


def assess_retest(
    trigger_frame: pd.DataFrame,
    side: str,
    breakout_level: float,
    breakout_index: pd.Timestamp,
    config: MomentumConfig,
    *,
    max_retest_hours: int | None = None,
) -> RetestAssessment:
    post_breakout = trigger_frame.loc[trigger_frame.index >= breakout_index]
    if post_breakout.empty:
        return RetestAssessment("pending", False, None, None, None, False)

    maturation_start = breakout_index + \
        pd.Timedelta(hours=config.breakout.min_retest_hours)
    retest_hours = max_retest_hours if max_retest_hours is not None else config.breakout.max_retest_hours
    freshness_end = breakout_index + pd.Timedelta(hours=retest_hours)
    freshness_window = post_breakout.loc[post_breakout.index <= freshness_end]
    if freshness_window.empty:
        return RetestAssessment("invalid", False, None, None, None, False)

    tolerance = breakout_level * config.breakout.retest_tolerance
    last_close = float(post_breakout["close"].iloc[-1])
    stale = post_breakout.index[-1] > freshness_end

    if side == "long":
        touches = freshness_window.loc[freshness_window["low"]
                                       <= breakout_level + tolerance]
        confirmed_rows = pd.DataFrame()
        if not touches.empty:
            confirmation_window = freshness_window.loc[touches.index[0]:]
            mature_confirmation_window = confirmation_window.loc[
                confirmation_window.index >= maturation_start]
            confirmed_rows = mature_confirmation_window.loc[
                mature_confirmation_window["close"] >= breakout_level]
        confirmed = not confirmed_rows.empty
        close_above_level = last_close >= breakout_level
        status = "confirmed" if confirmed and close_above_level else "pending"
        if last_close < breakout_level - tolerance or (stale and not confirmed):
            status = "invalid"
        entry_price = float(
            confirmed_rows["close"].iloc[0]) if confirmed else None
        return RetestAssessment(
            status,
            confirmed,
            entry_price,
            float(touches["low"].min()) if not touches.empty else None,
            float(freshness_window["high"].max()),
            close_above_level,
        )

    touches = freshness_window.loc[freshness_window["high"]
                                   >= breakout_level - tolerance]
    confirmed_rows = pd.DataFrame()
    if not touches.empty:
        confirmation_window = freshness_window.loc[touches.index[0]:]
        mature_confirmation_window = confirmation_window.loc[
            confirmation_window.index >= maturation_start]
        confirmed_rows = mature_confirmation_window.loc[
            mature_confirmation_window["close"] <= breakout_level]
    confirmed = not confirmed_rows.empty
    close_above_level = last_close <= breakout_level
    status = "confirmed" if confirmed and close_above_level else "pending"
    if last_close > breakout_level + tolerance or (stale and not confirmed):
        status = "invalid"
    entry_price = float(confirmed_rows["close"].iloc[0]) if confirmed else None
    return RetestAssessment(
        status,
        confirmed,
        entry_price,
        float(freshness_window["low"].min()),
        float(touches["high"].max()) if not touches.empty else None,
        close_above_level,
    )


def build_invalidation(
    trigger_frame: pd.DataFrame,
    side: str,
    breakout_level: float,
    retest: RetestAssessment,
    config: MomentumConfig,
) -> float:
    trigger_atr = float(atr(trigger_frame, 14).iloc[-1] or 0.0)
    buffer = trigger_atr * config.execution.stop_atr_buffer
    if side == "long":
        retest_low = retest.retest_low if retest.retest_low is not None else breakout_level
        return float(min(retest_low, breakout_level) - buffer)
    retest_high = retest.retest_high if retest.retest_high is not None else breakout_level
    return float(max(retest_high, breakout_level) + buffer)
