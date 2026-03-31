from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


Timeframe = Literal["1h", "4h"]
Bias = Literal["long", "short", "neutral"]


@dataclass(frozen=True)
class StrategyConfig:
    timeframe: Timeframe = "1h"
    atr_period: int = 14
    rsi_period: int = 14
    ema_fast: int = 20
    ema_slow: int = 50
    bb_period: int = 20
    bb_std: float = 2.0
    base_risk_fraction: float = 0.01
    max_leverage_1h: float = 5.0
    max_leverage_4h: float = 3.0
    min_liquidity_pulse: float = -0.5


@dataclass(frozen=True)
class StrategySignal:
    bias: Bias
    confidence: float
    momentum_score: float
    volatility_score: float
    liquidity_score: float
    leverage_suggestion: float
    stop_distance_atr: float
    take_profit_rr: float
    reason: str


def _to_df(data: object) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        df = data.copy()
    elif hasattr(data, "to_df"):
        df = data.to_df().copy()
    else:
        raise TypeError("Expected pandas DataFrame or OpenBB object with to_df().")

    cols = {c.lower(): c for c in df.columns}
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(f"Missing OHLC columns: {missing}")
    return df.rename(columns={cols[k]: k for k in cols})


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_strategy_signal(
    price_data: object,
    liquidity_pulse: float,
    config: StrategyConfig | None = None,
) -> StrategySignal:
    """
    Build a momentum + volatility + liquidity strategy signal.

    Parameters
    ----------
    price_data:
        OHLCV dataframe or OpenBB object with `to_df()`.
    liquidity_pulse:
        Composite liquidity signal (e.g., normalized TGA/RRP/ETF flow pulse).
        Positive means supportive liquidity.
    config:
        Strategy parameters. Defaults tuned for LTF leverage trading (1h/4h).
    """
    cfg = config or StrategyConfig()
    df = _to_df(price_data).dropna().copy()
    if len(df) < max(cfg.ema_slow, cfg.bb_period, cfg.rsi_period, cfg.atr_period) + 2:
        raise ValueError("Not enough candles to compute strategy signal.")

    close = df["close"]
    df["ema_fast"] = close.ewm(span=cfg.ema_fast, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=cfg.ema_slow, adjust=False).mean()
    df["rsi"] = _rsi(close, cfg.rsi_period)
    df["atr"] = _atr(df, cfg.atr_period)

    mid = close.rolling(cfg.bb_period).mean()
    std = close.rolling(cfg.bb_period).std()
    df["bb_upper"] = mid + cfg.bb_std * std
    df["bb_lower"] = mid - cfg.bb_std * std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / mid.replace(0, np.nan)

    row = df.iloc[-1]
    prev = df.iloc[-2]

    trend_up = row["ema_fast"] > row["ema_slow"]
    trend_dn = row["ema_fast"] < row["ema_slow"]
    momentum_raw = (
        (1.0 if trend_up else -1.0 if trend_dn else 0.0)
        + ((row["rsi"] - 50.0) / 25.0)
        + ((row["close"] - prev["close"]) / prev["close"]) * 50.0
    )
    momentum_score = _clamp(momentum_raw / 3.0, -1.0, 1.0)

    atr_pct = row["atr"] / row["close"] if row["close"] else 0.0
    bb_width = float(row["bb_width"]) if np.isfinite(row["bb_width"]) else 0.0
    vol_raw = (atr_pct * 30.0) + (bb_width * 20.0)
    volatility_score = _clamp(vol_raw, 0.0, 1.0)

    liquidity_score = _clamp(liquidity_pulse, -1.0, 1.0)

    combined = (0.5 * momentum_score) + (0.25 * volatility_score) + (0.25 * liquidity_score)
    short_pressure = momentum_score < -0.2 and liquidity_score < 0
    long_pressure = momentum_score > 0.2 and liquidity_score > cfg.min_liquidity_pulse

    if long_pressure and combined > 0.2:
        bias: Bias = "long"
    elif short_pressure and combined < -0.05:
        bias = "short"
    else:
        bias = "neutral"

    confidence = abs(combined)
    max_lev = cfg.max_leverage_1h if cfg.timeframe == "1h" else cfg.max_leverage_4h
    leverage_suggestion = 0.0 if bias == "neutral" else _clamp(max_lev * confidence, 1.0, max_lev)

    stop_distance_atr = 1.2 if cfg.timeframe == "1h" else 1.5
    take_profit_rr = 2.2 if volatility_score > 0.55 else 1.8

    reason = (
        f"Bias={bias}; momentum={momentum_score:.2f}, volatility={volatility_score:.2f}, "
        f"liquidity={liquidity_score:.2f}, combined={combined:.2f}"
    )

    return StrategySignal(
        bias=bias,
        confidence=round(confidence, 4),
        momentum_score=round(momentum_score, 4),
        volatility_score=round(volatility_score, 4),
        liquidity_score=round(liquidity_score, 4),
        leverage_suggestion=round(leverage_suggestion, 2),
        stop_distance_atr=stop_distance_atr,
        take_profit_rr=take_profit_rr,
        reason=reason,
    )
