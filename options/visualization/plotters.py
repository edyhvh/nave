"""Plotly-first chart builders with matplotlib fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from options.models import StrategyRecommendation

try:
    import plotly.express as px
    import plotly.graph_objects as go

    _HAS_PLOTLY = True
except Exception:  # noqa: BLE001
    _HAS_PLOTLY = False


def build_payoff_chart(
    *,
    recommendation: StrategyRecommendation,
    underlying_price: float,
    output_path: Path,
) -> str:
    """Build payoff profile at expiration for one recommendation."""
    prices = np.linspace(underlying_price * 0.65, underlying_price * 1.35, 120)
    pnl = []
    for price in prices:
        pnl_val = 0.0
        for leg in recommendation.strategy.legs:
            multiplier = leg.quantity * 100.0 if leg.instrument_type == "option" else leg.quantity
            side = 1.0 if leg.side == "buy" else -1.0
            if leg.instrument_type == "stock":
                pnl_val += side * (price - leg.premium) * multiplier
                continue

            strike = leg.strike or 0.0
            intrinsic = max(
                0.0, price - strike) if leg.option_type == "call" else max(0.0, strike - price)
            pnl_val += side * (intrinsic - leg.premium) * multiplier
        pnl.append(pnl_val)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if _HAS_PLOTLY:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=prices, y=pnl, mode="lines",
                      name=recommendation.strategy.name))
        fig.add_hline(y=0.0, line_dash="dash")
        fig.update_layout(
            title=f"Payoff at Expiration: {recommendation.strategy.name}",
            xaxis_title="Underlying Price",
            yaxis_title="P/L (USD)",
            template="plotly_white",
        )
        fig.write_html(output_path)
        return str(output_path)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(prices, pnl, label=recommendation.strategy.name)
    ax.axhline(0.0, color="black", linestyle="--")
    ax.set_title(f"Payoff at Expiration: {recommendation.strategy.name}")
    ax.set_xlabel("Underlying Price")
    ax.set_ylabel("P/L (USD)")
    ax.legend()
    png_path = output_path.with_suffix(".png")
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)
    return str(png_path)


def build_greeks_chart(
    *,
    option_frame: pd.DataFrame,
    output_path: Path,
) -> str:
    """Build a greek exposure chart by strike."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    grouped = (
        option_frame.groupby(["strike", "option_type"], as_index=False)[
            ["delta", "gamma", "theta", "vega"]]
        .mean(numeric_only=True)
        .sort_values("strike")
    )

    if _HAS_PLOTLY:
        fig = px.line(
            grouped,
            x="strike",
            y=["delta", "gamma", "theta", "vega"],
            color="option_type",
            title="Greeks by Strike",
        )
        fig.write_html(output_path)
        return str(output_path)

    fig, ax = plt.subplots(figsize=(10, 5))
    for greek in ["delta", "gamma", "theta", "vega"]:
        ax.plot(grouped["strike"], grouped[greek], label=greek)
    ax.set_title("Greeks by Strike")
    ax.set_xlabel("Strike")
    ax.legend()
    png_path = output_path.with_suffix(".png")
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)
    return str(png_path)


def build_pnl_distribution_chart(
    *,
    recommendation: StrategyRecommendation,
    underlying_price: float,
    hv_annualized: float,
    days_to_expiration: int,
    n_paths: int,
    seed: int,
    output_path: Path,
) -> str:
    """Monte Carlo terminal P/L distribution chart."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    dt = max(1.0 / 365.0, days_to_expiration / 365.0)
    sigma = max(0.01, hv_annualized)
    terminal_prices = underlying_price * np.exp(
        (-0.5 * sigma * sigma) * dt + sigma *
        np.sqrt(dt) * rng.standard_normal(n_paths)
    )

    pnl_vals: list[float] = []
    for price in terminal_prices:
        pnl = 0.0
        for leg in recommendation.strategy.legs:
            multiplier = leg.quantity * 100.0 if leg.instrument_type == "option" else leg.quantity
            side = 1.0 if leg.side == "buy" else -1.0
            if leg.instrument_type == "stock":
                pnl += side * (price - leg.premium) * multiplier
                continue
            strike = leg.strike or 0.0
            intrinsic = max(
                0.0, price - strike) if leg.option_type == "call" else max(0.0, strike - price)
            pnl += side * (intrinsic - leg.premium) * multiplier
        pnl_vals.append(float(pnl))

    pnl_arr = np.array(pnl_vals)
    if _HAS_PLOTLY:
        fig = px.histogram(x=pnl_arr, nbins=60,
                           title="Monte Carlo P/L Distribution")
        fig.update_layout(xaxis_title="P/L (USD)",
                          yaxis_title="Frequency", template="plotly_white")
        fig.write_html(output_path)
        return str(output_path)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(pnl_arr, bins=60)
    ax.set_title("Monte Carlo P/L Distribution")
    ax.set_xlabel("P/L (USD)")
    ax.set_ylabel("Frequency")
    png_path = output_path.with_suffix(".png")
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)
    return str(png_path)


def build_strategy_ranking_chart(
    *,
    recommendations: list[StrategyRecommendation],
    ticker: str,
    underlying_price: float,
    options_snapshot: dict[str, Any],
    output_path: Path,
) -> str:
    """Build a ranking chart with strategy metrics and tradeoff commentary."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not recommendations:
        fig, ax = plt.subplots(figsize=(9, 3))
        ax.text(0.5, 0.5, "No strategies to rank", ha="center", va="center")
        ax.axis("off")
        png_path = output_path.with_suffix(".png")
        fig.tight_layout()
        fig.savefig(png_path, dpi=120)
        plt.close(fig)
        return str(png_path)

    rows = []
    for idx, rec in enumerate(recommendations, start=1):
        m = rec.metrics
        rows.append(
            {
                "Rank": idx,
                "Strategy": rec.strategy.name.replace("_", " "),
                "Score": round(m.composite_score, 2),
                "PoP %": round(m.pop, 2),
                "EV": round(m.expected_value, 2),
                "Touch %": round(m.probability_of_touch, 2),
                "RR": round(m.risk_reward, 2),
                "Max Loss": round(m.max_loss, 2),
                "Comment": rec.tradeoff_comment,
            }
        )

    if _HAS_PLOTLY:
        meta = (
            f"{ticker} | Price: {underlying_price:.2f} | Contracts: {int(options_snapshot.get('contracts', 0))} | "
            f"Put/Call OI: {options_snapshot.get('put_call_oi_ratio', float('nan')):.2f}"
        )
        df = pd.DataFrame(rows)
        fig = go.Figure(
            data=[
                go.Table(
                    header={
                        "values": list(df.columns),
                        "fill_color": "#f3f4f6",
                        "align": "left",
                    },
                    cells={
                        "values": [df[col] for col in df.columns],
                        "align": "left",
                    },
                )
            ]
        )
        fig.update_layout(
            title=f"Strategy Ranking Dashboard - {meta}",
            template="plotly_white",
        )
        fig.write_html(output_path)
        return str(output_path)

    fig, ax = plt.subplots(figsize=(11, 5))
    names = [row["Strategy"] for row in rows]
    scores = [row["Score"] for row in rows]
    y = np.arange(len(names))
    ax.barh(y, scores)
    ax.set_yticks(y, labels=names)
    ax.invert_yaxis()
    ax.set_xlabel("Composite Score")
    ax.set_title(f"Strategy Ranking - {ticker} @ {underlying_price:.2f}")
    for idx, score in enumerate(scores):
        ax.text(score + 0.5, idx, f"{score:.1f}", va="center")
    png_path = output_path.with_suffix(".png")
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)
    return str(png_path)
