from __future__ import annotations

from options.ticker_strategy import registry_tape_alignment, strategy_bias_fit


def test_strategy_bias_fit_bull_put_needs_bullish_or_neutral():
    assert strategy_bias_fit("bull_put_credit_spread", "bullish")
    assert strategy_bias_fit("bull_put_credit_spread", "neutral")
    assert not strategy_bias_fit("bull_put_credit_spread", "bearish")


def test_registry_tape_alignment_warns_bull_put_on_bearish_tape():
    index = {
        "ORCL": {
            "strategy": "bull_put_credit_spread",
            "merge_status": "approved",
            "by_bias": {"bearish": {"strategy": "bear_call_credit_spread"}},
        }
    }
    out = registry_tape_alignment(
        "ORCL",
        "bull_put_credit_spread",
        tape_bias="bearish",
        strategy_index=index,
    )
    assert out["warning"]
    assert out["score_penalty"] > 0
    assert not out["aligned"]
