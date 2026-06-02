"""Per-ticker setup learning tests."""

from __future__ import annotations

from options.ticker_strategy import (
    edge_score,
    learn_ticker_strategy,
    registry_setup_bonus,
    strategy_bias_fit,
)


def _row(
    ticker: str,
    strategy: str,
    *,
    profitable: bool,
    pnl: float,
) -> dict:
    return {
        "ticker": ticker,
        "status": "trade_candidate",
        "strategy_name": strategy,
        "profitable": profitable,
        "mark": {"pnl_dollars": pnl},
        "entry_metrics": {"pop": 78.0, "probability_of_touch": 42.0},
        "directional_bias": "bullish",
    }


def test_learn_picks_bull_put_for_wfc_pattern() -> None:
    rows = [
        _row("WFC", "bull_put_credit_spread", profitable=True, pnl=40),
        _row("WFC", "bull_put_credit_spread", profitable=True, pnl=20),
        _row("WFC", "bull_put_credit_spread", profitable=False, pnl=-30),
        _row("WFC", "bear_call_credit_spread", profitable=False, pnl=-80),
    ]
    learned = learn_ticker_strategy(rows, "WFC", bias_20d="neutral")
    assert learned["status"] == "ok"
    assert learned["primary"]["strategy"] == "bull_put_credit_spread"
    assert learned["by_bias"]["neutral"]["strategy"] == "bull_put_credit_spread"
    bear = next(s for s in learned["ranked"] if s["strategy"] == "bear_call_credit_spread")
    assert bear["win_rate"] < learned["primary"]["win_rate"]


def test_by_bias_differs_for_bearish_tape() -> None:
    rows = [
        _row("XYZ", "bull_put_credit_spread", profitable=False, pnl=-50),
        _row("XYZ", "bull_put_credit_spread", profitable=False, pnl=-40),
        _row("XYZ", "bear_call_credit_spread", profitable=True, pnl=60),
        _row("XYZ", "bear_call_credit_spread", profitable=True, pnl=45),
    ]
    learned = learn_ticker_strategy(rows, "XYZ", bias_20d="bearish")
    assert learned["primary"]["strategy"] == "bear_call_credit_spread"
    assert learned["by_bias"]["bearish"]["strategy"] == "bear_call_credit_spread"


def test_registry_setup_bonus_primary_match() -> None:
    idx = {
        "WFC": {
            "strategy": "bull_put_credit_spread",
            "confidence": "high",
            "merge_status": "approved",
            "by_bias": {},
            "avoid": set(),
        }
    }
    pts, reasons = registry_setup_bonus(
        "WFC",
        "bull_put_credit_spread",
        strategy_index=idx,
    )
    assert pts == 18.0
    assert reasons


def test_strategy_bias_fit() -> None:
    assert strategy_bias_fit("bull_put_credit_spread", "neutral")
    assert not strategy_bias_fit("bull_put_credit_spread", "bearish")
    assert strategy_bias_fit("bear_call_credit_spread", "bearish")


def test_edge_score_scales_with_sample() -> None:
    low = edge_score(trades=1, win_rate=1.0, avg_pnl_dollars=50.0)
    high = edge_score(trades=8, win_rate=0.75, avg_pnl_dollars=25.0)
    assert high > low