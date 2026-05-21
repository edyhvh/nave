from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

import options.analyzer as analyzer_module
from options.analysis_overlay import build_narrative_overlay
from options.analyzer import OptionsAnalyzer
from options.config import OptionsConfig
from options.models import StrategyCandidate, StrategyLeg, StrategyMetrics, StrategyRecommendation


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
    assert "analysis_overlay" in payload
    assert "executive_summary" in payload["analysis_overlay"]
    assert "final_recommendations" in payload["analysis_overlay"]
    assert "all_recommendations_ranked" in payload
    assert payload["all_recommendations_ranked"]
    assert "generation_audit" in payload
    assert "strategy_generation" in payload["generation_audit"] or payload["generation_audit"].get(
        "status") == "no_chain"
    assert "ranking_audit" in payload["analysis_overlay"]
    assert "strategy_comparison_table" in payload["analysis_overlay"]
    assert set(payload["charts"].keys()) == {
        "payoff", "greeks", "monte_carlo", "strategy_ranking"}


def test_options_analyzer_can_evaluate_manual_bull_put(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        analyzer_module, "YFinanceOptionsFetcher", _DummyFetcher)

    analyzer = OptionsAnalyzer(config=_config(tmp_path))
    frame = _sample_chain()
    expiration = str(frame.iloc[0]["expiration"])

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

    payload = analyzer.run(
        ticker="MSFT",
        strategy="bull-put",
        expiration=expiration,
        short_put=100.0,
        long_put=95.0,
        short_premium=2.0,
        long_premium=0.7,
    )

    assert payload["generation_audit"]["status"] == "manual"
    manual = payload["underlying_analysis"]["manual_strategy"]
    assert manual["net_credit"] == 130.0
    assert manual["max_loss"] == 370.0
    rec = payload["all_recommendations_ranked"][0]
    assert rec["strategy"]["name"] == "bull_put_credit_spread"
    assert rec["strategy"]["legs"][0]["strike"] == 100.0
    assert rec["strategy"]["legs"][1]["strike"] == 95.0


def test_options_analyzer_overlay_can_prefer_bull_put_as_conservative_setup(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        analyzer_module, "YFinanceOptionsFetcher", _DummyFetcher)

    analyzer = OptionsAnalyzer(config=_config(tmp_path))
    frame = _sample_chain()

    monkeypatch.setattr(
        analyzer,
        "_load_or_fetch",
        lambda ticker: (
            frame,
            412.0,
            sorted(frame["expiration"].unique().tolist()),
            {"used_cache": False, "metadata": {"ticker": ticker}},
        ),
    )
    monkeypatch.setattr(
        analyzer,
        "_underlying_history",
        lambda ticker: pd.Series(np.linspace(360.0, 420.0, 365)),
    )
    monkeypatch.setattr(
        analyzer_module,
        "compute_put_call_skew",
        lambda option_frame, *, underlying_price: {
            "atm_put_iv": 0.33,
            "atm_call_iv": 0.29,
            "skew_diff": 0.04,
            "skew_ratio": 1.14,
        },
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

    expiration = frame.iloc[0]["expiration"]

    def _rec(
        *,
        name: str,
        composite_score: float,
        pop: float,
        expected_value: float,
        touch: float,
        theta_per_day: float,
        max_loss: float,
        breakeven_points: list[float],
        legs: list[StrategyLeg],
        tradeoff_comment: str,
    ) -> StrategyRecommendation:
        return StrategyRecommendation(
            strategy=StrategyCandidate(
                name=name,
                expiration=expiration,
                days_to_expiration=30,
                legs=legs,
                net_premium=250.0,
                max_profit=250.0,
                max_loss=max_loss,
                breakeven_points=breakeven_points,
            ),
            metrics=StrategyMetrics(
                pop=pop,
                expected_value=expected_value,
                expected_profit=max(0.0, expected_value + 60.0),
                expected_loss=max(0.0, abs(expected_value) + 20.0),
                risk_reward=1.2,
                max_loss=max_loss,
                theta_per_day=theta_per_day,
                vega_exposure=0.1,
                probability_of_touch=touch,
                profit_range_low=breakeven_points[0],
                profit_range_high=breakeven_points[-1],
                composite_score=composite_score,
            ),
            pnl_samples=[-max_loss, expected_value, 250.0],
            tradeoff_comment=tradeoff_comment,
        )

    monkeypatch.setattr(
        analyzer_module,
        "rank_recommendations",
        lambda **kwargs: [
            _rec(
                name="iron_condor",
                composite_score=71.0,
                pop=61.7,
                expected_value=-12.0,
                touch=78.4,
                theta_per_day=0.18,
                max_loss=920.0,
                breakeven_points=[399.3, 420.7],
                legs=[
                    StrategyLeg("option", "sell", 1, 4.1, 410.0, "put"),
                    StrategyLeg("option", "buy", 1, 1.8, 395.0, "put"),
                    StrategyLeg("option", "sell", 1, 4.2, 410.0, "call"),
                    StrategyLeg("option", "buy", 1, 1.7, 420.0, "call"),
                ],
                tradeoff_comment="Range-bound premium collection setup.",
            ),
            _rec(
                name="long_strangle",
                composite_score=66.0,
                pop=35.0,
                expected_value=8.0,
                touch=49.0,
                theta_per_day=-0.17,
                max_loss=1450.0,
                breakeven_points=[382.0, 438.0],
                legs=[
                    StrategyLeg("option", "buy", 1, 12.0, 410.0, "put"),
                    StrategyLeg("option", "buy", 1, 9.0, 415.0, "call"),
                ],
                tradeoff_comment="Long volatility with cheaper OTM strikes.",
            ),
            _rec(
                name="long_straddle",
                composite_score=62.0,
                pop=32.0,
                expected_value=6.0,
                touch=51.0,
                theta_per_day=-0.43,
                max_loss=2712.0,
                breakeven_points=[382.9, 437.1],
                legs=[
                    StrategyLeg("option", "buy", 1, 13.6, 410.0, "put"),
                    StrategyLeg("option", "buy", 1, 13.5, 410.0, "call"),
                ],
                tradeoff_comment="ATM volatility expansion setup.",
            ),
            _rec(
                name="bull_put_credit_spread",
                composite_score=59.0,
                pop=68.0,
                expected_value=11.0,
                touch=43.0,
                theta_per_day=0.14,
                max_loss=750.0,
                breakeven_points=[397.5],
                legs=[
                    StrategyLeg("option", "sell", 1, 2.5, 400.0, "put"),
                    StrategyLeg("option", "buy", 1, 0.0, 390.0, "put"),
                ],
                tradeoff_comment="Directional bullish credit spread.",
            ),
        ],
    )

    payload = analyzer.run(ticker="MSFT", days_to_exp=30)

    assert len(payload["recommendations"]) == 3
    overlay = payload["analysis_overlay"]
    conservative = overlay["final_recommendations"]["best_conservative_executable_setup"]
    assert conservative["strategy_name"] == "bull_put_credit_spread"
    assert "tight condor" in conservative["rationale"] or "condor" in conservative["rationale"]
    warnings = overlay.get("warnings") or []
    assert any("negative expected value" in item.lower() for item in warnings)
    ranking_audit = overlay.get("ranking_audit") or []
    assert ranking_audit
    assert all(
        "modeled_rank" in item and "executable_rank" in item for item in ranking_audit)
    comparison = {item["strategy_name"]                  : item for item in overlay["strategy_comparison"]}
    assert comparison["iron_condor"]["flags"]["range_too_tight_vs_expected_move"] is True
    assert comparison["iron_condor"]["flags"]["negative_ev_despite_high_pop"] is True
    assert comparison["bull_put_credit_spread"]["flags"]["puts_rich_supportive"] is True


def test_options_analyzer_warns_when_top_modeled_touch_is_too_high(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        analyzer_module, "YFinanceOptionsFetcher", _DummyFetcher)

    analyzer = OptionsAnalyzer(config=_config(tmp_path))
    frame = _sample_chain()

    monkeypatch.setattr(
        analyzer,
        "_load_or_fetch",
        lambda ticker: (
            frame,
            120.0,
            sorted(frame["expiration"].unique().tolist()),
            {"used_cache": False, "metadata": {"ticker": ticker}},
        ),
    )
    monkeypatch.setattr(
        analyzer,
        "_underlying_history",
        lambda ticker: pd.Series(np.linspace(100.0, 122.0, 365)),
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

    expiration = frame.iloc[0]["expiration"]

    monkeypatch.setattr(
        analyzer_module,
        "rank_recommendations",
        lambda **kwargs: [
            StrategyRecommendation(
                strategy=StrategyCandidate(
                    name="iron_condor",
                    expiration=expiration,
                    days_to_expiration=30,
                    legs=[
                        StrategyLeg("option", "sell", 1, 4.0, 120.0, "put"),
                        StrategyLeg("option", "buy", 1, 1.5, 110.0, "put"),
                        StrategyLeg("option", "sell", 1, 4.1, 120.0, "call"),
                        StrategyLeg("option", "buy", 1, 1.6, 130.0, "call"),
                    ],
                    net_premium=500.0,
                    max_profit=500.0,
                    max_loss=950.0,
                    breakeven_points=[116.0, 124.0],
                ),
                metrics=StrategyMetrics(
                    pop=60.0,
                    expected_value=9.0,
                    expected_profit=50.0,
                    expected_loss=25.0,
                    risk_reward=1.0,
                    max_loss=950.0,
                    theta_per_day=0.2,
                    vega_exposure=0.1,
                    probability_of_touch=89.0,
                    profit_range_low=116.0,
                    profit_range_high=124.0,
                    composite_score=70.0,
                ),
                pnl_samples=[-950.0, 9.0, 500.0],
                tradeoff_comment="Tight range premium setup.",
            )
        ],
    )

    payload = analyzer.run(ticker="MSFT", days_to_exp=30)
    warnings = payload["analysis_overlay"].get("warnings") or []
    assert any("probability of touch" in item.lower() for item in warnings)


def test_overlay_rejects_negative_ev_cash_secured_put_as_conservative() -> None:
    def _rec(name: str, expected_value: float, touch: float, max_loss: float) -> dict:
        return {
            "strategy": {
                "name": name,
                "legs": [
                    {
                        "instrument_type": "option",
                        "side": "sell",
                        "quantity": 1,
                        "premium": 4.0,
                        "strike": 400.0,
                        "option_type": "put",
                    }
                ],
                "breakeven_points": [396.0],
            },
            "metrics": {
                "composite_score": 72.0,
                "pop": 64.0,
                "expected_value": expected_value,
                "probability_of_touch": touch,
                "theta_per_day": 0.2,
                "vega_exposure": 0.1,
                "risk_reward": 0.02,
                "max_loss": max_loss,
            },
            "tradeoff_comment": "Income + discounted-entry style setup.",
        }

    overlay = build_narrative_overlay(
        ticker="SPY",
        underlying_analysis={
            "historical_volatility": {"hv_30": 0.18},
            "implied_volatility": {"iv_mean": 0.36, "iv_rank": 100.0, "iv_percentile": 100.0},
            "expected_move": {"one_std_move": 42.8, "one_std_move_pct": 0.104},
            "hv_vs_iv": {"iv_rich_vs_hv_short": True},
            "put_call_skew": {"skew_diff": -0.236},
            "options_market_snapshot": {"put_call_oi_ratio": 1.0, "put_call_volume_ratio": 1.0},
        },
        all_ranked=[_rec("cash_secured_put", -572.0, 72.0, 39670.0)],
    )

    assert overlay["final_recommendations"]["best_conservative_executable_setup"] is None
    assert any("no conservative income setup" in item.lower()
               for item in overlay["warnings"])


def test_overlay_demotes_high_touch_straddle_below_bull_put_for_executable_ranking() -> None:
    ranked = [
        {
            "strategy": {
                "name": "long_straddle",
                "legs": [
                    {
                        "instrument_type": "option",
                        "side": "buy",
                        "quantity": 1,
                        "premium": 20.0,
                        "strike": 412.0,
                        "option_type": "call",
                    },
                    {
                        "instrument_type": "option",
                        "side": "buy",
                        "quantity": 1,
                        "premium": 20.0,
                        "strike": 412.0,
                        "option_type": "put",
                    },
                ],
                "breakeven_points": [372.0, 452.0],
            },
            "metrics": {
                "composite_score": 82.0,
                "pop": 52.0,
                "expected_value": 30.0,
                "probability_of_touch": 91.7,
                "theta_per_day": -0.6,
                "vega_exposure": 0.6,
                "risk_reward": 1.0,
                "max_loss": 4000.0,
            },
            "tradeoff_comment": "ATM volatility expansion setup.",
        },
        {
            "strategy": {
                "name": "bull_put_credit_spread",
                "legs": [
                    {
                        "instrument_type": "option",
                        "side": "sell",
                        "quantity": 1,
                        "premium": 3.4,
                        "strike": 395.0,
                        "option_type": "put",
                    },
                    {
                        "instrument_type": "option",
                        "side": "buy",
                        "quantity": 1,
                        "premium": 1.2,
                        "strike": 385.0,
                        "option_type": "put",
                    },
                ],
                "breakeven_points": [392.8],
            },
            "metrics": {
                "composite_score": 60.0,
                "pop": 64.0,
                "expected_value": 12.0,
                "probability_of_touch": 48.0,
                "theta_per_day": 0.18,
                "vega_exposure": -0.1,
                "risk_reward": 0.28,
                "max_loss": 780.0,
            },
            "tradeoff_comment": "Directional bullish credit spread.",
        },
    ]

    overlay = build_narrative_overlay(
        ticker="SPY",
        underlying_analysis={
            "historical_volatility": {"hv_30": 0.18},
            "implied_volatility": {"iv_mean": 0.366, "iv_rank": 100.0, "iv_percentile": 100.0},
            "expected_move": {"one_std_move": 42.8, "one_std_move_pct": 0.104},
            "hv_vs_iv": {"iv_rich_vs_hv_short": True},
            "put_call_skew": {"skew_diff": -0.236},
            "options_market_snapshot": {"put_call_oi_ratio": 1.0, "put_call_volume_ratio": 1.0},
        },
        all_ranked=ranked,
    )

    conservative = overlay["final_recommendations"]["best_conservative_executable_setup"]
    assert conservative["strategy_name"] == "bull_put_credit_spread"
    audit = {item["strategy_name"]: item for item in overlay["ranking_audit"]}
    assert (
        audit["bull_put_credit_spread"]["executable_rank"]
        < audit["long_straddle"]["executable_rank"]
    )
    assert any("probability of touch" in item.lower() for item in overlay["warnings"])


def test_overlay_marks_low_quality_top_rank_as_no_trade() -> None:
    overlay = build_narrative_overlay(
        ticker="SPY",
        underlying_analysis={
            "historical_volatility": {"hv_30": 0.18},
            "implied_volatility": {
                "iv_mean": 0.36,
                "iv_rank": 100.0,
                "iv_percentile": 100.0,
            },
            "expected_move": {"one_std_move": 42.8, "one_std_move_pct": 0.104},
            "hv_vs_iv": {"iv_rich_vs_hv_short": True},
            "put_call_skew": {"skew_diff": -0.236},
            "options_market_snapshot": {
                "put_call_oi_ratio": 1.0,
                "put_call_volume_ratio": 1.0,
            },
        },
        all_ranked=[
            {
                "strategy": {
                    "name": "bull_call_debit_spread",
                    "legs": [
                        {
                            "instrument_type": "option",
                            "side": "buy",
                            "quantity": 1,
                            "premium": 4.4,
                            "strike": 410.0,
                            "option_type": "call",
                        },
                        {
                            "instrument_type": "option",
                            "side": "sell",
                            "quantity": 1,
                            "premium": 2.2,
                            "strike": 420.0,
                            "option_type": "call",
                        },
                    ],
                    "breakeven_points": [412.2],
                },
                "metrics": {
                    "composite_score": 20.0093,
                    "pop": 43.9642,
                    "expected_value": -2.57,
                    "probability_of_touch": 87.5996,
                    "theta_per_day": -0.04,
                    "vega_exposure": 0.07,
                    "risk_reward": 3.54,
                    "max_loss": 220.0,
                },
                "tradeoff_comment": (
                    "bull call debit spread: Balanced probability profile; "
                    "negative modeled expectancy; high path-risk."
                ),
            }
        ],
    )

    assert overlay["trade_decision"]["status"] == "no_trade"
    assert overlay["final_recommendations"]["best_overall_executable_setup"] is None
    assert overlay["final_recommendations"]["best_aggressive_setup"] is None
    audit = overlay["ranking_audit"][0]
    assert audit["quality_gate"]["actionable"] is False
    # Aggressive strategies now use 40 threshold; score 20.0 is below it
    assert "composite_score_below_40_threshold" in audit["quality_gate"]["blockers"]
    # Slightly negative EV (-2.57) is now a warning, not a blocker for aggressive
    assert "slightly_negative_expected_value" in audit["quality_gate"]["warnings"]
    assert "probability_of_touch_above_model_warning" in audit["quality_gate"]["blockers"]


def test_overlay_rejects_capital_intensive_covered_call_scan_candidate() -> None:
    overlay = build_narrative_overlay(
        ticker="KLAC",
        underlying_analysis={
            "historical_volatility": {"hv_30": 0.18},
            "implied_volatility": {
                "iv_mean": 0.25,
                "iv_rank": 65.0,
                "iv_percentile": 70.0,
            },
            "expected_move": {"one_std_move": 42.8, "one_std_move_pct": 0.024},
            "hv_vs_iv": {"iv_rich_vs_hv_short": True},
            "put_call_skew": {"skew_diff": 0.01},
            "options_market_snapshot": {
                "put_call_oi_ratio": 1.0,
                "put_call_volume_ratio": 1.0,
            },
        },
        all_ranked=[
            {
                "strategy": {
                    "name": "covered_call",
                    "legs": [
                        {
                            "instrument_type": "stock",
                            "side": "buy",
                            "quantity": 100,
                            "premium": 1764.58,
                        },
                        {
                            "instrument_type": "option",
                            "side": "sell",
                            "quantity": 1,
                            "premium": 10.0,
                            "strike": 1820.0,
                            "option_type": "call",
                        },
                    ],
                    "breakeven_points": [1754.58],
                },
                "metrics": {
                    "composite_score": 62.0,
                    "pop": 99.0,
                    "expected_value": 616.0,
                    "probability_of_touch": 1.0,
                    "theta_per_day": 0.2,
                    "vega_exposure": -0.1,
                    "risk_reward": 0.1,
                    "max_loss": 175458.0,
                },
                "tradeoff_comment": "Covered call requires long stock.",
            }
        ],
    )

    assert overlay["trade_decision"]["status"] == "no_trade"
    assert overlay["final_recommendations"]["best_overall_executable_setup"] is None
    blockers = overlay["ranking_audit"][0]["quality_gate"]["blockers"]
    assert "requires_existing_position_or_large_cash_reserve" in blockers


def test_scan_crypto_opportunities_applies_momentum_gate_before_options(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        analyzer_module, "YFinanceOptionsFetcher", _DummyFetcher)

    analyzer = OptionsAnalyzer(config=_config(tmp_path))
    run_calls: list[str] = []

    def _fake_run(*, ticker: str = "MSFT", days_to_exp: int = 30):
        run_calls.append(ticker)
        return {
            "ticker": ticker,
            "recommendations": [
                {
                    "strategy": {"name": "bull_put_credit_spread"},
                    "metrics": {
                        "composite_score": 81.0,
                        "pop": 64.0,
                        "expected_value": 12.0,
                        "probability_of_touch": 44.0,
                    },
                }
            ],
        }

    monkeypatch.setattr(analyzer, "run", _fake_run)

    class _FakeMomentumService:
        def parse_timeframes(self, tf: str):
            assert tf == "4h,1h"
            return SimpleNamespace(bias="1d", setup="4h", trigger="1h")

        def scan_live(self, **kwargs):
            assert kwargs["symbols"] == ["BTCUSDT", "ETHUSDT"]
            return {
                "timeframes": {"bias": "1d", "setup": "4h", "trigger": "1h"},
                "summary": {"tradeable_count": 1},
                "results": {
                    "BTCUSDT": {
                        "plans": [
                            {
                                "side": "long",
                                "setup_status": "confirmed",
                                "confidence_score": 88,
                                "entry_zone": [70000.0, 71000.0],
                                "invalidation": 69500.0,
                                "rr_estimated": 3.2,
                            }
                        ],
                        "tradeable": [
                            {
                                "side": "long",
                                "setup_status": "confirmed",
                                "confidence_score": 88,
                                "entry_zone": [70000.0, 71000.0],
                                "invalidation": 69500.0,
                                "rr_estimated": 3.2,
                            }
                        ],
                    },
                    "ETHUSDT": {
                        "plans": [
                            {
                                "side": "long",
                                "setup_status": "pending",
                                "confidence_score": 63,
                                "entry_zone": [3500.0, 3575.0],
                                "invalidation": 3450.0,
                                "rr_estimated": 2.1,
                            }
                        ],
                        "tradeable": [],
                    },
                },
            }

    monkeypatch.setattr(
        "trading.crypto.momentum.service.MomentumMarketService", _FakeMomentumService)

    payload = analyzer.scan_crypto_opportunities(
        coins=["BTC", "ETH"],
        days_to_exp=30,
        tf="4h,1h",
        require_tradeable=True,
    )

    assert payload["summary"]["coins_requested"] == 2
    assert payload["summary"]["momentum_allowed"] == 1
    assert payload["summary"]["options_ready"] == 1
    assert run_calls == ["BTC-USD"]
    assert payload["opportunities"]["BTC"]["status"] == "ready"
    assert payload["opportunities"]["ETH"]["status"] == "filtered_by_momentum"
    assert payload["ranked"][0]["coin"] == "BTC"


def test_scan_crypto_opportunities_deribit_source_uses_coin_tickers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        analyzer_module, "DeribitOptionsFetcher", _DummyFetcher)

    analyzer = OptionsAnalyzer(config=_config(
        tmp_path), fetcher_source="deribit")
    run_calls: list[str] = []

    def _fake_run(*, ticker: str = "BTC", days_to_exp: int = 30):
        _ = days_to_exp
        run_calls.append(ticker)
        return {
            "ticker": ticker,
            "recommendations": [
                {
                    "strategy": {"name": "bull_put_credit_spread"},
                    "metrics": {
                        "composite_score": 80.0,
                        "pop": 62.0,
                        "expected_value": 10.0,
                        "probability_of_touch": 41.0,
                    },
                }
            ],
        }

    monkeypatch.setattr(analyzer, "run", _fake_run)

    class _FakeMomentumService:
        def parse_timeframes(self, tf: str):
            _ = tf
            return SimpleNamespace(bias="1d", setup="4h", trigger="1h")

        def scan_live(self, **kwargs):
            assert kwargs["symbols"] == ["BTCUSDT"]
            return {
                "timeframes": {"bias": "1d", "setup": "4h", "trigger": "1h"},
                "summary": {"tradeable_count": 1},
                "results": {
                    "BTCUSDT": {
                        "plans": [{"side": "long", "confidence_score": 80}],
                        "tradeable": [{"side": "long", "confidence_score": 80}],
                    }
                },
            }

    monkeypatch.setattr(
        "trading.crypto.momentum.service.MomentumMarketService", _FakeMomentumService
    )

    payload = analyzer.scan_crypto_opportunities(
        coins=["BTC"],
        days_to_exp=30,
        tf="4h,1h",
        require_tradeable=True,
    )

    assert run_calls == ["BTC"]
    assert payload["data_source"] == "deribit"
