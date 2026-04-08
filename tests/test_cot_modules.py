from __future__ import annotations

from trading.cot.cot_historical_analyzer import COTHistoricalAnalyzer
from trading.cot.cot_position_generator import COTPositionGenerator
from trading.cot.cot_report_generator import COTReportGenerator
from trading.services.cot_service import COTService


def _sample_sections() -> dict:
    return {
        "BTC": {
            "combined": {
                "net_commercial": 12000,
                "net_commercial_delta": 2400,
                "net_non_commercial": -9000,
                "net_non_commercial_delta": -600,
            }
        }
    }


def _sample_market() -> dict:
    return {
        "BTC": {
            "trend": "bullish",
            "price": 70000.0,
            "swing_high": 72000.0,
            "swing_low": 68000.0,
            "atr": 900.0,
        }
    }


def test_position_generator_uses_commercials_as_primary_bias() -> None:
    generator = COTPositionGenerator(default_risk_pct=0.01)
    weekly_plan = generator.generate_weekly_plan(
        cot_data={
            "BTC": {
                "combined": {
                    "net_commercial": 15000,
                    "net_commercial_delta": 1800,
                    "net_non_commercial": 8000,
                    "net_non_commercial_delta": 900,
                }
            }
        },
        market_data_4h=_sample_market(),
    )

    plan = weekly_plan["assets"]["BTC"]
    assert plan["bias"] == "bullish"
    assert "Commercials are net supportive" in plan["bias_explanation"]
    assert len(plan["setups"]) == 3


def test_position_generator_setup_payload_contains_actionable_fields() -> None:
    generator = COTPositionGenerator(default_risk_pct=0.01)
    weekly_plan = generator.generate_weekly_plan(
        cot_data=_sample_sections(),
        market_data_4h=_sample_market(),
        capital_usd=2000.0,
        leverage=10.0,
    )

    setup = weekly_plan["assets"]["BTC"]["setups"][0]
    assert "entry_zone" in setup
    assert "stop_loss" in setup
    assert "take_profit_levels" in setup
    assert len(setup["take_profit_levels"]) == 3
    assert "recommended_risk_pct" in setup
    assert setup["notional_usd_10x"] <= 20000.0


def test_historical_analyzer_returns_precise_calendar_ranges() -> None:
    analyzer = COTHistoricalAnalyzer()
    cot_data = {
        "BTC": {
            "as_of_date": "2026-03-31",
            "raw": [
                {
                    "report_date_as_yyyy_mm_dd": "2026-01-06",
                    "noncomm_positions_long_all": 1000,
                    "noncomm_positions_short_all": 800,
                    "comm_positions_long_all": 700,
                    "comm_positions_short_all": 900,
                    "open_interest_all": 5000,
                },
                {
                    "report_date_as_yyyy_mm_dd": "2026-03-03",
                    "noncomm_positions_long_all": 1200,
                    "noncomm_positions_short_all": 750,
                    "comm_positions_long_all": 690,
                    "comm_positions_short_all": 960,
                    "open_interest_all": 5200,
                },
                {
                    "report_date_as_yyyy_mm_dd": "2026-03-24",
                    "noncomm_positions_long_all": 1250,
                    "noncomm_positions_short_all": 740,
                    "comm_positions_long_all": 680,
                    "comm_positions_short_all": 980,
                    "open_interest_all": 5300,
                },
                {
                    "report_date_as_yyyy_mm_dd": "2026-03-31",
                    "noncomm_positions_long_all": 1300,
                    "noncomm_positions_short_all": 700,
                    "comm_positions_long_all": 670,
                    "comm_positions_short_all": 1020,
                    "open_interest_all": 5500,
                },
            ],
        }
    }

    report = analyzer.generate_historical_variation(months=3, cot_data=cot_data)
    rows = report["assets"]["BTC"]
    assert rows[0]["period"] == "Last Week"
    assert rows[0]["start_date"] == "2026-03-24"
    assert rows[0]["end_date"] == "2026-03-31"
    assert rows[1]["period"] == "Last 1 Month"


def test_report_generator_formats_trader_counts() -> None:
    reporter = COTReportGenerator()
    lines = reporter.format_section_lines(
        {
            "net_non_commercial": 1500,
            "net_non_commercial_delta": 200,
            "net_commercial": -1800,
            "net_commercial_delta": -220,
            "open_interest": 6400,
            "open_interest_delta": 300,
            "pct_oi": 23.4,
            "traders_non_commercial": 48,
            "traders_commercial": 36,
        }
    )
    assert any("# Traders: Non-Comm: 48 | Commercial: 36" in line for line in lines)


def test_cot_service_weekly_plan_json_contract(monkeypatch) -> None:
    service = COTService()

    def fake_fetch_latest_cot(*, report_type: str, **kwargs):
        base = {
            "as_of_date": "2026-03-31",
            "latest_date": "2026-03-31",
            "release_date": "2026-04-03",
            "cached": False,
            "raw": [
                {
                    "report_date_as_yyyy_mm_dd": "2026-03-24",
                    "noncomm_positions_long_all": 1000,
                    "noncomm_positions_short_all": 1100,
                    "comm_positions_long_all": 800,
                    "comm_positions_short_all": 700,
                    "open_interest_all": 5000,
                },
                {
                    "report_date_as_yyyy_mm_dd": "2026-03-31",
                    "noncomm_positions_long_all": 1200,
                    "noncomm_positions_short_all": 1400,
                    "comm_positions_long_all": 900,
                    "comm_positions_short_all": 650,
                    "open_interest_all": 5300,
                },
            ],
        }
        if report_type == "futures_only":
            return {"BTC": base}
        return {"BTC": base}

    class FakeClient:
        def __init__(self, wallet_name=None, testnet=True):
            pass

        def get_historical_candles(self, **kwargs):
            return [
                {"close": 69000, "high": 69500, "low": 68500},
                {"close": 69200, "high": 69800, "low": 68800},
                {"close": 69400, "high": 70100, "low": 69100},
                {"close": 69800, "high": 70400, "low": 69400},
                {"close": 70100, "high": 70800, "low": 69700},
                {"close": 70300, "high": 71000, "low": 69900},
                {"close": 70500, "high": 71200, "low": 70100},
                {"close": 70600, "high": 71400, "low": 70200},
                {"close": 70800, "high": 71500, "low": 70300},
                {"close": 70900, "high": 71600, "low": 70400},
                {"close": 71100, "high": 71800, "low": 70600},
                {"close": 71300, "high": 72000, "low": 70700},
                {"close": 71400, "high": 72100, "low": 70800},
                {"close": 71600, "high": 72200, "low": 70900},
                {"close": 71800, "high": 72400, "low": 71000},
                {"close": 71900, "high": 72500, "low": 71100},
                {"close": 72000, "high": 72600, "low": 71200},
                {"close": 72100, "high": 72700, "low": 71300},
            ]

    monkeypatch.setattr("trading.services.cot_service.fetch_latest_cot", fake_fetch_latest_cot)
    monkeypatch.setattr("trading.services.cot_service.HyperliquidClient", FakeClient)

    payload = service.get_weekly_plan(coins="BTC", capital_usd=2000.0, leverage=10.0)

    assert "generated_at" in payload
    assert "assets" in payload
    assert "BTC" in payload["assets"]
    assert "report_markdown" in payload
