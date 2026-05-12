from __future__ import annotations

from options.visualization.terminal import build_terminal_chart_data


def test_build_terminal_chart_data_with_bull_put_spread_fixture() -> None:
    report = {
        "ticker": "MSFT",
        "underlying_analysis": {
            "price": 420.0,
            "historical_volatility": {"hv_30": 0.24},
            "expected_move": {"horizon_days": 30, "one_std_move": 11.0},
        },
        "recommendations": [
            {
                "strategy": {
                    "name": "bull_put_credit_spread",
                    "expiration": "2026-06-20",
                    "days_to_expiration": 30,
                    "net_premium": 1.5,
                    "max_profit": 150.0,
                    "max_loss": 850.0,
                    "breakeven_points": [398.5],
                    "legs": [
                        {
                            "instrument_type": "option",
                            "side": "sell",
                            "quantity": 1,
                            "premium": 2.5,
                            "strike": 400.0,
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
                },
                "metrics": {
                    "composite_score": 73.0,
                    "pop": 67.0,
                    "expected_value": 12.4,
                    "probability_of_touch": 39.0,
                    "theta_per_day": 0.13,
                    "vega_exposure": 0.08,
                },
                "tradeoff_comment": "Defined risk credit spread with bullish bias.",
            }
        ],
        "all_recommendations_ranked": [
            {
                "strategy": {"name": "bull_put_credit_spread"},
                "metrics": {"composite_score": 73.0},
            },
            {
                "strategy": {"name": "iron_condor"},
                "metrics": {"composite_score": 62.0},
            },
        ],
    }

    chart_data = build_terminal_chart_data(report)

    payoff = chart_data["payoff"]
    assert payoff["strategy_name"] == "bull_put_credit_spread"
    assert len(payoff["prices"]) == len(payoff["pnl"])
    assert len(payoff["prices"]) >= 100
    assert min(payoff["pnl"]) < 0
    assert max(payoff["pnl"]) > 0

    greeks = chart_data["greeks"]
    assert set(greeks.keys()) == {"delta", "gamma", "theta", "vega"}

    mc = chart_data["monte_carlo"]
    assert len(mc["samples"]) == 1500
    assert mc["p5"] <= mc["mean"] <= mc["p95"]

    ranking = chart_data["ranking"]
    assert ranking["names"][0] == "bull_put_credit_spread"
    assert ranking["scores"][0] == 73.0
