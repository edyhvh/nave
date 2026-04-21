"""Tests for Hermes integration contracts and CLI registration."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cli.main import app
from core.exceptions import HermesIntegrationError
from hermes.integration import HermesNaveIntegration
from trading.signals import Direction, Signal, Timeframe
from trading.theory_v2 import TheoryV2Decision

runner = CliRunner()


def test_list_tools_contains_required_toolset() -> None:
    integration = HermesNaveIntegration()
    payload = integration.list_tools()

    assert payload["skill"]["name"] == "nave_trading"
    tool_names = {tool["name"] for tool in payload["tools"]}
    assert {
        "cot_report",
        "cot_history",
        "weekly_plan",
        "theory_v2_scan",
        "strategy_context",
    }.issubset(tool_names)


def test_gateway_invoke_requires_tool_name() -> None:
    integration = HermesNaveIntegration()

    with pytest.raises(HermesIntegrationError):
        integration.gateway_invoke({"arguments": {}})


def test_dispatch_tool_call_uses_registered_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    def fake_report(**kwargs):
        return {"ok": True, "args": kwargs}

    monkeypatch.setattr(integration, "cot_report", fake_report)
    result = integration.dispatch_tool_call("cot_report", {"coins": "BTC ETH"})

    assert result["ok"] is True
    assert result["tool"] == "cot_report"
    assert result["result"]["args"]["coins"] == "BTC ETH"


def test_cli_registers_hermes_group() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "hermes" in result.stdout


def _fake_fired_decision() -> TheoryV2Decision:
    signal = Signal(
        coin="BTC",
        direction=Direction.LONG,
        confidence=0.65,
        source="theory_v2",
        bias_timeframe=Timeframe.WEEKLY,
        setup_timeframe=Timeframe.H4,
        trigger_timeframe=Timeframe.H1,
        invalidation=70000.0,
        targets=[75000.0, 80000.0],
        metadata={
            "entry_price": 72000.0,
            "bias": "long",
            "stop_distance": 0.0278,
            "zc1_rr": 1.5,
            "daily_atr_14": 1500.0,
            "retrace_fraction": 0.62,
            "weekly_velocity_atr": 1.58,
        },
    )
    return TheoryV2Decision(
        coin="BTC",
        bias="long",
        daily_confirmed=True,
        setup_valid=True,
        stage="fired",
        reason="retrace 62% inside entry band",
        signal=signal,
    )


def _fake_neutral_decision(coin: str = "ETH") -> TheoryV2Decision:
    return TheoryV2Decision(
        coin=coin,
        bias="neutral",
        daily_confirmed=False,
        setup_valid=False,
        stage="weekly",
        reason="no high-momentum weekly bias (velocity=+0.45 ATRs)",
        signal=None,
    )


def test_theory_v2_scan_returns_decision_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()
    fired = _fake_fired_decision()
    neutral = _fake_neutral_decision()

    def fake_build(coins):
        return [fired.signal], [fired, neutral]

    monkeypatch.setattr("trading.theory_v2.build_signals_for_coins", fake_build)

    payload = integration.theory_v2_scan(coins="BTC ETH")

    assert set(payload["coins"].keys()) == {"BTC", "ETH"}
    assert payload["summary"]["fires"] == ["BTC"]
    assert payload["summary"]["fire_count"] == 1
    btc = payload["coins"]["BTC"]
    assert btc["fired"] is True
    assert btc["stage"] == "fired"
    assert btc["signal"]["direction"] == "long"
    assert btc["signal"]["entry_price"] == 72000.0
    assert btc["signal"]["weekly_velocity_atr"] == 1.58
    assert payload["coins"]["ETH"]["fired"] is False
    assert payload["coins"]["ETH"]["stage"] == "weekly"


def test_theory_v2_scan_rejects_empty_coin_list() -> None:
    integration = HermesNaveIntegration()
    with pytest.raises(HermesIntegrationError):
        integration.theory_v2_scan(coins="   ")


def test_strategy_context_exposes_parameters_and_metrics() -> None:
    integration = HermesNaveIntegration()
    ctx = integration.strategy_context()

    assert ctx["version"] == "theory_v2.iter_14"
    weekly = ctx["parameters"]["weekly_momentum"]
    assert weekly["min_velocity_atrs"] == 1.2
    assert weekly["lookback_weeks"] == 4
    pooled = ctx["backtest_metrics"]["pooled"]
    assert pooled["fires"] == 46
    assert pooled["win_rate"] == pytest.approx(0.778)
    assert pooled["total_r"] == pytest.approx(42.54)
    blind_spot_names = {entry["name"] for entry in ctx["known_blind_spots"]}
    assert "range_breakout" in blind_spot_names


def test_dispatch_tool_call_routes_new_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    def fake_scan(**kwargs):
        return {"coins": {"BTC": {"fired": False}}, "summary": {"fires": []}, "args": kwargs}

    monkeypatch.setattr(integration, "theory_v2_scan", fake_scan)

    result = integration.dispatch_tool_call("theory_v2_scan", {"coins": "BTC"})
    assert result["ok"] is True
    assert result["tool"] == "theory_v2_scan"
    assert result["result"]["args"]["coins"] == "BTC"

    ctx_result = integration.dispatch_tool_call("strategy_context", {})
    assert ctx_result["ok"] is True
    assert ctx_result["tool"] == "strategy_context"
    assert ctx_result["result"]["version"] == "theory_v2.iter_14"
