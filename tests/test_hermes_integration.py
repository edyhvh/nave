"""Tests for Hermes integration contracts and CLI registration."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

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
        "recommend_position",
        "scan_history",
        "stocks_ism_report",
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

    assert ctx["version"] == "theory_v2.iter_18"
    weekly = ctx["parameters"]["weekly_momentum"]
    assert weekly["min_velocity_atrs"] == 1.2
    assert weekly["lookback_weeks"] == 4
    assert ctx["parameters"]["range_breakout"]["max_range_atrs"] == 1.5
    pooled = ctx["backtest_metrics"]["pooled"]
    assert pooled["fires"] == 47
    assert pooled["win_rate"] == pytest.approx(0.784)
    assert pooled["total_r"] == pytest.approx(44.14)
    blind_spot_names = {entry["name"] for entry in ctx["known_blind_spots"]}
    assert "cot_extreme_block" in blind_spot_names
    assert "range_breakout_partial" in blind_spot_names


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
    assert ctx_result["result"]["version"] == "theory_v2.iter_18"


def test_dispatch_tool_call_routes_stocks_ism_report(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    def fake_stocks_report(**kwargs):
        return {"kind": "manufacturing", "criteria": kwargs, "summary": {"expanding_candidates": 1}}

    monkeypatch.setattr(integration, "stocks_ism_report", fake_stocks_report)
    result = integration.dispatch_tool_call(
        "stocks_ism_report",
        {"kind": "manufacturing", "top_n": 3, "max_pe_ratio": 25.0},
    )
    assert result["ok"] is True
    assert result["tool"] == "stocks_ism_report"
    assert result["result"]["criteria"]["top_n"] == 3


def test_stocks_ism_report_validates_bounds() -> None:
    integration = HermesNaveIntegration()
    with pytest.raises(HermesIntegrationError):
        integration.stocks_ism_report(kind="bad")
    with pytest.raises(HermesIntegrationError):
        integration.stocks_ism_report(top_n=0)


def _fired_scan_entry() -> dict:
    return {
        "coin": "BTC",
        "bias": "long",
        "stage": "fired",
        "reason": "retrace 62% inside entry band",
        "daily_confirmed": True,
        "setup_valid": True,
        "fired": True,
        "signal": {
            "direction": "long",
            "confidence": 0.65,
            "entry_price": 72000.0,
            "stop_loss": 70000.0,
            "targets": [75000.0, 80000.0],
            "zc1_rr": 1.5,
            "stop_distance_pct": 0.0278,
            "weekly_velocity_atr": 1.58,
            "daily_atr_14": 1500.0,
            "retrace_fraction": 0.62,
            "bias_timeframe": "1W",
            "setup_timeframe": "4H",
            "trigger_timeframe": "1H",
        },
    }


def test_recommend_position_sizes_from_fired_scan() -> None:
    integration = HermesNaveIntegration()
    entry = _fired_scan_entry()

    result = integration.recommend_position(
        coin_scan=entry,
        capital_usd=10000.0,
        leverage=10.0,
        risk_pct=0.01,
    )

    assert result["recommendation"] == "open_position"
    sizing = result["sizing"]
    # stop distance = 2000 → qty = 100 / 2000 = 0.05 BTC
    assert sizing["coin_qty"] == pytest.approx(0.05, rel=1e-3)
    # notional = 0.05 * 72000 = 3600
    assert sizing["notional_usd"] == pytest.approx(3600.0, rel=1e-3)
    # margin = notional / leverage = 360
    assert sizing["margin_required_usd"] == pytest.approx(360.0, rel=1e-3)
    # reward at ZC1 = (75000-72000) * 0.05 = 150 USD → RR = 150 / 100 = 1.5
    assert result["reward"]["zc1_rr"] == pytest.approx(1.5, rel=1e-3)
    assert result["safety"]["default_dry_run"] is True
    assert result["safety"]["suggested_mcp_call"]["tool"] == "open_position"


def test_recommend_position_stand_aside_on_unfired_scan() -> None:
    integration = HermesNaveIntegration()
    result = integration.recommend_position(
        coin_scan={"fired": False, "stage": "weekly", "reason": "neutral", "bias": "neutral"},
        capital_usd=10000.0,
    )
    assert result["recommendation"] == "stand_aside"
    assert result["stage"] == "weekly"


def test_recommend_position_rejects_bad_inputs() -> None:
    integration = HermesNaveIntegration()
    entry = _fired_scan_entry()

    with pytest.raises(HermesIntegrationError):
        integration.recommend_position(coin_scan=entry, capital_usd=0)
    with pytest.raises(HermesIntegrationError):
        integration.recommend_position(coin_scan=entry, capital_usd=100, leverage=100)
    with pytest.raises(HermesIntegrationError):
        integration.recommend_position(coin_scan=entry, capital_usd=100, risk_pct=0.5)


def test_scan_history_reads_reports_dir(tmp_path: Path) -> None:
    integration = HermesNaveIntegration()
    today = date.today()
    # Write two scans: today and yesterday
    for offset in (0, 1):
        day = today - timedelta(days=offset)
        path = tmp_path / f"daily_scan_{day.isoformat()}.json"
        path.write_text(
            json.dumps(
                {
                    "generated_at": f"{day.isoformat()}T00:00:00+00:00",
                    "scan": {
                        "generated_at": f"{day.isoformat()}T00:00:00+00:00",
                        "coins": {
                            "BTC": {"stage": "weekly_cot", "fired": False},
                            "ETH": {"stage": "weekly", "fired": False},
                        },
                        "summary": {"evaluated": ["BTC", "ETH"], "fires": []},
                    },
                }
            )
        )

    result = integration.scan_history(days=3, reports_dir=tmp_path)

    assert len(result["reports"]) == 2
    assert result["reports"][0]["date"] == today.isoformat()
    assert result["reports"][0]["stages"]["BTC"] == "weekly_cot"
    assert len(result["missing"]) == 1


def test_scan_history_rejects_out_of_range_days() -> None:
    integration = HermesNaveIntegration()
    with pytest.raises(HermesIntegrationError):
        integration.scan_history(days=0)
    with pytest.raises(HermesIntegrationError):
        integration.scan_history(days=100)
