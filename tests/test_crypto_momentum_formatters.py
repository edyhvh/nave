from __future__ import annotations

from trading.crypto.momentum.formatters import (
    render_entry_zone_alert_markdown_v2,
    render_momentum_scan_markdown_v2,
)


def _scan_payload() -> dict:
    return {
        "generated_at": "2026-05-06T12:00:00+00:00",
        "strategy": "derivatives_momentum_v1",
        "summary": {
            "tradeable_count": 0,
            "confirmed_count": 0,
            "effective_score_threshold": 75,
            "cadence_state": "quiet",
        },
        "cadence": {
            "state": "quiet",
            "note": "Momentum breadth is thin; tighten selection.",
        },
        "results": {
            "BTCUSDT": {
                "plans": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "setup_status": "pending",
                        "tradeable": False,
                        "confidence_score": 84,
                        "entry_zone": [81112.86, 82479.0],
                        "invalidation": 81052.5,
                        "tp1": 85778.16,
                        "tp2": 89077.32,
                        "tp3": 93036.31,
                        "rr_estimated": 4.63,
                        "sizing": {"risk_pct": 0.005},
                        "reasoning": {
                            "blockers": ["falta retest", "falta trigger 1H"],
                            "confirmations": ["1D y 4H alcistas"],
                        },
                        "diagnostics": {"funding_rate": -0.00000817, "oi_change_pct": 0.0179},
                    },
                    {
                        "symbol": "BTCUSDT",
                        "side": "short",
                        "setup_status": "invalid",
                        "tradeable": False,
                        "confidence_score": 36,
                        "entry_zone": [77530.75, 78781.25],
                        "invalidation": 84146.94,
                        "tp1": 79197.12,
                        "tp2": 77854.0,
                        "tp3": 75068.2,
                        "rr_estimated": 2.81,
                    },
                ],
            },
            "ETHUSDT": {
                "plans": [
                    {
                        "symbol": "ETHUSDT",
                        "side": "long",
                        "setup_status": "pending",
                        "tradeable": False,
                        "confidence_score": 85,
                        "entry_zone": [2379.21, 2417.59],
                        "invalidation": 2359.65,
                        "tp1": 2506.09,
                        "tp2": 2602.48,
                        "tp3": 2718.14,
                        "rr_estimated": 3.85,
                        "sizing": {"risk_pct": 0.005},
                        "reasoning": {
                            "blockers": ["falta validacion de zona", "falta trigger 1H"],
                            "confirmations": ["breakout 4H presente"],
                        },
                        "diagnostics": {"funding_rate": -0.00005321, "oi_change_pct": 0.1105},
                    }
                ],
            },
        },
    }


def test_render_momentum_scan_markdown_includes_watchlist_and_symbols() -> None:
    messages = render_momentum_scan_markdown_v2(_scan_payload())
    text = "\n".join(messages)

    assert messages
    assert "NAVE Crypto" in text
    assert "Watchlist prioritaria" in text
    assert "BTCUSDT" in text
    assert "ETHUSDT" in text
    assert "sin trade ahora" in text


def test_render_momentum_scan_markdown_chunks_when_needed() -> None:
    payload = _scan_payload()
    for idx in range(30):
        payload["results"][f"ALT{idx}USDT"] = {
            "plans": [
                {
                    "symbol": f"ALT{idx}USDT",
                    "side": "long",
                    "setup_status": "pending",
                    "tradeable": False,
                    "confidence_score": 80,
                    "entry_zone": [100 + idx, 101 + idx],
                    "invalidation": 99 + idx,
                    "tp1": 102 + idx,
                    "tp2": 103 + idx,
                    "tp3": 104 + idx,
                    "rr_estimated": 2.2,
                    "reasoning": {"blockers": ["faltan confirmaciones"]},
                    "sizing": {"risk_pct": 0.005},
                }
            ]
        }

    messages = render_momentum_scan_markdown_v2(payload, max_message_chars=500)
    assert len(messages) > 1
    assert messages[0].startswith("*Parte 1/")


def test_render_momentum_scan_markdown_flags_extended_setup() -> None:
    payload = _scan_payload()
    payload["results"]["BTCUSDT"]["plans"][0]["diagnostics"]["breakout_status"] = "extended"

    messages = render_momentum_scan_markdown_v2(payload)

    joined = "\n".join(messages)
    assert "movimiento extendido" in joined
    assert "no trail de entrada fresca" in joined


def test_render_momentum_scan_markdown_does_not_publish_invalid_levels_as_watchlist() -> None:
    payload = {
        "generated_at": "2026-06-18T12:00:00+00:00",
        "summary": {"tradeable_count": 0, "effective_score_threshold": 90},
        "results": {
            "BTCUSDT": {
                "plans": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "short",
                        "setup_status": "invalid",
                        "tradeable": False,
                        "confidence_score": 47,
                        "entry_zone": [66745.0, 67821.0],
                        "invalidation": 67483.0,
                        "tp1": 65000.0,
                        "tp2": 63000.0,
                        "tp3": 61000.0,
                        "rr_estimated": 1.8,
                        "reasoning": {"blockers": ["retest invalid"]},
                    }
                ]
            }
        },
    }

    text = "\n".join(render_momentum_scan_markdown_v2(payload))

    assert "Watchlist prioritaria" not in text
    assert "Niveles: inactivos" in text
    assert "Zona: 66,745.00" not in text


def test_render_momentum_scan_markdown_uses_side_aware_short_entry_reference() -> None:
    payload = _scan_payload()
    payload["results"] = {
        "BTCUSDT": {
            "plans": [
                {
                    "symbol": "BTCUSDT",
                    "side": "short",
                    "setup_status": "pending",
                    "tradeable": False,
                    "confidence_score": 80,
                    "entry_zone": [66745.0, 67821.0],
                    "invalidation": 69000.0,
                    "tp1": 65000.0,
                    "tp2": 63000.0,
                    "tp3": 61000.0,
                    "rr_estimated": 2.1,
                    "sizing": {"risk_pct": 0.005},
                    "reasoning": {"blockers": ["falta trigger 1H"]},
                }
            ]
        }
    }

    text = "\n".join(render_momentum_scan_markdown_v2(payload))

    assert "zona 66,745\\.00 \\- 67,821\\.00" in text
    assert "entrada ref 66,745\\.00" in text
    assert "Entrada ref: 66,745\\.00" in text


def test_render_entry_zone_alert_markdown() -> None:
    message = render_entry_zone_alert_markdown_v2(
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "price": 81900.0,
            "entry_zone": [81112.86, 82479.0],
            "invalidation": 81052.5,
            "confidence_score": 84,
        }
    )

    assert "Alerta de Entrada" in message
    assert "BTCUSDT" in message
    assert "LONG" in message
    assert "score" in message
