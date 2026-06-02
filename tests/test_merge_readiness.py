"""Merge-readiness gate tests."""

from __future__ import annotations

from options.merge_readiness import assess_merge_status, summarize_registry_merge_readiness


def test_approve_strong_in_sample() -> None:
    learned = {
        "confidence": "high",
        "primary": {
            "strategy": "bull_put_credit_spread",
            "edge_score": 55,
            "win_rate": 0.75,
            "trades": 8,
        },
    }
    m = assess_merge_status(learned, {"oos_win_rate": 0.6, "oos_trades": 5})
    assert m["merge_status"] == "approved"
    assert m["validated_setup"] == "bull_put_credit_spread"


def test_reject_low_edge() -> None:
    learned = {
        "confidence": "low",
        "primary": {"strategy": "bear_call_credit_spread", "edge_score": 5, "win_rate": 0.0, "trades": 1},
    }
    m = assess_merge_status(learned, {"oos_win_rate": 0.0, "oos_trades": 4})
    assert m["merge_status"] == "reject"


def test_summarize_registry_counts() -> None:
    profiles = {
        "WFC": {
            "learned_strategy": {
                "primary": {"strategy": "bull_put_credit_spread", "edge_score": 55, "win_rate": 0.75, "trades": 8},
                "confidence": "high",
                "walkforward": {"oos_win_rate": 0.6, "oos_trades": 5},
                "merge": {"merge_status": "approved", "validated_setup": "bull_put_credit_spread"},
            }
        },
        "MSFT": {
            "learned_strategy": {
                "primary": {"strategy": "bull_put_credit_spread", "edge_score": 3, "win_rate": 0.2, "trades": 6},
                "confidence": "medium",
                "merge": {"merge_status": "watch", "validated_setup": "bull_put_credit_spread"},
            }
        },
    }
    summary = summarize_registry_merge_readiness(profiles)
    assert summary["counts"]["approved"] == 1
    assert summary["counts"]["watch"] == 1