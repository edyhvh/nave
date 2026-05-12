"""Strategy scoring and recommendation ranking."""

from __future__ import annotations

import numpy as np
import pandas as pd

from options.analytics.probability import evaluate_strategy_distribution
from options.models import StrategyCandidate, StrategyMetrics, StrategyRecommendation


def _aggregate_greek_exposure(option_frame: pd.DataFrame, candidate: StrategyCandidate) -> tuple[float, float]:
    theta_total = 0.0
    vega_total = 0.0

    for leg in candidate.legs:
        if leg.instrument_type != "option" or leg.strike is None or leg.option_type is None:
            continue

        side_mult = 1.0 if leg.side == "buy" else -1.0
        rows = option_frame[
            (option_frame["expiration"] == candidate.expiration)
            & (option_frame["strike"] == leg.strike)
            & (option_frame["option_type"] == leg.option_type)
        ]
        if rows.empty:
            continue
        row = rows.iloc[0]
        theta_total += side_mult * \
            float(row.get("theta", 0.0) or 0.0) * float(leg.quantity)
        vega_total += side_mult * \
            float(row.get("vega", 0.0) or 0.0) * float(leg.quantity)

    return theta_total, vega_total


def _risk_reward(candidate: StrategyCandidate) -> float:
    if candidate.max_profit is None or candidate.max_loss is None or candidate.max_loss <= 0:
        return 1.0
    return float(max(0.0, candidate.max_profit / candidate.max_loss))


def _edge_score(*, expected_value: float, risk_reward: float) -> float:
    ev_component = np.tanh(expected_value / 300.0) * 30.0 + 30.0
    rr_component = min(40.0, max(0.0, risk_reward) * 20.0)
    return float(max(0.0, min(100.0, ev_component + rr_component)))


def _negative_ev_penalty(*, expected_value: float, iv_rank: float | None, iv_percentile: float | None) -> float:
    if expected_value >= 0:
        return 0.0

    base_penalty = 8.0 + min(20.0, abs(expected_value) / 25.0)
    elevated_iv = 0.0

    if iv_rank is not None and np.isfinite(iv_rank) and iv_rank >= 40.0:
        elevated_iv = max(elevated_iv, min(1.0, (iv_rank - 40.0) / 40.0))
    if iv_percentile is not None and np.isfinite(iv_percentile) and iv_percentile >= 60.0:
        elevated_iv = max(elevated_iv, min(1.0, (iv_percentile - 60.0) / 40.0))

    return float(base_penalty * (1.0 + (0.6 * elevated_iv)))


def _composite_score(
    *,
    strategy_name: str,
    pop: float,
    expected_value: float,
    expected_loss: float,
    risk_reward: float,
    max_loss: float,
    theta_per_day: float,
    vega_exposure: float,
    probability_of_touch: float,
    iv_rank: float | None = None,
    iv_percentile: float | None = None,
) -> float:
    ev_scaled = np.tanh(expected_value / 500.0) * 100.0
    rr_scaled = min(100.0, risk_reward * 35.0)
    edge_score = _edge_score(
        expected_value=expected_value, risk_reward=risk_reward)
    loss_penalty = max(0.0, min(100.0, (max_loss + expected_loss) / 35.0))
    theta_scaled = np.tanh(theta_per_day / 2.0) * 50.0 + 50.0
    vega_penalty = max(0.0, min(100.0, abs(vega_exposure) * 8.0))
    touch_scaled = max(0.0, min(100.0, probability_of_touch))
    touch_comfort_scaled = 100.0 - touch_scaled
    negative_ev_penalty = _negative_ev_penalty(
        expected_value=expected_value,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
    )
    high_touch_penalty = max(0.0, touch_scaled - 85.0) * 0.9
    if strategy_name in {"long_straddle", "long_strangle"} and touch_scaled > 85.0:
        high_touch_penalty += min(15.0, (touch_scaled - 85.0) * 1.2)

    raw = (
        0.27 * pop
        + 0.18 * ev_scaled
        + 0.14 * rr_scaled
        + 0.12 * theta_scaled
        + 0.08 * touch_comfort_scaled
        + 0.11 * edge_score
        - 0.05 * loss_penalty
        - 0.02 * vega_penalty
        - negative_ev_penalty
        - high_touch_penalty
    )
    return float(max(0.0, min(100.0, raw)))


def _tradeoff_comment(
    *,
    strategy_name: str,
    pop: float,
    expected_value: float,
    probability_of_touch: float,
    max_loss: float,
    risk_reward: float,
) -> str:
    strategy_key = strategy_name.lower().strip()
    tone: list[str] = []

    if strategy_key == "long_straddle":
        tone.append("ATM volatility expansion setup")
    elif strategy_key == "long_strangle":
        tone.append("OTM volatility expansion setup with wider strikes")
    elif strategy_key == "covered_call":
        tone.append("Income-oriented overlay with upside cap")
    elif strategy_key == "cash_secured_put":
        tone.append("Income + discounted-entry style setup")
    elif strategy_key == "iron_condor":
        tone.append("Range-bound premium collection setup")

    if pop >= 60.0:
        tone.append("Higher win-probability profile")
    elif pop <= 40.0:
        tone.append("Lower win-probability, higher convexity setup")
    else:
        tone.append("Balanced probability profile")

    if expected_value >= 0:
        tone.append("positive modeled expectancy")
    else:
        tone.append("negative modeled expectancy")

    if risk_reward >= 2.0:
        tone.append("strong payoff asymmetry")
    elif risk_reward < 1.0:
        tone.append("limited payoff asymmetry")

    if probability_of_touch >= 70.0:
        tone.append("high path-risk (likely breakeven touch)")
    elif probability_of_touch <= 35.0:
        tone.append("lower path-risk before expiration")

    tone.append(f"PoP {pop:.1f}% | touch {probability_of_touch:.1f}%")

    if max_loss > 0:
        tone.append(f"max loss about ${max_loss:,.0f} per 1-lot position")

    return f"{strategy_name.replace('_', ' ')}: " + "; ".join(tone) + "."


def rank_recommendations(
    *,
    candidates: list[StrategyCandidate],
    option_frame: pd.DataFrame,
    underlying_price: float,
    iv_atm: float,
    iv_rank: float | None = None,
    iv_percentile: float | None = None,
    top_n: int = 3,
) -> list[StrategyRecommendation]:
    """Rank strategy candidates and return top recommendations."""
    recs: list[StrategyRecommendation] = []
    for candidate in candidates:
        theta_per_day, vega_exposure = _aggregate_greek_exposure(
            option_frame, candidate)
        dist = evaluate_strategy_distribution(
            candidate,
            underlying_price=underlying_price,
            implied_volatility=iv_atm,
        )
        pop = float(dist["pop"])
        expected_value = float(dist["expected_value"])
        expected_profit = float(dist["expected_profit"])
        expected_loss = float(dist["expected_loss"])
        probability_of_touch = float(dist["probability_of_touch"])
        profit_range_low = float(dist["profit_range_low"])
        profit_range_high = float(dist["profit_range_high"])
        risk_reward = _risk_reward(candidate)
        max_loss = float(candidate.max_loss or 0.0)
        score = _composite_score(
            strategy_name=candidate.name,
            pop=pop,
            expected_value=expected_value,
            expected_loss=expected_loss,
            risk_reward=risk_reward,
            max_loss=max_loss,
            theta_per_day=theta_per_day,
            vega_exposure=vega_exposure,
            probability_of_touch=probability_of_touch,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
        )

        pnl_samples = [expected_value - max_loss, expected_value,
                       expected_value + (candidate.max_profit or 0.0)]
        recs.append(
            StrategyRecommendation(
                strategy=candidate,
                metrics=StrategyMetrics(
                    pop=pop,
                    expected_value=expected_value,
                    expected_profit=expected_profit,
                    expected_loss=expected_loss,
                    risk_reward=risk_reward,
                    max_loss=max_loss,
                    theta_per_day=float(theta_per_day),
                    vega_exposure=float(vega_exposure),
                    probability_of_touch=probability_of_touch,
                    profit_range_low=profit_range_low,
                    profit_range_high=profit_range_high,
                    composite_score=score,
                ),
                pnl_samples=[float(x) for x in pnl_samples],
                tradeoff_comment=_tradeoff_comment(
                    strategy_name=candidate.name,
                    pop=pop,
                    expected_value=expected_value,
                    probability_of_touch=probability_of_touch,
                    max_loss=max_loss,
                    risk_reward=risk_reward,
                ),
            )
        )

    return sorted(recs, key=lambda item: item.metrics.composite_score, reverse=True)[:top_n]
