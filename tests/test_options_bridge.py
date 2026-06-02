from __future__ import annotations

from trading.crypto.analysis.options_bridge import normalize_options_metrics, summarize_options_opportunity


def test_normalize_options_metrics_scales_pop_and_ev():
    raw = {"pop": 0.604, "expected_value": 346805.0, "probability_of_touch": 77.09}
    out = normalize_options_metrics(raw)
    assert out["pop_pct"] == 60.4
    assert out["expected_value"] == 346.81
    assert out["probability_of_touch_pct"] == 77.09


def test_summarize_options_opportunity_ready():
    opp = {
        "status": "ready",
        "directional_bias": "bearish",
        "executable_strategy": "bear_put_debit_spread",
        "executable_metrics": {"pop": 58.0, "expected_value": 120.5, "composite_score": 80},
        "trade_decision": {"status": "trade_candidate"},
    }
    summary = summarize_options_opportunity(opp)
    assert summary["status"] == "ready"
    assert summary["strategy"] == "bear_put_debit_spread"
    assert summary["metrics"]["pop_pct"] == 58.0