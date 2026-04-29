from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading.crypto.momentum.config import MomentumConfig


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError("momentum evaluation requires a non-empty frame")
    normalized = frame.copy()
    normalized.columns = [str(column).lower() for column in normalized.columns]
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(normalized.columns)
    if missing:
        raise ValueError(f"frame missing required columns: {sorted(missing)}")
    if "timestamp" in normalized.columns:
        normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
        normalized = normalized.sort_values("timestamp").set_index("timestamp", drop=True)
    elif not isinstance(normalized.index, pd.DatetimeIndex):
        raise ValueError("frame must use a DatetimeIndex or include a timestamp column")
    normalized.index = pd.to_datetime(normalized.index, utc=True)
    normalized = normalized.sort_index()
    return normalized


def atr(frame: pd.DataFrame, window: int) -> pd.Series:
    prev_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


@dataclass(frozen=True)
class TrendAssessment:
    passed: bool
    score: float
    slope_bps: float
    ema_stack_gap_pct: float


def assess_trend(frame: pd.DataFrame, side: str, config: MomentumConfig) -> TrendAssessment:
    fast = ema(frame["close"], config.trend.ema_fast)
    slow = ema(frame["close"], config.trend.ema_slow)
    if len(fast.dropna()) < 3 or len(slow.dropna()) < 3:
        return TrendAssessment(False, 0.0, 0.0, 0.0)

    last_close = float(frame["close"].iloc[-1])
    fast_last = float(fast.iloc[-1])
    slow_last = float(slow.iloc[-1])
    slope = (fast.iloc[-1] - fast.iloc[-3]) / fast.iloc[-3] * 10000 if fast.iloc[-3] else 0.0
    stack_gap_pct = abs(fast_last - slow_last) / last_close if last_close else 0.0

    if side == "long":
        passed = last_close > fast_last > slow_last and slope >= config.trend.min_slope_bps
    else:
        passed = last_close < fast_last < slow_last and slope <= -config.trend.min_slope_bps

    slope_score = min(abs(slope) / max(config.trend.min_slope_bps, 1.0), 2.0) / 2.0
    stack_score = min(stack_gap_pct / 0.03, 1.0)
    score = (0.6 * slope_score) + (0.4 * stack_score)
    if not passed:
        score *= 0.45
    return TrendAssessment(passed, min(score, 1.0), float(slope), float(stack_gap_pct))


@dataclass(frozen=True)
class VolatilityAssessment:
    passed: bool
    atr_ratio: float
    range_expansion: float
    score: float
    atr_fast: float


def assess_volatility(frame: pd.DataFrame, bar_index: pd.Timestamp, config: MomentumConfig) -> VolatilityAssessment:
    atr_fast = atr(frame, config.volatility.atr_fast)
    atr_slow = atr(frame, config.volatility.atr_slow)
    bar = frame.loc[bar_index]
    avg_range = (frame["high"] - frame["low"]).rolling(20, min_periods=20).mean()
    atr_ratio = float(atr_fast.loc[bar_index] / atr_slow.loc[bar_index]) if atr_slow.loc[bar_index] else 0.0
    range_expansion = float((bar["high"] - bar["low"]) / avg_range.loc[bar_index]) if avg_range.loc[bar_index] else 0.0
    passed = (
        atr_ratio >= config.volatility.min_atr_ratio
        or (
            range_expansion >= config.volatility.min_range_expansion
            and atr_ratio >= config.volatility.expansion_atr_floor
        )
    )
    atr_score = min(atr_ratio / max(config.volatility.min_atr_ratio, 0.01), 1.6) / 1.6
    range_score = min(
        range_expansion / max(config.volatility.min_range_expansion, 0.01),
        1.6,
    ) / 1.6
    score = max(atr_score, range_score)
    if not passed:
        score *= 0.5
    return VolatilityAssessment(
        passed=passed,
        atr_ratio=atr_ratio,
        range_expansion=range_expansion,
        score=min(score, 1.0),
        atr_fast=float(atr_fast.loc[bar_index] or 0.0),
    )


@dataclass(frozen=True)
class BreakoutAssessment:
    detected: bool
    status: str
    breakout_index: pd.Timestamp | None
    breakout_level: float | None
    range_low: float | None
    range_high: float | None
    breakout_close: float | None
    breakout_volume_ratio: float
    near_trigger: bool


def assess_breakout(frame: pd.DataFrame, side: str, config: MomentumConfig) -> BreakoutAssessment:
    lookback = config.breakout.lookback_bars
    recent = config.breakout.recent_breakout_bars
    atr_series = atr(frame, config.volatility.atr_fast)
    volume_mean = frame["volume"].rolling(20, min_periods=20).mean()

    breakout_index: pd.Timestamp | None = None
    breakout_level: float | None = None
    range_low: float | None = None
    range_high: float | None = None
    breakout_close: float | None = None
    breakout_volume_ratio = 0.0

    start = max(lookback, len(frame) - recent)
    for position in range(start, len(frame)):
        window = frame.iloc[position - lookback:position]
        if window.empty:
            continue
        level_high = float(window["high"].max())
        level_low = float(window["low"].min())
        ts = frame.index[position]
        close = float(frame["close"].iloc[position])
        current_atr = float(atr_series.iloc[position] or 0.0)
        buffer = current_atr * config.breakout.buffer_atr
        if side == "long" and close > level_high + buffer:
            breakout_index = ts
            breakout_level = level_high
            range_low = level_low
            range_high = level_high
            breakout_close = close
        if side == "short" and close < level_low - buffer:
            breakout_index = ts
            breakout_level = level_low
            range_low = level_low
            range_high = level_high
            breakout_close = close
        if breakout_index is not None:
            avg_volume = float(volume_mean.iloc[position] or 0.0)
            breakout_volume_ratio = float(frame["volume"].iloc[position] / avg_volume) if avg_volume else 0.0
            break

    if breakout_index is not None:
        return BreakoutAssessment(
            detected=True,
            status="breakout",
            breakout_index=breakout_index,
            breakout_level=breakout_level,
            range_low=range_low,
            range_high=range_high,
            breakout_close=breakout_close,
            breakout_volume_ratio=breakout_volume_ratio,
            near_trigger=False,
        )

    trailing = frame.iloc[-lookback:]
    trailing_atr = float(atr_series.iloc[-1] or 0.0)
    if side == "long":
        distance = float(trailing["high"].max() - frame["close"].iloc[-1])
    else:
        distance = float(frame["close"].iloc[-1] - trailing["low"].min())
    near_trigger = trailing_atr > 0 and distance <= trailing_atr * config.breakout.pending_distance_atr
    return BreakoutAssessment(
        detected=False,
        status="pending" if near_trigger else "absent",
        breakout_index=None,
        breakout_level=float(trailing["high"].max()) if side == "long" else float(trailing["low"].min()),
        range_low=float(trailing["low"].min()),
        range_high=float(trailing["high"].max()),
        breakout_close=None,
        breakout_volume_ratio=0.0,
        near_trigger=near_trigger,
    )


@dataclass(frozen=True)
class ParticipationAssessment:
    passed: bool
    score: float
    volume_ratio: float
    oi_change_pct: float | None
    oi_supported: bool
    funding_rate: float | None
    crowded: bool
    squeeze_risk: bool


def _extract_oi_value(open_interest: pd.DataFrame | pd.Series | None) -> tuple[float | None, float | None]:
    if open_interest is None:
        return None, None
    if isinstance(open_interest, pd.Series):
        series = open_interest.astype(float)
    else:
        normalized = open_interest.copy()
        normalized.columns = [str(column).lower() for column in normalized.columns]
        column = "open_interest" if "open_interest" in normalized.columns else normalized.columns[-1]
        series = normalized[column].astype(float)
    if len(series) < 2:
        return None, None
    latest = float(series.iloc[-1])
    baseline = float(series.iloc[-min(len(series), 20):-1].mean()) if len(series) > 2 else float(series.iloc[0])
    return latest, baseline


def assess_participation(
    breakout: BreakoutAssessment,
    side: str,
    config: MomentumConfig,
    open_interest: pd.DataFrame | pd.Series | None = None,
    funding_rate: float | None = None,
) -> ParticipationAssessment:
    volume_ratio = breakout.breakout_volume_ratio
    latest_oi, baseline_oi = _extract_oi_value(open_interest)
    oi_change_pct = None
    oi_supported = latest_oi is not None and baseline_oi not in (None, 0.0)
    if oi_supported and latest_oi is not None and baseline_oi is not None and baseline_oi != 0:
        oi_change_pct = (latest_oi - baseline_oi) / baseline_oi

    crowded = False
    if funding_rate is not None:
        crowded = (
            side == "long" and funding_rate > config.participation.max_funding_long
        ) or (
            side == "short" and funding_rate < config.participation.min_funding_short
        )

    squeeze_risk = bool(
        funding_rate is not None
        and oi_change_pct is not None
        and abs(funding_rate) >= config.participation.squeeze_abs_funding
        and abs(oi_change_pct) >= config.participation.squeeze_oi_change_pct
    )

    volume_score = min(volume_ratio / max(config.participation.min_volume_ratio, 0.01), 1.4) / 1.4
    if oi_change_pct is None:
        oi_score = 0.6
    else:
        oi_score = min(
            max(oi_change_pct, 0.0) / max(config.participation.min_oi_change_pct, 0.001),
            1.4,
        ) / 1.4
    score = (0.6 * volume_score) + (0.4 * oi_score)
    passed = volume_ratio >= config.participation.min_volume_ratio and not crowded
    if squeeze_risk:
        score *= 0.65
    if not passed:
        score *= 0.35
    return ParticipationAssessment(
        passed=passed,
        score=min(score, 1.0),
        volume_ratio=volume_ratio,
        oi_change_pct=oi_change_pct,
        oi_supported=oi_supported,
        funding_rate=funding_rate,
        crowded=crowded,
        squeeze_risk=squeeze_risk,
    )


def diagnostics_payload(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}