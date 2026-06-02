from __future__ import annotations

from datetime import date

import pandas as pd

from options.analysis_overlay import (
    _qualifies_mega_cap_income_pass,
    build_narrative_overlay,
    pick_directional_override,
    pick_primary_executable,
)
from options.models import StrategyCandidate, StrategyLeg
from options.replay import bs_option_price, mark_candidate_pnl, reprice_legs_bs


def _rec(name: str, *, score: float, ev: float, pop: float, touch: float, max_loss: float) -> dict:
    return {
        "strategy": {"name": name, "legs": [], "breakeven_points": [100.0]},
        "metrics": {
            "composite_score": score,
            "expected_value": ev,
            "pop": pop,
            "probability_of_touch": touch,
            "max_loss": max_loss,
            "theta_per_day": 0.05,
            "vega_exposure": 0.1,
            "risk_reward": 0.5,
        },
        "tradeoff_comment": "",
    }


def test_pick_primary_blocks_bear_call_when_neutral() -> None:
    bear_call = _rec("bear_call_credit_spread", score=50.0, ev=20.0, pop=65.0, touch=45.0, max_loss=400.0)
    chosen = pick_primary_executable(
        all_ranked=[bear_call],
        best_conservative=bear_call,
        best_aggressive=None,
        actionable_pool=[bear_call],
        flags_by_name={"bear_call_credit_spread": {}},
        iv_percentile=50.0,
        iv_rich=False,
        conservative_touch_max_pct=75.0,
        directional_bias="neutral",
    )
    assert chosen is None


def test_pick_primary_prefers_bull_put_over_long_strangle() -> None:
    bull_put = _rec("bull_put_credit_spread", score=42.0, ev=-10.0, pop=72.0, touch=40.0, max_loss=400.0)
    strangle = _rec("long_strangle", score=55.0, ev=120.0, pop=70.0, touch=60.0, max_loss=500.0)
    all_ranked = [strangle, bull_put]
    flags = {
        "bull_put_credit_spread": {},
        "long_strangle": {},
    }
    chosen = pick_primary_executable(
        all_ranked=all_ranked,
        best_conservative=bull_put,
        best_aggressive=strangle,
        actionable_pool=[bull_put, strangle],
        flags_by_name=flags,
        iv_percentile=90.0,
        iv_rich=True,
        conservative_touch_max_pct=75.0,
    )
    assert chosen is bull_put


def test_bs_option_price_positive_for_atm_call() -> None:
    px = bs_option_price(
        spot=100.0,
        strike=100.0,
        days_to_expiration=30,
        implied_volatility=0.25,
        option_type="call",
    )
    assert px > 1.0


def test_mega_cap_bull_put_pass_for_bullish_high_pop_low_touch() -> None:
    rec = _rec("bull_put_credit_spread", score=28.0, ev=-20.0, pop=72.0, touch=42.0, max_loss=400.0)
    assert _qualifies_mega_cap_income_pass(
        rec,
        directional_bias="bullish",
        underlying_price=420.0,
        flags={},
    )


def test_overlay_directional_override_when_gate_blocks_bull_put() -> None:
    bull_put = {
        "strategy": {
            "name": "bull_put_credit_spread",
            "legs": [
                {
                    "instrument_type": "option",
                    "side": "sell",
                    "quantity": 1,
                    "premium": 1.5,
                    "strike": 395.0,
                    "option_type": "put",
                },
                {
                    "instrument_type": "option",
                    "side": "buy",
                    "quantity": 1,
                    "premium": 1.0,
                    "strike": 390.0,
                    "option_type": "put",
                },
            ],
            "breakeven_points": [393.5],
        },
        "metrics": {
            "composite_score": 24.0,
            "pop": 68.0,
            "expected_value": -25.0,
            "probability_of_touch": 45.0,
            "theta_per_day": 0.05,
            "vega_exposure": 0.1,
            "risk_reward": 0.3,
            "max_loss": 350.0,
        },
        "tradeoff_comment": "",
    }
    overlay = build_narrative_overlay(
        ticker="MSFT",
        underlying_analysis={
            "price": 420.0,
            "directional_bias": "bullish",
            "historical_volatility": {"hv_30": 0.3},
            "implied_volatility": {"iv_mean": 0.32, "iv_rank": 40.0, "iv_percentile": 50.0},
            "expected_move": {"one_std_move": 40.0, "one_std_move_pct": 0.1},
            "hv_vs_iv": {"iv_rich_vs_hv_short": True},
            "put_call_skew": {"skew_diff": 0.02},
            "options_market_snapshot": {"put_call_oi_ratio": 1.0, "put_call_volume_ratio": 1.0},
        },
        all_ranked=[bull_put],
        prefer_directional_override=True,
        allow_mega_cap_income_pass=True,
    )
    assert overlay["trade_decision"]["status"] in {
        "trade_candidate",
        "directional_override",
    }
    assert overlay["final_recommendations"]["best_overall_executable_setup"] is not None


def test_iter_monthly_entry_dates_returns_sorted_pairs() -> None:
    from datetime import date

    from options.replay import iter_monthly_entry_dates

    pairs = iter_monthly_entry_dates(months=3, end=date(2026, 6, 15), hold_days=30)
    assert len(pairs) == 3
    assert pairs[0][0] < pairs[-1][0]


def test_summarize_yearly_high_odds_filter() -> None:
    from options.replay import summarize_yearly_backtest

    rows = [
        {
            "status": "trade_candidate",
            "ticker": "MSFT",
            "entry_date": "2025-06-01",
            "profitable": True,
            "strategy_name": "bull_put_credit_spread",
            "entry_metrics": {"pop": 70.0, "probability_of_touch": 40.0},
            "mark": {"pnl_dollars": 80.0, "pnl_pct_of_max_profit": 55.0},
        },
        {
            "status": "trade_candidate",
            "ticker": "XYZ",
            "entry_date": "2025-07-01",
            "profitable": False,
            "strategy_name": "bull_put_credit_spread",
            "entry_metrics": {"pop": 50.0, "probability_of_touch": 80.0},
            "mark": {"pnl_dollars": -50.0, "pnl_pct_of_max_loss": -20.0},
        },
    ]
    summary = summarize_yearly_backtest(rows, min_pop=60.0, max_touch=72.0, min_return_pct=40.0)
    assert summary["high_odds"]["trades"] == 1
    assert summary["high_odds"]["wins"] == 1
    assert summary["high_odds_high_return"]["count"] == 1


def test_mark_candidate_pnl_credit_spread_profit_when_short_leg_decays() -> None:
    expiration = "2026-07-18"
    candidate = StrategyCandidate(
        name="bull_put_credit_spread",
        expiration=expiration,
        days_to_expiration=30,
        legs=[
            StrategyLeg("option", "sell", 1, 2.0, 95.0, "put"),
            StrategyLeg("option", "buy", 1, 1.0, 90.0, "put"),
        ],
        net_premium=100.0,
        max_profit=100.0,
        max_loss=400.0,
        breakeven_points=[94.0],
    )
    entry_legs = reprice_legs_bs(
        candidate,
        spot=100.0,
        iv=0.25,
        days_to_expiration=30,
        risk_free_rate=0.04,
    )
    frame = pd.DataFrame(
        [
            {
                "expiration": expiration,
                "strike": 95.0,
                "option_type": "put",
                "mid_price": 0.5,
                "bid": 0.45,
                "ask": 0.55,
                "last_price": 0.5,
            },
            {
                "expiration": expiration,
                "strike": 90.0,
                "option_type": "put",
                "mid_price": 0.2,
                "bid": 0.15,
                "ask": 0.25,
                "last_price": 0.2,
            },
        ]
    )
    marks = mark_candidate_pnl(candidate, frame=frame, entry_legs=entry_legs)
    assert marks["pnl_dollars"] is not None
    assert float(marks["pnl_dollars"]) > 0.0