from __future__ import annotations

from trading.crypto.analysis.daily_display import render_daily_entry_check


def test_render_daily_does_not_crash(capsys):
    payload = {
        "generated_at": "2026-06-02T12:00:00+00:00",
        "summary": {"actionable_count": 1, "watch_count": 0, "stand_aside_count": 1},
        "recommendations": [
            {
                "coin": "BTC",
                "action": "enter",
                "direction": "short",
                "confidence": 0.87,
                "regime_phase": "continuation_short",
                "entry_zone": [70000, 71000],
                "invalidation": 72000,
                "momentum_score": 87,
                "playbook": "test",
                "reasons": ["ok"],
                "blockers": [],
                "targets": [68000, 66000],
            },
            {
                "coin": "ETH",
                "action": "stand_aside",
                "direction": None,
                "confidence": 0,
                "regime_phase": "neutral",
                "reasons": [],
                "blockers": ["none"],
            },
        ],
    }
    render_daily_entry_check(payload)
    captured = capsys.readouterr()
    assert "ENTER NOW" in captured.out
    assert "BTC" in captured.out