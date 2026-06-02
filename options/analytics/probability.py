"""Payoff and probability helpers for options strategies."""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm

from options.models import StrategyCandidate


def expected_move_one_std(
    underlying_price: float,
    implied_volatility: float,
    days_to_expiration: int,
) -> float:
    """Return a one-standard-deviation expected move for the target horizon."""
    t = max(1, days_to_expiration) / 365.0
    sigma = max(0.001, implied_volatility)
    return float(underlying_price * sigma * math.sqrt(t))


def terminal_price_distribution(
    underlying_price: float,
    implied_volatility: float,
    days_to_expiration: int,
    *,
    risk_free_rate: float = 0.04,
    equity_risk_premium: float = 0.03,
    points: int = 801,
    z_max: float = 4.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Build a lognormal terminal price grid with normalized probability weights."""
    t = max(1, days_to_expiration) / 365.0
    sigma = max(0.001, implied_volatility)
    vol_horizon = sigma * math.sqrt(t)
    drift_rate = risk_free_rate + equity_risk_premium
    drift = (drift_rate - 0.5 * sigma * sigma) * t

    z = np.linspace(-z_max, z_max, max(51, points), dtype=float)
    prices = underlying_price * np.exp(drift + vol_horizon * z)
    weights = norm.pdf(z)
    weight_sum = float(weights.sum())
    if weight_sum <= 0:
        return prices, np.ones_like(prices) / len(prices)
    return prices, weights / weight_sum


def strategy_pnl_profile(
    candidate: StrategyCandidate,
    prices: np.ndarray,
) -> np.ndarray:
    """Compute strategy P/L at expiration across a price grid."""
    pnl = np.zeros_like(prices, dtype=float)
    for leg in candidate.legs:
        side_mult = 1.0 if leg.side == "buy" else -1.0
        if leg.instrument_type == "stock":
            multiplier = float(leg.quantity)
            pnl += side_mult * (prices - float(leg.premium)) * multiplier
            continue

        strike = float(leg.strike or 0.0)
        if leg.option_type == "call":
            intrinsic = np.maximum(0.0, prices - strike)
        else:
            intrinsic = np.maximum(0.0, strike - prices)
        multiplier = float(leg.quantity) * 100.0
        pnl += side_mult * (intrinsic - float(leg.premium)) * multiplier

    return pnl


def _interpolate_zero_crossing(p0: float, p1: float, v0: float, v1: float) -> float:
    denom = v1 - v0
    if math.isclose(denom, 0.0):
        return p0
    alpha = -v0 / denom
    alpha = max(0.0, min(1.0, alpha))
    return float(p0 + alpha * (p1 - p0))


def profit_ranges(prices: np.ndarray, pnl: np.ndarray) -> list[tuple[float, float]]:
    """Return contiguous terminal-price ranges where strategy P/L is positive."""
    if len(prices) == 0 or len(pnl) == 0 or len(prices) != len(pnl):
        return []

    profitable = pnl > 0.0
    if not np.any(profitable):
        return []

    ranges: list[tuple[float, float]] = []
    start: float | None = float(prices[0]) if profitable[0] else None

    for idx in range(1, len(prices)):
        was_profitable = bool(profitable[idx - 1])
        is_profitable = bool(profitable[idx])

        if not was_profitable and is_profitable:
            start = _interpolate_zero_crossing(
                float(prices[idx - 1]),
                float(prices[idx]),
                float(pnl[idx - 1]),
                float(pnl[idx]),
            )
        elif was_profitable and not is_profitable and start is not None:
            end = _interpolate_zero_crossing(
                float(prices[idx - 1]),
                float(prices[idx]),
                float(pnl[idx - 1]),
                float(pnl[idx]),
            )
            ranges.append((start, end))
            start = None

    if profitable[-1] and start is not None:
        ranges.append((start, float(prices[-1])))

    return ranges


def probability_of_touch(
    underlying_price: float,
    barrier_price: float,
    implied_volatility: float,
    days_to_expiration: int,
) -> float:
    """Approximate one-barrier touch probability from terminal distribution tails."""
    if underlying_price <= 0 or barrier_price <= 0:
        return 0.0
    if math.isclose(barrier_price, underlying_price):
        return 1.0

    t = max(1, days_to_expiration) / 365.0
    sigma = max(0.001, implied_volatility)
    vol_horizon = sigma * math.sqrt(t)

    z = (math.log(barrier_price / underlying_price) +
         0.5 * vol_horizon * vol_horizon) / vol_horizon
    if barrier_price > underlying_price:
        terminal_tail = 1.0 - float(norm.cdf(z))
    else:
        terminal_tail = float(norm.cdf(z))

    return float(max(0.0, min(1.0, 2.0 * terminal_tail)))


def evaluate_strategy_distribution(
    candidate: StrategyCandidate,
    *,
    underlying_price: float,
    implied_volatility: float,
    risk_free_rate: float = 0.04,
    equity_risk_premium: float = 0.03,
) -> dict[str, float]:
    """Compute POP/EV/profit ranges by integrating over a terminal-price distribution."""
    prices, weights = terminal_price_distribution(
        underlying_price,
        implied_volatility,
        candidate.days_to_expiration,
        risk_free_rate=risk_free_rate,
        equity_risk_premium=equity_risk_premium,
    )
    pnl = strategy_pnl_profile(candidate, prices)
    profitable = pnl > 0.0

    pop_prob = float(weights[profitable].sum()) if np.any(profitable) else 0.0
    expected_value = float(np.dot(weights, pnl))

    expected_profit = 0.0
    expected_loss = 0.0
    if np.any(profitable):
        win_weights = weights[profitable]
        expected_profit = float(
            np.dot(win_weights, pnl[profitable]) / win_weights.sum())
    if np.any(~profitable):
        loss_weights = weights[~profitable]
        avg_loss = float(
            np.dot(loss_weights, pnl[~profitable]) / loss_weights.sum())
        expected_loss = abs(avg_loss)

    ranges = profit_ranges(prices, pnl)
    range_low = float(ranges[0][0]) if ranges else float("nan")
    range_high = float(ranges[-1][1]) if ranges else float("nan")

    touch_prob = 0.0
    if candidate.breakeven_points:
        touch_prob = max(
            probability_of_touch(
                underlying_price,
                be,
                implied_volatility,
                candidate.days_to_expiration,
            )
            for be in candidate.breakeven_points
        )

    return {
        "pop": max(0.0, min(100.0, pop_prob * 100.0)),
        "expected_value": expected_value,
        "expected_profit": expected_profit,
        "expected_loss": expected_loss,
        "profit_range_low": range_low,
        "profit_range_high": range_high,
        "probability_of_touch": max(0.0, min(100.0, touch_prob * 100.0)),
    }
