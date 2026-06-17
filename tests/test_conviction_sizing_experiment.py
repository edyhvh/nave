from __future__ import annotations

from scripts.conviction_sizing_experiment import TradeRow, evaluate_policy, policy_proposed, score_band
from trading.crypto.momentum import MomentumBacktester


def _trade(score: int, r: float, period: str = "p") -> TradeRow:
    return TradeRow(
        period=period,
        symbol="BTCUSDT",
        side="long",
        r_multiple=r,
        confidence_score=score,
        entry_time=f"2024-01-{score % 20 + 1:02d}T00:00:00+00:00",
    )


def test_score_band_boundaries():
    assert score_band(96) == "95-100"
    assert score_band(90) == "90-94"
    assert score_band(89) == "80-89"
    assert score_band(77) == "<80"


def test_proposed_policy_scales_r_by_risk_relative_to_base():
    trades = [_trade(92, 2.0), _trade(84, -1.0)]

    result = evaluate_policy(trades, policy_proposed)

    metrics = result["metrics"]
    assert metrics["trades"] == 2
    assert metrics["total_weighted_r"] == 2.0
    assert metrics["return_pct"] == 0.01
    assert result["average_risk_pct"] == 0.00625


def test_quality_grouping_by_score_band():
    trades = [_trade(96, 1.0), _trade(92, -1.0), _trade(84, 2.0)]

    result = evaluate_policy(trades, policy_proposed)

    assert result["by_score_band"]["95-100"]["trades"] == 1
    assert result["by_score_band"]["90-94"]["trades"] == 1
    assert result["by_score_band"]["80-89"]["trades"] == 1


def test_momentum_backtester_rejects_invalid_step_bars():
    backtester = MomentumBacktester()
    try:
        backtester.evaluate(
            symbol="BTCUSDT",
            daily_frame=[],
            setup_frame=[],
            trigger_frame=[],
            step_bars=0,
        )
    except ValueError as exc:
        assert "step_bars" in str(exc)
    else:
        raise AssertionError("expected invalid step_bars to raise")
