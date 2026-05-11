from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import options.analyzer as analyzer_module
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
    assert set(payload["charts"].keys()) == {
        "payoff", "greeks", "monte_carlo", "strategy_ranking"}


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
    comparison = {item["strategy_name"]: item for item in overlay["strategy_comparison"]}
    assert comparison["iron_condor"]["flags"]["range_too_tight_vs_expected_move"] is True
    assert comparison["iron_condor"]["flags"]["negative_ev_despite_high_pop"] is True
    assert comparison["bull_put_credit_spread"]["flags"]["puts_rich_supportive"] is True
