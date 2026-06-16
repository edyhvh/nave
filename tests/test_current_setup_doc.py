from __future__ import annotations

from trading.crypto.analysis.current_setup_doc import render_current_setup_markdown


def test_render_current_setup_includes_secondary_opportunities():
    review = {
        "generated_at": "2026-06-16T12:00:00+00:00",
        "coins": ["ETH"],
        "summary": {"actionable_count": 0, "watch_count": 1, "stand_aside_count": 0},
        "recommendations": [
            {
                "coin": "ETH",
                "action": "watch",
                "direction": "short",
                "confidence": 0.73,
                "primary_source": "cot+regime",
                "regime_phase": "relief_rally_fade",
                "entry_zone": [1700.0, 2100.0],
                "invalidation": 2150.0,
                "targets": [1720.0, 1667.0],
                "reasons": ["COT: bearish"],
                "blockers": ["No momentum setup"],
                "instruments": ["hyperliquid_perp"],
                "options": {"status": "unavailable"},
                "secondary_opportunities": [
                    {
                        "kind": "forming_short",
                        "direction": "short",
                        "confidence": 0.73,
                        "playbook": "Short structure forming",
                        "entry_zone": [1640.0, 1670.0],
                        "invalidation": 1700.0,
                        "targets": [1600.0],
                        "blockers": ["Wait for daily confirmation"],
                    }
                ],
                "market_context": {
                    "cot_percentile": 50,
                    "regime_metrics": {
                        "drawdown_from_28d_high_pct": 17.7,
                        "bounce_from_14d_low_pct": 10.6,
                    },
                },
            }
        ],
    }
    md = render_current_setup_markdown(review, theory_by_coin={})
    assert "Secondary opportunities" in md
    assert "forming_short" in md
    assert "Market context" in md
    assert "P50" in md


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
