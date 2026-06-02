"""Tests for hidden-gem scoring and X interest index."""

from __future__ import annotations

import json
from pathlib import Path

from options.gem_finder import (
    DEFAULT_FILTER,
    GemFilterConfig,
    bias_aligned,
    passes_gem_filters,
    rank_hidden_gems,
    score_gem_row,
    score_replay_row,
    summarize_filter_experiment,
)
from trading.stocks.x_interest import XInterestProfile, load_x_interest_index


def _scan_row(
    *,
    ticker: str = "WFC",
    open_rec: bool = True,
    pop: float = 72.0,
    touch: float = 40.0,
    bias: str = "bullish",
) -> dict:
    return {
        "ticker": ticker,
        "status": "trade_candidate",
        "trade_decision": {
            "status": "trade_candidate",
            "open_recommended": open_rec,
        },
        "executable_strategy": "bull_put_credit_spread",
        "executable_metrics": {
            "pop": pop,
            "probability_of_touch": touch,
            "expected_value": 120.0,
            "composite_score": 28.0,
        },
        "executable_setup": {"bias": bias},
    }


def test_score_gem_row_requires_open_recommended() -> None:
    assert score_gem_row(_scan_row(open_rec=False)) is None


def test_bear_call_blocked_by_default() -> None:
    row = _scan_row(ticker="BA", bias="bearish")
    row["executable_strategy"] = "bear_call_credit_spread"
    assert score_gem_row(row) is None


def test_bank_neutral_bull_put_allowed() -> None:
    row = _scan_row(ticker="WFC", bias="neutral", pop=78.0, touch=32.0)
    row["executable_metrics"]["composite_score"] = 36.0
    row["executable_metrics"]["expected_value"] = 150.0
    scored = score_gem_row(row)
    assert scored is not None
    assert scored["ticker"] == "WFC"


def test_high_vol_ticker_blocked() -> None:
    row = _scan_row(ticker="TSLA", pop=80.0, touch=30.0)
    assert score_gem_row(row) is None


def test_hidden_gem_ranks_non_mega_above_mega() -> None:
    x_index = {
        "WFC": XInterestProfile(
            ticker="WFC",
            post_count=12,
            engagement=500,
            sentiment="bullish",
            bullish_hits=5,
            bearish_hits=1,
            top_post_url=None,
            snapshot_date="2026-05-01",
        ),
    }
    scan = {
        "results": {
            "MSFT": _scan_row(ticker="MSFT", pop=80.0, touch=30.0),
            "WFC": _scan_row(ticker="WFC", pop=78.0, touch=32.0),
        }
    }
    wfc = scan["results"]["WFC"]
    wfc["executable_metrics"]["composite_score"] = 36.0
    wfc["executable_metrics"]["expected_value"] = 150.0
    ranked = rank_hidden_gems(scan, x_index=x_index, limit=5)
    gems = ranked["gems"]
    assert gems and gems[0]["ticker"] == "WFC"


def test_bias_aligned_banks_neutral() -> None:
    assert bias_aligned("bull_put_credit_spread", "neutral", ticker="WFC", allow_neutral_banks=True)
    assert not bias_aligned("bull_put_credit_spread", "neutral", ticker="XYZ", allow_neutral_banks=True)


def test_production_filter_beats_baseline_on_yearly_fixture() -> None:
    path = Path(__file__).resolve().parents[1] / "docs/analysis/raw/options_yearly_20260602T181813Z.json"
    if not path.is_file():
        return
    rows = json.loads(path.read_text())["rows"]
    baseline = GemFilterConfig(
        require_open_recommended=False,
        require_bias_aligned=False,
        allow_bear_calls=True,
        block_high_vol=False,
        min_structure=0.0,
        min_gem_score=0.0,
    )
    base_stats = summarize_filter_experiment(rows, baseline)
    prod_stats = summarize_filter_experiment(rows, DEFAULT_FILTER)
    assert prod_stats["win_rate"] >= base_stats["win_rate"]
    assert prod_stats["avg_pnl"] > base_stats["avg_pnl"]


def test_load_x_interest_index_from_fixture(tmp_path: Path) -> None:
    payload = {
        "summary_stats": {
            "PANW": {
                "post_count": 3,
                "total_likes": 40,
                "total_replies": 5,
                "total_retweets": 2,
                "top_post_url": "https://x.com/x/1",
            }
        },
        "posts_by_ticker": {
            "PANW": [
                {"text": "PANW looks bullish breakout buy the dip"},
            ]
        },
    }
    path = tmp_path / "x_analysis_2026-05-08_panw.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    index = load_x_interest_index(snapshot_dir=tmp_path)
    assert "PANW" in index
    assert index["PANW"].sentiment == "bullish"


def test_score_replay_row() -> None:
    row = {
        "status": "trade_candidate",
        "ticker": "JPM",
        "strategy_name": "bull_put_credit_spread",
        "directional_bias": "bullish",
        "entry_metrics": {
            "pop": 78.0,
            "probability_of_touch": 30.0,
            "expected_value": 120.0,
            "composite_score": 32.0,
        },
        "mark": {"pnl_dollars": 10.0},
        "profitable": True,
    }
    assert score_replay_row(row) is not None