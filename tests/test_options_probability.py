from __future__ import annotations

from options.analytics.probability import (
    evaluate_strategy_distribution,
    probability_of_touch,
    strategy_pnl_profile,
    terminal_price_distribution,
)
from options.models import StrategyCandidate, StrategyLeg


def test_terminal_price_distribution_weights_sum_to_one() -> None:
    prices, weights = terminal_price_distribution(100.0, 0.25, 30)
    assert len(prices) == len(weights)
    assert abs(float(weights.sum()) - 1.0) < 1e-9


def test_probability_of_touch_increases_with_closer_barrier() -> None:
    near = probability_of_touch(100.0, 102.0, 0.25, 30)
    far = probability_of_touch(100.0, 120.0, 0.25, 30)
    assert 0.0 <= far <= near <= 1.0


def test_strategy_distribution_metrics_for_long_call() -> None:
    candidate = StrategyCandidate(
        name="long_call_test",
        expiration="2099-12-15",
        days_to_expiration=30,
        legs=[
            StrategyLeg(
                instrument_type="option",
                side="buy",
                quantity=1,
                premium=5.0,
                strike=100.0,
                option_type="call",
            )
        ],
        net_premium=-500.0,
        max_profit=None,
        max_loss=500.0,
        breakeven_points=[105.0],
    )

    prices, _ = terminal_price_distribution(100.0, 0.25, 30)
    pnl = strategy_pnl_profile(candidate, prices)
    assert pnl.min() <= 0.0
    assert pnl.max() > 0.0

    metrics = evaluate_strategy_distribution(
        candidate,
        underlying_price=100.0,
        implied_volatility=0.25,
    )
    assert 0.0 <= metrics["pop"] <= 100.0
    assert 0.0 <= metrics["probability_of_touch"] <= 100.0
    assert metrics["expected_loss"] >= 0.0
