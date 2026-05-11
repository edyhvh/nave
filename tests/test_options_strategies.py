from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from options.scoring import rank_recommendations
from options.strategies import build_strategy_candidates


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
