from __future__ import annotations

from trading.crypto.analysis.daily_display import render_daily_entry_check


def test_render_daily_shows_secondary_table(capsys):
    payload = {
        "generated_at": "2026-06-16T12:00:00+00:00",
        "summary": {"actionable_count": 0, "watch_count": 1, "stand_aside_count": 1},
        "recommendations": [
            {
                "coin": "ETH",
                "action": "watch",
                "direction": "short",
                "confidence": 0.73,
                "regime_phase": "relief_rally_fade",
                "entry_zone": [1700, 2100],
                "invalidation": 2150,
                "momentum_score": None,
                "playbook": "fade relief rally",
                "reasons": ["COT bearish"],
                "blockers": [],
                "targets": [1720, 1667],
                "secondary_opportunities": [
                    {
                        "kind": "forming_short",
                        "direction": "short",
                        "confidence": 0.73,
                        "playbook": "Short structure forming",
                        "entry_zone": [1640, 1670],
                        "invalidation": 1700,
                        "targets": [1600],
                    }
                ],
            },
            {
                "coin": "BTC",
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
    assert "Secondary opportunities" in captured.out
    assert "forming_short" in captured.out
    assert "Primary stack: stand aside" not in captured.out


def test_render_daily_stand_aside_with_secondary_hint(capsys):
    payload = {
        "generated_at": "2026-06-16T12:00:00+00:00",
        "summary": {"actionable_count": 0, "watch_count": 0, "stand_aside_count": 1},
        "recommendations": [
            {
                "coin": "BTC",
                "action": "stand_aside",
                "direction": None,
                "confidence": 0,
                "regime_phase": "neutral",
                "reasons": [],
                "blockers": ["none"],
                "secondary_opportunities": [
                    {
                        "kind": "relief_rally_fade",
                        "direction": "short",
                        "confidence": 0.72,
                        "playbook": "Fade relief rally",
                        "entry_zone": [65000, 76000],
                        "invalidation": 78000,
                    }
                ],
            },
        ],
    }
    render_daily_entry_check(payload)
    captured = capsys.readouterr()
    assert "Primary stack: stand aside" in captured.out
    assert "relief_rally_fade" in captured.out


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


def test_render_daily_shows_primary_enter_risk_hint(capsys):
    payload = {
        "generated_at": "2026-06-02T12:00:00+00:00",
        "summary": {"actionable_count": 1, "watch_count": 0, "stand_aside_count": 0},
        "recommendations": [
            {
                "coin": "BTC",
                "action": "enter",
                "direction": "long",
                "confidence": 0.96,
                "regime_phase": "continuation_long",
                "entry_zone": [70000, 71000],
                "invalidation": 69000,
                "momentum_score": 96,
                "playbook": "test",
                "reasons": ["ok"],
                "blockers": [],
                "targets": [73000],
                "suggested_risk": {
                    "mode": "advisory",
                    "current_risk_pct": 0.005,
                    "suggested_risk_pct": 0.0075,
                    "blocked": False,
                },
            }
        ],
    }
    render_daily_entry_check(payload)
    captured = capsys.readouterr()
    assert "0.75%" in captured.out
    assert "advisory" in captured.out


def test_render_daily_shows_blocked_risk_hint(capsys):
    payload = {
        "generated_at": "2026-06-02T12:00:00+00:00",
        "summary": {"actionable_count": 1, "watch_count": 0, "stand_aside_count": 0},
        "recommendations": [
            {
                "coin": "BTC",
                "action": "enter",
                "direction": "long",
                "confidence": 0.96,
                "regime_phase": "continuation_long",
                "entry_zone": [70000, 71000],
                "invalidation": 69000,
                "momentum_score": 96,
                "playbook": "test",
                "reasons": ["ok"],
                "blockers": [],
                "targets": [73000],
                "suggested_risk": {
                    "mode": "advisory",
                    "current_risk_pct": 0.005,
                    "suggested_risk_pct": 0.005,
                    "blocked": True,
                    "blockers": ["COT history is stale"],
                },
            }
        ],
    }
    render_daily_entry_check(payload)
    captured = capsys.readouterr()
    assert "blocked" in captured.out
    assert "COT history is stale" in captured.out
