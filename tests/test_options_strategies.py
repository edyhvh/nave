from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from options import scoring
from options.models import StrategyCandidate
from options.scoring import rank_recommendations
from options.strategies import (
    build_strategy_candidates,
    build_strategy_candidates_with_audit,
)


def _sample_option_frame() -> pd.DataFrame:
    expiration = (datetime.now(timezone.utc) +
                  timedelta(days=32)).date().isoformat()
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
                "volume": 250,
                "open_interest": 900,
                "implied_volatility": 0.25,
                "in_the_money": strike < 100.0,
                "last_trade_date": "2026-05-10",
                "spread_pct": 0.08,
                "liquidity_score": 500.0,
                "delta": 0.5,
                "gamma": 0.02,
                "theta": -0.03,
                "vega": 0.12,
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
                "volume": 250,
                "open_interest": 900,
                "implied_volatility": 0.28,
                "in_the_money": strike > 100.0,
                "last_trade_date": "2026-05-10",
                "spread_pct": 0.08,
                "liquidity_score": 500.0,
                "delta": -0.5,
                "gamma": 0.02,
                "theta": -0.03,
                "vega": 0.12,
            }
        )
    return pd.DataFrame(rows)


def test_build_strategy_candidates_includes_core_set() -> None:
    frame = _sample_option_frame()
    candidates = build_strategy_candidates(
        frame, underlying_price=100.0, target_dte=30)

    names = {candidate.name for candidate in candidates}
    assert "covered_call" in names
    assert "cash_secured_put" in names
    assert "iron_condor" in names
    assert "long_straddle" in names
    assert "long_strangle" in names


def test_rank_recommendations_returns_top_three() -> None:
    frame = _sample_option_frame()
    candidates = build_strategy_candidates(
        frame, underlying_price=100.0, target_dte=30)

    ranked = rank_recommendations(
        candidates=candidates,
        option_frame=frame,
        underlying_price=100.0,
        iv_atm=0.26,
        top_n=3,
    )

    assert len(ranked) == 3
    assert all(0.0 <= rec.metrics.composite_score <= 100.0 for rec in ranked)
    assert all(0.0 <= rec.metrics.pop <= 100.0 for rec in ranked)
    assert all(0.0 <= rec.metrics.probability_of_touch <=
               100.0 for rec in ranked)
    assert all(rec.metrics.expected_profit >= 0.0 for rec in ranked)
    assert all(rec.metrics.expected_loss >= 0.0 for rec in ranked)
    assert all(rec.tradeoff_comment for rec in ranked)


def test_rank_recommendations_penalizes_negative_ev_more_in_high_iv(monkeypatch) -> None:
    frame = _sample_option_frame()
    candidates = [
        StrategyCandidate(
            name="positive_edge",
            expiration=frame.iloc[0]["expiration"],
            days_to_expiration=30,
            legs=[],
            net_premium=0.0,
            max_profit=120.0,
            max_loss=60.0,
            breakeven_points=[100.0],
        ),
        StrategyCandidate(
            name="negative_edge",
            expiration=frame.iloc[0]["expiration"],
            days_to_expiration=30,
            legs=[],
            net_premium=0.0,
            max_profit=250.0,
            max_loss=60.0,
            breakeven_points=[100.0],
        ),
    ]

    distributions = {
        "positive_edge": {
            "pop": 58.0,
            "expected_value": 22.0,
            "expected_profit": 61.0,
            "expected_loss": 19.0,
            "probability_of_touch": 42.0,
            "profit_range_low": 96.0,
            "profit_range_high": 109.0,
        },
        "negative_edge": {
            "pop": 75.0,
            "expected_value": -8.0,
            "expected_profit": 52.0,
            "expected_loss": 12.0,
            "probability_of_touch": 30.0,
            "profit_range_low": 92.0,
            "profit_range_high": 108.0,
        },
    }

    def _fake_distribution(candidate, underlying_price: float, implied_volatility: float):
        return distributions[candidate.name]

    monkeypatch.setattr(
        scoring, "evaluate_strategy_distribution", _fake_distribution)
    monkeypatch.setattr(scoring, "_aggregate_greek_exposure",
                        lambda option_frame, candidate: (0.0, 0.0))

    ranked_low_iv = scoring.rank_recommendations(
        candidates=candidates,
        option_frame=frame,
        underlying_price=100.0,
        iv_atm=0.26,
        iv_rank=20.0,
        iv_percentile=35.0,
        top_n=2,
    )
    ranked_high_iv = scoring.rank_recommendations(
        candidates=candidates,
        option_frame=frame,
        underlying_price=100.0,
        iv_atm=0.26,
        iv_rank=75.0,
        iv_percentile=85.0,
        top_n=2,
    )

    by_name_low = {rec.strategy.name: rec for rec in ranked_low_iv}
    by_name_high = {rec.strategy.name: rec for rec in ranked_high_iv}

    assert ranked_high_iv[0].strategy.name == "positive_edge"
    assert by_name_high["negative_edge"].metrics.composite_score < by_name_low["negative_edge"].metrics.composite_score


def test_build_strategy_candidates_with_audit_exposes_generation_details() -> None:
    frame = _sample_option_frame()
    candidates, audit = build_strategy_candidates_with_audit(
        frame,
        underlying_price=100.0,
        target_dte=30,
    )

    assert candidates
    assert audit["status"] == "ok"
    assert "template_config" in audit
    assert "strategy_generation" in audit
    bull_put_entries = [
        entry for entry in audit["strategy_generation"]
        if entry.get("strategy_family") == "bull_put_credit_spread"
    ]
    assert bull_put_entries
    assert bull_put_entries[0]["status"] in {"built", "dropped"}


def test_build_strategy_candidates_with_audit_returns_no_chain_status_on_empty_frame() -> None:
    candidates, audit = build_strategy_candidates_with_audit(
        pd.DataFrame(),
        underlying_price=100.0,
        target_dte=30,
    )

    assert candidates == []
    assert audit["status"] == "no_chain"
