from __future__ import annotations

import json

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_cli_registers_crypto_group() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "crypto" in result.stdout


def test_crypto_momentum_scan_json(monkeypatch) -> None:
    payload = {
        "strategy": "derivatives_momentum_v1",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "summary": {"tradeable_count": 1},
        "results": {
            "BTCUSDT": {"plans": [{"side": "long", "tradeable": True, "confidence_score": 88, "setup_status": "confirmed", "entry_zone": [100.0, 101.0], "invalidation": 98.0, "tp2": 109.0, "rr_estimated": 2.2, "expected_move_pct": 0.08}], "tradeable": []},
            "ETHUSDT": {"plans": [], "tradeable": []},
        },
    }

    from trading.crypto.momentum.service import MomentumMarketService

    monkeypatch.setattr(MomentumMarketService, "scan_live", lambda self, **kwargs: payload)
    result = runner.invoke(app, ["crypto", "momentum-scan", "--symbols", "BTCUSDT,ETHUSDT", "--json"])

    assert result.exit_code == 0
    decoded = json.loads(result.stdout)
    assert decoded["strategy"] == "derivatives_momentum_v1"
    assert decoded["summary"]["tradeable_count"] == 1


def test_crypto_momentum_playbook_json(monkeypatch) -> None:
    payload = {
        "strategy": "derivatives_momentum_v1",
        "symbol": "BTCUSDT",
        "plan": {
            "side": "short",
            "setup_status": "confirmed",
            "tradeable": True,
            "confidence_score": 90,
            "entry_zone": [100.0, 101.0],
            "invalidation": 102.0,
            "tp1": 96.0,
            "tp2": 92.0,
            "tp3": 88.0,
            "rr_estimated": 2.0,
            "expected_move_pct": 0.09,
        },
    }

    from trading.crypto.momentum.service import MomentumMarketService

    monkeypatch.setattr(MomentumMarketService, "playbook_live", lambda self, **kwargs: payload)
    result = runner.invoke(app, ["crypto", "momentum-playbook", "--symbol", "BTCUSDT", "--side", "short", "--json"])

    assert result.exit_code == 0
    decoded = json.loads(result.stdout)
    assert decoded["plan"]["side"] == "short"
    assert decoded["plan"]["tradeable"] is True


def test_crypto_scan_alias_defaults_to_momentum(monkeypatch) -> None:
    payload = {
        "strategy": "derivatives_momentum_v1",
        "symbols": ["BTCUSDT"],
        "summary": {"tradeable_count": 1},
        "results": {"BTCUSDT": {"plans": [], "tradeable": []}},
    }

    from trading.crypto.momentum.service import MomentumMarketService

    monkeypatch.setattr(MomentumMarketService, "scan_live", lambda self, **kwargs: payload)
    result = runner.invoke(app, ["crypto", "scan", "--symbols", "BTCUSDT", "--json"])

    assert result.exit_code == 0
    decoded = json.loads(result.stdout)
    assert decoded["strategy"] == "derivatives_momentum_v1"


def test_crypto_playbook_alias_defaults_to_momentum(monkeypatch) -> None:
    payload = {
        "strategy": "derivatives_momentum_v1",
        "symbol": "ETHUSDT",
        "plan": {
            "side": "long",
            "setup_status": "pending",
            "tradeable": False,
            "confidence_score": 76,
            "entry_zone": [10.0, 11.0],
            "invalidation": 9.5,
            "tp1": 12.0,
            "tp2": 13.0,
            "tp3": 14.0,
            "rr_estimated": 1.9,
            "expected_move_pct": 0.08,
        },
    }

    from trading.crypto.momentum.service import MomentumMarketService

    monkeypatch.setattr(MomentumMarketService, "playbook_live", lambda self, **kwargs: payload)
    result = runner.invoke(app, ["crypto", "playbook", "--symbol", "ETHUSDT", "--side", "long", "--json"])

    assert result.exit_code == 0
    decoded = json.loads(result.stdout)
    assert decoded["strategy"] == "derivatives_momentum_v1"
    assert decoded["plan"]["side"] == "long"