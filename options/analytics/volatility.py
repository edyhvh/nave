"""Volatility analytics for options and underlyings."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def compute_historical_volatility(close_prices: pd.Series, window: int = 30) -> float:
    """Compute annualized historical volatility from close prices."""
    if close_prices.empty or len(close_prices) < window + 1:
        return float("nan")
    ratio = close_prices / close_prices.shift(1)
    log_returns = ratio.map(np.log).dropna()
    if log_returns.empty:
        return float("nan")
    rolling_std = log_returns.rolling(window=window).std().dropna()
    if rolling_std.empty:
        return float("nan")
    return float(rolling_std.iloc[-1] * math.sqrt(252.0))


def compute_iv_rank_percentile(
    iv_series: pd.Series,
    *,
    lookback: int = 90,
) -> tuple[float, float]:
    """Return IV rank and IV percentile from a recent IV history series."""
    clean = pd.to_numeric(iv_series, errors="coerce").dropna()
    if clean.empty:
        return (float("nan"), float("nan"))

    if len(clean) > lookback:
        clean = clean.iloc[-lookback:]

    current = float(clean.iloc[-1])
    min_iv = float(clean.min())
    max_iv = float(clean.max())

    if math.isclose(max_iv, min_iv):
        iv_rank = 50.0
    else:
        iv_rank = 100.0 * ((current - min_iv) / (max_iv - min_iv))

    iv_percentile = 100.0 * float((clean <= current).mean())
    return (float(iv_rank), float(iv_percentile))


def compute_put_call_skew(
    option_frame: pd.DataFrame,
    *,
    target_moneyness_band: float = 0.05,
    underlying_price: float,
) -> dict[str, Any]:
    """Estimate put/call skew using near-ATM implied vols."""
    if option_frame.empty or underlying_price <= 0:
        return {
            "atm_put_iv": float("nan"),
            "atm_call_iv": float("nan"),
            "skew_diff": float("nan"),
            "skew_ratio": float("nan"),
        }

    frame = option_frame.copy()
    frame["moneyness"] = (
        frame["strike"] - underlying_price) / underlying_price
    atm = frame[frame["moneyness"].abs() <= target_moneyness_band]

    puts = atm[atm["option_type"] == "put"]["implied_volatility"]
    calls = atm[atm["option_type"] == "call"]["implied_volatility"]

    atm_put_iv = float(pd.to_numeric(puts, errors="coerce").dropna(
    ).mean()) if not puts.empty else float("nan")
    atm_call_iv = float(pd.to_numeric(calls, errors="coerce").dropna(
    ).mean()) if not calls.empty else float("nan")

    skew_diff = atm_put_iv - atm_call_iv
    skew_ratio = float("nan")
    if not math.isnan(atm_call_iv) and not math.isclose(atm_call_iv, 0.0):
        skew_ratio = atm_put_iv / atm_call_iv

    return {
        "atm_put_iv": atm_put_iv,
        "atm_call_iv": atm_call_iv,
        "skew_diff": skew_diff,
        "skew_ratio": skew_ratio,
    }
