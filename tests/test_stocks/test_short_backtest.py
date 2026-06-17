from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from trading.stocks.ondo_universe import ONDO_STOCK_PERP_UNIVERSE, is_ondo_stock_perp
from trading.stocks.price_provider import StaticPriceProvider, YFinancePriceProvider
from trading.stocks.short_backtest import ISMShortBacktester


def _price_series(start: str, prices: list[float]) -> pd.Series:
    idx = pd.date_range(start, periods=len(prices), freq="D", tz="UTC")
    return pd.Series(prices, index=idx, dtype=float)


def test_ondo_universe_covers_default_screening_basket() -> None:
    assert "NUE" in ONDO_STOCK_PERP_UNIVERSE
    assert is_ondo_stock_perp("nue") is True
    assert is_ondo_stock_perp("ZZZZ") is False


def test_short_backtest_uses_fixture_snapshots_and_static_prices(tmp_path: Path) -> None:
    snapshot = {
        "report_month": "March 2026",
        "kind": "manufacturing",
        "candidates": {
            "shorts": [
                {
                    "symbol": "GIS",
                    "side": "short",
                    "sector": "Consumer Staples",
                    "confidence": 0.9,
                    "score": 0.2,
                }
            ]
        },
    }
    (tmp_path / "ism_manufacturing_2026-03.json").write_text(json.dumps(snapshot))
    april = {
        "report_month": "April 2026",
        "kind": "manufacturing",
        "candidates": {"shorts": []},
    }
    (tmp_path / "ism_manufacturing_2026-04.json").write_text(json.dumps(april))

    prices = {
        "GIS": pd.Series(
            {
                pd.Timestamp("2026-04-01", tz="UTC"): 100.0,
                pd.Timestamp("2026-05-01", tz="UTC"): 90.0,
            },
            dtype=float,
        ),
    }
    backtester = ISMShortBacktester(price_provider=StaticPriceProvider(prices))
    payload = backtester.evaluate(
        snapshot_dir=tmp_path,
        kinds=["manufacturing"],
        from_month="2026-03",
        to_month="2026-04",
        min_confidence=0.3,
        ondo_only=True,
    )

    assert payload["summary"]["trade_count"] >= 1
    trade = payload["trades"][0]
    assert trade["symbol"] == "GIS"
    assert trade["return_pct"] > 0
    assert trade["ondo_perp"] is True
    assert trade["entry_rule"].startswith("Enter short")
    assert trade["entry_price"] == 100.0
    assert trade["target"]["price"] == 85.0
    assert trade["stop"]["price"] == 108.0
    assert trade["holding_window_days"] > 0
    assert trade["risk_pct"] == 0.01
    assert trade["max_leverage"] == 1.0
    assert trade["trade_plan"]["entry_price"] == trade["entry_price"]
    assert trade["exit_reason"] == "time_exit"


def test_short_backtest_filters_non_ondo_when_enabled(tmp_path: Path) -> None:
    snapshot = {
        "report_month": "March 2026",
        "kind": "manufacturing",
        "candidates": {
            "shorts": [
                {
                    "symbol": "ZZZZ",
                    "side": "short",
                    "sector": "Unknown",
                    "confidence": 0.9,
                    "score": -0.2,
                }
            ]
        },
    }
    (tmp_path / "ism_manufacturing_2026-03.json").write_text(json.dumps(snapshot))
    backtester = ISMShortBacktester(price_provider=StaticPriceProvider({}))
    payload = backtester.evaluate(
        snapshot_dir=tmp_path,
        kinds=["manufacturing"],
        from_month="2026-03",
        to_month="2026-03",
        ondo_only=True,
    )
    assert payload["summary"]["trade_count"] == 0


def test_short_backtest_exits_at_target_before_next_release(tmp_path: Path) -> None:
    snapshot = {
        "report_month": "March 2026",
        "kind": "manufacturing",
        "candidates": {
            "shorts": [
                {
                    "symbol": "GIS",
                    "side": "short",
                    "sector": "Consumer Staples",
                    "confidence": 0.9,
                    "score": 0.2,
                }
            ]
        },
    }
    (tmp_path / "ism_manufacturing_2026-03.json").write_text(json.dumps(snapshot))
    (tmp_path / "ism_manufacturing_2026-04.json").write_text(
        json.dumps({"report_month": "April 2026", "kind": "manufacturing", "candidates": {"shorts": []}})
    )
    prices = {"GIS": _price_series("2026-04-01", [100.0, 84.0, 82.0, 90.0])}

    payload = ISMShortBacktester(price_provider=StaticPriceProvider(prices)).evaluate(
        snapshot_dir=tmp_path,
        kinds=["manufacturing"],
        from_month="2026-03",
        to_month="2026-04",
        ondo_only=True,
    )

    trade = payload["trades"][0]
    assert trade["exit_reason"] == "target"
    assert trade["exit_date"] == "2026-04-02"
    assert trade["return_pct"] == 16.0


def test_short_backtest_exits_at_stop_before_next_release(tmp_path: Path) -> None:
    snapshot = {
        "report_month": "March 2026",
        "kind": "manufacturing",
        "candidates": {
            "shorts": [
                {
                    "symbol": "GIS",
                    "side": "short",
                    "sector": "Consumer Staples",
                    "confidence": 0.9,
                    "score": 0.2,
                }
            ]
        },
    }
    (tmp_path / "ism_manufacturing_2026-03.json").write_text(json.dumps(snapshot))
    (tmp_path / "ism_manufacturing_2026-04.json").write_text(
        json.dumps({"report_month": "April 2026", "kind": "manufacturing", "candidates": {"shorts": []}})
    )
    prices = {"GIS": _price_series("2026-04-01", [100.0, 109.0, 80.0])}

    payload = ISMShortBacktester(price_provider=StaticPriceProvider(prices)).evaluate(
        snapshot_dir=tmp_path,
        kinds=["manufacturing"],
        from_month="2026-03",
        to_month="2026-04",
        ondo_only=True,
    )

    trade = payload["trades"][0]
    assert trade["exit_reason"] == "stop"
    assert trade["exit_date"] == "2026-04-02"
    assert trade["return_pct"] == -9.0


def test_short_backtest_filters_non_deteriorating_short_scores(tmp_path: Path) -> None:
    snapshot = {
        "report_month": "March 2026",
        "kind": "manufacturing",
        "candidates": {
            "shorts": [
                {
                    "symbol": "GIS",
                    "side": "short",
                    "sector": "Consumer Staples",
                    "confidence": 0.9,
                    "score": 0.0,
                },
                {
                    "symbol": "CPB",
                    "side": "short",
                    "sector": "Consumer Staples",
                    "confidence": 0.9,
                    "score": 0.2,
                },
            ]
        },
    }
    (tmp_path / "ism_manufacturing_2026-03.json").write_text(json.dumps(snapshot))
    (tmp_path / "ism_manufacturing_2026-04.json").write_text(
        json.dumps({"report_month": "April 2026", "kind": "manufacturing", "candidates": {"shorts": []}})
    )
    prices = {
        "GIS": _price_series("2026-04-01", [100.0, 95.0]),
        "CPB": _price_series("2026-04-01", [50.0, 45.0]),
    }

    payload = ISMShortBacktester(price_provider=StaticPriceProvider(prices)).evaluate(
        snapshot_dir=tmp_path,
        kinds=["manufacturing"],
        from_month="2026-03",
        to_month="2026-04",
        min_short_score=0.0,
        ondo_only=True,
    )

    assert [trade["symbol"] for trade in payload["trades"]] == ["CPB"]


def test_short_backtest_research_mode_includes_threshold_equality(tmp_path: Path) -> None:
    snapshot = {
        "report_month": "March 2026",
        "kind": "manufacturing",
        "candidates": {
            "shorts": [
                {
                    "symbol": "GIS",
                    "side": "short",
                    "sector": "Consumer Staples",
                    "confidence": 0.9,
                    "score": 0.0,
                }
            ]
        },
    }
    (tmp_path / "ism_manufacturing_2026-03.json").write_text(json.dumps(snapshot))
    (tmp_path / "ism_manufacturing_2026-04.json").write_text(
        json.dumps({"report_month": "April 2026", "kind": "manufacturing", "candidates": {"shorts": []}})
    )
    prices = {
        "GIS": _price_series("2026-04-01", [100.0, 95.0]),
    }

    payload = ISMShortBacktester(price_provider=StaticPriceProvider(prices)).evaluate(
        snapshot_dir=tmp_path,
        kinds=["manufacturing"],
        from_month="2026-03",
        to_month="2026-04",
        min_short_score=0.0,
        research_mode=True,
        ondo_only=True,
    )

    assert [trade["symbol"] for trade in payload["trades"]] == ["GIS"]
    assert payload["lookback"]["research_mode"] is True


def test_short_backtest_defaults_to_latest_six_month_context(tmp_path: Path) -> None:
    for month_name, month_key in (
        ("December 2025", "2025-12"),
        ("January 2026", "2026-01"),
        ("February 2026", "2026-02"),
        ("March 2026", "2026-03"),
        ("April 2026", "2026-04"),
        ("May 2026", "2026-05"),
    ):
        snapshot = {
            "report_month": month_name,
            "kind": "manufacturing",
            "candidates": {
                "shorts": [
                    {
                        "symbol": "GIS",
                        "side": "short",
                        "sector": "Consumer Staples",
                        "confidence": 0.9,
                        "score": 0.2,
                        "short_quality_score": 0.7,
                    }
                ]
            },
        }
        (tmp_path / f"ism_manufacturing_{month_key}.json").write_text(
            json.dumps(snapshot)
        )

    prices = {
        "GIS": pd.Series(
            {
                pd.Timestamp("2026-01-05", tz="UTC"): 120.0,
                pd.Timestamp("2026-02-02", tz="UTC"): 118.0,
                pd.Timestamp("2026-03-02", tz="UTC"): 116.0,
                pd.Timestamp("2026-04-01", tz="UTC"): 114.0,
                pd.Timestamp("2026-05-01", tz="UTC"): 112.0,
                pd.Timestamp("2026-06-01", tz="UTC"): 110.0,
            },
            dtype=float,
        )
    }

    payload = ISMShortBacktester(price_provider=StaticPriceProvider(prices)).evaluate(
        snapshot_dir=tmp_path,
        kinds=["manufacturing"],
        ondo_only=True,
    )

    assert payload["lookback"]["from_month"] == "2025-12"
    assert payload["lookback"]["to_month"] == "2026-05"
    assert payload["lookback"]["latest_months"] == 6
    assert [row["covers_month"] for row in payload["snapshots_used"]] == [
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
    ]
    assert payload["trades"][0]["short_quality_score"] == 0.7


def test_yfinance_provider_handles_single_symbol_multiindex(monkeypatch) -> None:
    idx = pd.date_range("2026-04-01", periods=2, freq="D")
    raw = pd.DataFrame(
        {
            ("GIS", "Open"): [99.0, 98.0],
            ("GIS", "Close"): [100.0, 90.0],
        },
        index=idx,
    )

    def fake_download(**kwargs):  # noqa: ARG001
        return raw

    import yfinance as yf

    monkeypatch.setattr(yf, "download", fake_download)
    prices = YFinancePriceProvider().fetch_daily_closes(
        ["GIS"],
        start=idx[0].date(),
        end=idx[-1].date(),
    )

    assert list(prices) == ["GIS"]
    assert prices["GIS"].tolist() == [100.0, 90.0]
