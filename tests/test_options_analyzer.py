from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import options.analyzer as analyzer_module
from options.analyzer import OptionsAnalyzer
from options.config import OptionsConfig


class _DummyFetcher:
    def __init__(self, config: OptionsConfig):
        _ = config


def _config(tmp_path: Path) -> OptionsConfig:
    cache_root = tmp_path / "options_cache"
    return OptionsConfig(
        cache_root=cache_root,
        sqlite_path=cache_root / "options_cache.sqlite",
        snapshots_dir=cache_root / "snapshots",
        charts_dir=cache_root / "charts",
        reports_dir=cache_root / "reports",
    )


def _sample_chain() -> pd.DataFrame:
    expiration = (datetime.now(timezone.utc) +
                  timedelta(days=35)).date().isoformat()
    rows: list[dict[str, object]] = []
    for strike in [90.0, 95.0, 100.0, 105.0, 110.0]:
        rows.append(
            {
                "ticker": "MSFT",
                "contract_symbol": f"MSFTC{int(strike)}",
                "option_type": "call",
                "expiration": expiration,
                "strike": strike,
                "last_price": max(0.5, 12.0 - abs(100.0 - strike)),
                "bid": max(0.4, 11.8 - abs(100.0 - strike)),
                "ask": max(0.6, 12.2 - abs(100.0 - strike)),
                "mid_price": max(0.5, 12.0 - abs(100.0 - strike)),
                "volume": 220,
                "open_interest": 800,
                "implied_volatility": 0.25,
                "in_the_money": strike < 100.0,
                "last_trade_date": "2026-05-10",
                "spread_pct": 0.08,
                "liquidity_score": 500.0,
            }
        )
        rows.append(
            {
                "ticker": "MSFT",
                "contract_symbol": f"MSFTP{int(strike)}",
                "option_type": "put",
                "expiration": expiration,
                "strike": strike,
                "last_price": max(0.5, 12.0 - abs(100.0 - strike)),
                "bid": max(0.4, 11.8 - abs(100.0 - strike)),
                "ask": max(0.6, 12.2 - abs(100.0 - strike)),
                "mid_price": max(0.5, 12.0 - abs(100.0 - strike)),
                "volume": 220,
                "open_interest": 800,
                "implied_volatility": 0.28,
                "in_the_money": strike > 100.0,
                "last_trade_date": "2026-05-10",
                "spread_pct": 0.08,
                "liquidity_score": 500.0,
            }
        )
    return pd.DataFrame(rows)


def test_options_analyzer_run_returns_expected_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        analyzer_module, "YFinanceOptionsFetcher", _DummyFetcher)

    analyzer = OptionsAnalyzer(config=_config(tmp_path))
    frame = _sample_chain()

    monkeypatch.setattr(
        analyzer,
        "_load_or_fetch",
        lambda ticker: (
            frame,
            100.0,
            sorted(frame["expiration"].unique().tolist()),
            {"used_cache": False, "metadata": {"ticker": ticker}},
        ),
    )
    monkeypatch.setattr(
        analyzer,
        "_underlying_history",
        lambda ticker: pd.Series(np.linspace(80.0, 102.0, 365)),
    )
    monkeypatch.setattr(analyzer_module, "build_payoff_chart",
                        lambda **kwargs: str(tmp_path / "payoff.html"))
    monkeypatch.setattr(analyzer_module, "build_greeks_chart",
                        lambda **kwargs: str(tmp_path / "greeks.html"))
    monkeypatch.setattr(
        analyzer_module,
        "build_pnl_distribution_chart",
        lambda **kwargs: str(tmp_path / "monte_carlo.html"),
    )
    monkeypatch.setattr(
        analyzer_module,
        "build_strategy_ranking_chart",
        lambda **kwargs: str(tmp_path / "ranking.html"),
    )

    payload = analyzer.run(ticker="MSFT", days_to_exp=30)

    assert payload["ticker"] == "MSFT"
    assert "underlying_analysis" in payload
    assert "expected_move" in payload["underlying_analysis"]
    assert payload["underlying_analysis"]["expected_move"]["horizon_days"] == 30
    assert "options_market_snapshot" in payload["underlying_analysis"]
    snapshot = payload["underlying_analysis"]["options_market_snapshot"]
    assert snapshot["contracts"] > 0
    assert snapshot["calls"] > 0
    assert snapshot["puts"] > 0
    assert len(payload["recommendations"]) == 3
    first_metrics = payload["recommendations"][0]["metrics"]
    assert "expected_profit" in first_metrics
    assert "expected_loss" in first_metrics
    assert "probability_of_touch" in first_metrics
    assert "profit_range_low" in first_metrics
    assert "profit_range_high" in first_metrics
    assert payload["recommendations"][0]["tradeoff_comment"]
    assert set(payload["charts"].keys()) == {
        "payoff", "greeks", "monte_carlo", "strategy_ranking"}
