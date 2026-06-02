"""Tests for S&P top-40 ticker playbook registry."""

from __future__ import annotations

import json
from pathlib import Path

from options.ticker_registry import (
    RegistryPaths,
    analyze_price_behavior,
    build_ticker_profile,
    load_ticker_profile,
    summarize_setup_performance,
    x_opinion_block,
)
from trading.stocks.x_interest import build_x_market_view


def test_summarize_setup_performance_picks_best_strategy() -> None:
    rows = [
        {
            "ticker": "WFC",
            "status": "trade_candidate",
            "strategy_name": "bull_put_credit_spread",
            "profitable": True,
            "mark": {"pnl_dollars": 50.0},
            "entry_metrics": {"pop": 80.0, "probability_of_touch": 40.0},
        },
        {
            "ticker": "WFC",
            "status": "trade_candidate",
            "strategy_name": "bull_put_credit_spread",
            "profitable": True,
            "mark": {"pnl_dollars": 30.0},
            "entry_metrics": {"pop": 75.0, "probability_of_touch": 45.0},
        },
        {
            "ticker": "WFC",
            "status": "trade_candidate",
            "strategy_name": "bear_call_credit_spread",
            "profitable": False,
            "mark": {"pnl_dollars": -100.0},
            "entry_metrics": {"pop": 70.0, "probability_of_touch": 50.0},
        },
    ]
    summary = summarize_setup_performance(rows, "WFC")
    assert summary["best_strategy"] == "bull_put_credit_spread"
    assert summary["best_win_rate"] == 1.0
    assert "bull_put" in summary["recommendation"]


def test_analyze_price_behavior_on_synthetic_series() -> None:
    import pandas as pd

    idx = pd.date_range("2025-01-01", periods=120, freq="D")
    # uptrend
    prices = pd.Series(range(100, 220), index=idx, dtype=float)
    block = analyze_price_behavior(prices)
    assert block["status"] == "ok"
    assert block["bias_20d"] == "bullish"
    assert block["return_20d_pct"] is not None


def test_build_and_load_profile(tmp_path: Path) -> None:
    import pandas as pd

    paths = RegistryPaths(tmp_path / "registry")
    idx = pd.date_range("2025-01-01", periods=90, freq="D")
    series = pd.Series([100.0 + i * 0.5 for i in range(90)], index=idx)
    profile = build_ticker_profile(
        "TEST",
        price_series=series,
        replay_rows=[],
        x_index={
            "TEST": build_x_market_view(
                "TEST",
                [{"text": "Buy under $100 target $120 bullish"}],
                {"post_count": 1, "total_likes": 50},
                snapshot_date="2026-05-01",
            ),
        },
    )
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.ticker_path("TEST").write_text(json.dumps(profile), encoding="utf-8")

    loaded = load_ticker_profile("TEST", paths=paths)
    assert loaded is not None
    assert loaded["playbook"]["bias_20d"] == "bullish"
    assert loaded["x_opinion"]["status"] == "ok"
    assert loaded["congress_holdings"]["role"] == "institutional_sentiment_proxy"


def test_x_opinion_no_cache() -> None:
    from options.ticker_registry import x_opinion_block

    block = x_opinion_block(None)
    assert block["status"] == "skipped"