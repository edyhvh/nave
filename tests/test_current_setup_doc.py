from __future__ import annotations

from trading.crypto.analysis.current_setup_doc import render_current_setup_markdown


def test_render_current_setup_includes_operator_stack_banner():
    review = {
        "generated_at": "2026-06-04T12:00:00+00:00",
        "coins": ["BTC"],
        "summary": {"actionable_count": 0, "watch_count": 1, "stand_aside_count": 0},
        "recommendations": [
            {
                "coin": "BTC",
                "action": "watch",
                "direction": "short",
                "confidence": 0.72,
                "primary_source": "cot+regime",
                "regime_phase": "leg_down",
                "entry_zone": [63000.0, 80000.0],
                "invalidation": None,
                "targets": [],
                "reasons": ["COT: bearish"],
                "blockers": ["No momentum setup"],
                "instruments": ["hyperliquid_perp", "deribit_options:advisory"],
                "options": {
                    "status": "ready",
                    "strategy": "call_butterfly",
                    "execution_lane": "options_advisory",
                    "advisory_reason": "touch gate",
                    "metrics": {"pop_pct": 59.0, "probability_of_touch_pct": 84.0},
                },
            }
        ],
    }
    md = render_current_setup_markdown(review, theory_by_coin={})
    assert "operator stack" in md.lower()
    assert "advisory only" in md.lower()
    assert "WATCH" in md
    assert "Do not use theory_v2 alone" in md
