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
from trading.stocks.ism_calendar import ISMCalendarRelease
from trading.theory_v2 import TheoryV2Decision

runner = CliRunner()


def test_list_tools_contains_required_toolset() -> None:
    integration = HermesNaveIntegration()
    payload = integration.list_tools()

    assert payload["skill"]["name"] == "nave_trading"
    tool_names = {tool["name"] for tool in payload["tools"]}
    assert {
        "momentum_scan",
        "momentum_zone_watch",
        "market_scan",
        "momentum_playbook",
        "market_playbook",
        "options_scan",
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

    monkeypatch.setattr(
        "trading.theory_v2.build_signals_for_coins", fake_build)

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


def test_momentum_scan_routes_through_service(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    def fake_scan_live(self, **kwargs):
        return {
            "strategy": "derivatives_momentum_v1",
            "symbols": ["BTCUSDT"],
            "summary": {"tradeable_count": 1},
            "results": {"BTCUSDT": {"plans": [], "tradeable": []}},
        }

    monkeypatch.setattr(
        "trading.crypto.momentum.service.MomentumMarketService.scan_live", fake_scan_live)
    monkeypatch.setattr(
        "trading.crypto.momentum.formatters.render_momentum_scan_markdown_v2",
        lambda payload: ["*digest*"]
    )
    payload = integration.momentum_scan(symbols="BTCUSDT")

    assert payload["strategy"] == "derivatives_momentum_v1"
    assert payload["summary"]["tradeable_count"] == 1
    assert payload["telegram_markdown_v2"] == ["*digest*"]


def test_momentum_playbook_validates_side(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    with pytest.raises(HermesIntegrationError):
        integration.momentum_playbook(symbol="BTCUSDT", side="flat")


def test_dispatch_tool_call_routes_momentum_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    monkeypatch.setattr(
        integration,
        "momentum_scan",
        lambda **kwargs: {"strategy": "derivatives_momentum_v1",
                          "args": kwargs},
    )
    result = integration.dispatch_tool_call(
        "momentum_scan",
        {"symbols": "BTCUSDT", "tf": "4h,1h"},
    )

    assert result["ok"] is True
    assert result["tool"] == "momentum_scan"
    assert result["result"]["args"]["symbols"] == "BTCUSDT"


def test_dispatch_tool_call_routes_options_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    monkeypatch.setattr(
        integration,
        "options_scan",
        lambda **kwargs: {"ticker": "MSFT",
                          "args": kwargs, "recommendations": []},
    )
    result = integration.dispatch_tool_call(
        "options_scan",
        {"ticker": "MSFT", "days_to_exp": 30},
    )

    assert result["ok"] is True
    assert result["tool"] == "options_scan"
    assert result["result"]["ticker"] == "MSFT"
    assert result["result"]["args"]["days_to_exp"] == 30


def test_dispatch_tool_call_routes_momentum_zone_watch(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    monkeypatch.setattr(
        integration,
        "momentum_zone_watch",
        lambda **kwargs: {"alert_count": 0, "args": kwargs},
    )
    result = integration.dispatch_tool_call(
        "momentum_zone_watch",
        {"symbols": "BTCUSDT", "score_threshold": 80},
    )

    assert result["ok"] is True
    assert result["tool"] == "momentum_zone_watch"
    assert result["result"]["args"]["score_threshold"] == 80


def test_momentum_zone_watch_exposes_active_watch_state(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    def fake_scan_live(self, **kwargs):
        return {
            "summary": {"tradeable_count": 0},
            "results": {
                "BTCUSDT": {
                    "plans": [
                        {
                            "side": "long",
                            "confidence_score": 84,
                            "entry_zone": [82550.0, 83800.0],
                            "invalidation": 82480.0,
                            "rr_estimated": 4.63,
                            "setup_status": "pending",
                        }
                    ],
                    "tradeable": [],
                }
            },
        }

    def fake_evaluate(self, candidates, *, price_lookup, now=None):
        return {
            "generated_at": "2026-05-08T12:00:00+00:00",
            "candidates": len(candidates),
            "alerts": [],
            "alert_count": 0,
            "watch_states": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_zone": [81112.86, 82479.0],
                    "scan_entry_zone": [82550.0, 83800.0],
                    "invalidation": 81052.5,
                    "scan_invalidation": 82480.0,
                    "confidence_score": 84,
                    "rr_estimated": 4.63,
                    "setup_status": "pending",
                    "watch_status": "holding_previous",
                    "price": 82300.0,
                    "inside": True,
                    "invalidated": False,
                }
            ],
        }

    monkeypatch.setattr(
        "trading.crypto.momentum.service.MomentumMarketService.scan_live", fake_scan_live,
    )
    monkeypatch.setattr(
        "trading.alerts.entry_zone_monitor.EntryZoneMonitor.evaluate", fake_evaluate,
    )
    monkeypatch.setattr(
        "trading.crypto.client.HyperliquidClient.get_mid", lambda self, coin: 82300.0,
    )

    payload = integration.momentum_zone_watch(
        symbols="BTCUSDT", score_threshold=75)

    assert payload["watch_candidates"][0]["entry_zone"] == [81112.86, 82479.0]
    assert payload["watch_candidates"][0]["scan_entry_zone"] == [
        82550.0, 83800.0]
    assert payload["watch_candidates"][0]["watch_status"] == "holding_previous"


def test_market_scan_alias_routes_to_momentum(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    monkeypatch.setattr(
        integration,
        "momentum_scan",
        lambda **kwargs: {"strategy": "derivatives_momentum_v1",
                          "args": kwargs},
    )
    result = integration.dispatch_tool_call(
        "market_scan",
        {"symbols": "BTCUSDT", "tf": "4h,1h"},
    )

    assert result["ok"] is True
    assert result["tool"] == "market_scan"
    assert result["result"]["strategy"] == "derivatives_momentum_v1"


def test_market_playbook_alias_routes_to_momentum(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    monkeypatch.setattr(
        integration,
        "momentum_playbook",
        lambda **kwargs: {"strategy": "derivatives_momentum_v1",
                          "plan": {"side": kwargs["side"]}},
    )
    result = integration.dispatch_tool_call(
        "market_playbook",
        {"symbol": "ETHUSDT", "side": "short"},
    )

    assert result["ok"] is True
    assert result["tool"] == "market_playbook"
    assert result["result"]["plan"]["side"] == "short"


def test_dispatch_tool_call_routes_stocks_ism_report(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    def fake_stocks_report(**kwargs):
        return {"kind": "manufacturing", "criteria": kwargs, "summary": {"expanding_candidates": 1}}

    monkeypatch.setattr(integration, "stocks_ism_report", fake_stocks_report)
    result = integration.dispatch_tool_call(
        "stocks_ism_report",
        {"kind": "manufacturing", "top_n": 3},
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


def test_stocks_ism_report_propagates_freshness_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration = HermesNaveIntegration()

    monkeypatch.setattr(
        "trading.stocks.reporting.build_ism_industry_report",
        lambda **kwargs: {
            "kind": kwargs.get("kind", "services"),
            "report_month": "March 2026",
            "report_month_key": "2026-03",
            "expected_covers_month": "2026-04",
            "is_expected_month": False,
            "freshness_status": "stale",
            "criteria": {"top_n": kwargs.get("top_n", 5)},
        },
    )

    payload = integration.stocks_ism_report(kind="services", top_n=5)
    assert payload["freshness_status"] == "stale"
    assert payload["expected_covers_month"] == "2026-04"
    assert payload["report_month_key"] == "2026-03"


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
        coin_scan={"fired": False, "stage": "weekly",
                   "reason": "neutral", "bias": "neutral"},
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
        integration.recommend_position(
            coin_scan=entry, capital_usd=100, leverage=100)
    with pytest.raises(HermesIntegrationError):
        integration.recommend_position(
            coin_scan=entry, capital_usd=100, risk_pct=0.5)


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


def test_stocks_politicians_scan_adds_telegram_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration = HermesNaveIntegration()

    payload = {
        "generated_at": "2026-05-06T20:01:00+00:00",
        "new_total": 1,
        "summary": {"by_chamber": {"house": 1, "senate": 0}},
        "new_trades": [
            {
                "chamber": "house",
                "symbol": "NVDA",
                "politician": "Jane Doe",
                "state": "CA",
                "amount_range": "$1,001 - $15,000",
                "transaction_date": "2026-05-01",
                "disclosure_date": "2026-05-06",
                "link": "https://example.test/filing",
            }
        ],
    }

    monkeypatch.setattr(
        "trading.stocks.politicians.scanner.run_daily_scan",
        lambda persist=True: payload,
    )

    result = integration.stocks_politicians_scan(persist=False)

    assert result["new_total"] == 1
    assert isinstance(result["telegram_markdown_v2"], list)
    assert result["telegram_markdown_v2"]
    assert "NAVE STOCK Act" in result["telegram_markdown_v2"][0]


def test_stocks_politicians_scan_empty_digest_when_no_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration = HermesNaveIntegration()

    payload = {
        "generated_at": "2026-05-06T20:01:00+00:00",
        "new_total": 0,
        "summary": {},
        "new_trades": [],
    }
    monkeypatch.setattr(
        "trading.stocks.politicians.scanner.run_daily_scan",
        lambda persist=True: payload,
    )

    result = integration.stocks_politicians_scan()
    assert result["telegram_markdown_v2"] == []


def test_stocks_ism_calendar_recent_days(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    monkeypatch.setattr(
        "trading.stocks.ism_calendar.recent_release",
        lambda **kwargs: ISMCalendarRelease(
            kind="services",
            release_at_utc="2026-05-05T14:00:00+00:00",
            release_date="2026-05-05",
            covers_month="2026-04",
            event="ISM Services PMI (Apr)",
            impact="High",
        ),
    )

    result = integration.stocks_ism_calendar(kind="services", recent_days=2)

    assert result["recent_days"] == 2
    assert result["recent_release"]["release_date"] == "2026-05-05"
    assert result["recent_release"]["covers_month"] == "2026-04"


def test_stocks_ism_calendar_rejects_invalid_recent_days() -> None:
    integration = HermesNaveIntegration()

    with pytest.raises(HermesIntegrationError):
        integration.stocks_ism_calendar(recent_days=-1)
    with pytest.raises(HermesIntegrationError):
        integration.stocks_ism_calendar(recent_days=31)
