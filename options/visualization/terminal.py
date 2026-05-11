"""Terminal-native chart rendering for options analysis payloads.

This module renders lightweight text charts with plotext so users can inspect
strategy profiles directly in terminal sessions (SSH, tmux, CI logs) without
opening HTML artifacts.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import Any

import numpy as np
from rich.console import Console
from rich.text import Text

from options.analytics.probability import strategy_pnl_profile
from options.models import StrategyCandidate, StrategyLeg

try:
    import plotext as _plt

    _HAS_PLOTEXT = True
except Exception:  # noqa: BLE001
    _plt = None
    _HAS_PLOTEXT = False


class TerminalChartDependencyError(RuntimeError):
    """Raised when terminal chart mode is requested without plotext installed."""


def render_terminal_charts(report_json: dict[str, Any], *, console: Console | None = None) -> None:
    """Render payoff, Greeks, Monte Carlo, and ranking charts in the terminal.

    Parameters
    ----------
    report_json:
        JSON-serializable analysis payload returned by the options analyzer.
    console:
        Optional Rich console used for labels and warning panels.
    """
    if not _HAS_PLOTEXT:
        raise TerminalChartDependencyError(
            "Terminal chart mode requires plotext. Install it with: pip install plotext"
        )

    out = console or Console()
    data = build_terminal_chart_data(report_json)
    chart_width = max(64, min(96, out.size.width - 8))

    _render_payoff_chart(data["payoff"], out, width=chart_width)
    _render_greeks_chart(data["greeks"], out, width=chart_width)
    _render_monte_carlo_chart(data["monte_carlo"], out, width=chart_width)
    _render_ranking_chart(data["ranking"], out, width=chart_width)


def build_terminal_chart_data(report_json: dict[str, Any]) -> dict[str, Any]:
    """Prepare normalized chart inputs from analyzer payload.

    This helper is deterministic and test-friendly. Rendering can consume this
    pre-shaped data without repeating extraction logic.
    """
    top = _top_recommendation(report_json)
    underlying_analysis = report_json.get("underlying_analysis") or {}
    underlying_price = _as_float(underlying_analysis.get("price")) or 0.0

    return {
        "payoff": _payoff_series(report_json, top, underlying_price),
        "greeks": _greeks_summary(report_json, top),
        "monte_carlo": _monte_carlo_distribution(report_json, top, underlying_price),
        "ranking": _ranking_series(report_json),
    }


def _top_recommendation(report_json: dict[str, Any]) -> dict[str, Any]:
    recs = list(report_json.get("recommendations") or [])
    if recs:
        return recs[0]
    ranked = list(report_json.get("all_recommendations_ranked") or [])
    return ranked[0] if ranked else {}


def _as_float(value: object) -> float | None:
    try:
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float, str)):
            return float(value)
    except (TypeError, ValueError):
        return None
    return None


def _strategy_from_payload(top: dict[str, Any]) -> StrategyCandidate | None:
    strategy = top.get("strategy") or {}
    legs_payload = list(strategy.get("legs") or [])
    if not legs_payload:
        return None

    legs: list[StrategyLeg] = []
    for leg in legs_payload:
        if not isinstance(leg, dict):
            continue
        quantity = int(_as_float(leg.get("quantity")) or 1)
        legs.append(
            StrategyLeg(
                instrument_type=str(leg.get("instrument_type") or "option"),
                side=str(leg.get("side") or "sell"),
                quantity=quantity,
                premium=_as_float(leg.get("premium")) or 0.0,
                strike=_as_float(leg.get("strike")),
                option_type=str(leg.get("option_type")) if leg.get(
                    "option_type") is not None else None,
            )
        )

    if not legs:
        return None

    return StrategyCandidate(
        name=str(strategy.get("name") or "unknown_strategy"),
        expiration=str(strategy.get("expiration") or "1970-01-01"),
        days_to_expiration=int(
            _as_float(strategy.get("days_to_expiration")) or 30),
        legs=legs,
        net_premium=_as_float(strategy.get("net_premium")) or 0.0,
        max_profit=_as_float(strategy.get("max_profit")),
        max_loss=_as_float(strategy.get("max_loss")),
        breakeven_points=[
            float(x)
            for x in list(strategy.get("breakeven_points") or [])
            if _as_float(x) is not None
        ],
        notes=[str(x) for x in list(strategy.get("notes") or [])],
    )


def _payoff_series(
    report_json: dict[str, Any],
    top: dict[str, Any],
    underlying_price: float,
) -> dict[str, Any]:
    terminal_data = report_json.get("terminal_chart_data") or {}
    native = terminal_data.get("payoff") or {}
    native_prices = list(native.get("prices") or [])
    native_pnl = list(native.get("pnl") or [])
    if native_prices and native_pnl and len(native_prices) == len(native_pnl):
        return {
            "strategy_name": str(native.get("strategy_name") or "top_strategy"),
            "prices": [float(x) for x in native_prices],
            "pnl": [float(y) for y in native_pnl],
            "expected_move": _as_float(native.get("expected_move")),
        }

    strategy = _strategy_from_payload(top)
    if strategy is None or underlying_price <= 0:
        return {
            "strategy_name": "no_strategy",
            "prices": [0.0, 1.0],
            "pnl": [0.0, 0.0],
            "expected_move": None,
        }

    prices = np.linspace(underlying_price * 0.65, underlying_price * 1.35, 120)
    pnl = strategy_pnl_profile(strategy, prices)
    expected_move = _as_float(
        ((report_json.get("underlying_analysis") or {}).get(
            "expected_move") or {}).get("one_std_move")
    )
    return {
        "strategy_name": strategy.name,
        "prices": prices.astype(float).tolist(),
        "pnl": pnl.astype(float).tolist(),
        "expected_move": expected_move,
    }


def _greeks_summary(report_json: dict[str, Any], top: dict[str, Any]) -> dict[str, float]:
    terminal_data = report_json.get("terminal_chart_data") or {}
    native = terminal_data.get("greeks_summary") or {}
    for candidate in [native, (report_json.get("underlying_analysis") or {}).get("greeks_summary") or {}]:
        if candidate:
            delta = _as_float(candidate.get("delta"))
            gamma = _as_float(candidate.get("gamma"))
            theta = _as_float(candidate.get("theta"))
            vega = _as_float(candidate.get("vega"))
            if all(value is not None for value in (delta, gamma, theta, vega)):
                return {
                    "delta": float(delta if delta is not None else 0.0),
                    "gamma": float(gamma if gamma is not None else 0.0),
                    "theta": float(theta if theta is not None else 0.0),
                    "vega": float(vega if vega is not None else 0.0),
                }

    metrics = top.get("metrics") or {}
    theta_metric = _as_float(metrics.get("theta_per_day")) or 0.0
    vega_metric = _as_float(metrics.get("vega_exposure")) or 0.0

    strategy = _strategy_from_payload(top)
    delta_proxy = 0.0
    gamma_proxy = 0.0
    if strategy is not None:
        for leg in strategy.legs:
            if leg.instrument_type != "option":
                continue
            direction = 1.0 if leg.side == "buy" else -1.0
            qty = float(leg.quantity)
            if leg.option_type == "call":
                delta_proxy += direction * 0.5 * qty
            else:
                delta_proxy += direction * -0.5 * qty
            gamma_proxy += direction * 0.05 * qty

    return {
        "delta": float(delta_proxy),
        "gamma": float(gamma_proxy),
        "theta": float(theta_metric),
        "vega": float(vega_metric),
    }


def _extract_hv(underlying_analysis: dict[str, Any]) -> float:
    hv = underlying_analysis.get("historical_volatility") or {}
    if isinstance(hv, dict):
        for _, value in hv.items():
            as_float = _as_float(value)
            if as_float is not None and as_float > 0:
                return float(as_float)
    return 0.3


def _monte_carlo_distribution(
    report_json: dict[str, Any],
    top: dict[str, Any],
    underlying_price: float,
) -> dict[str, Any]:
    terminal_data = report_json.get("terminal_chart_data") or {}
    native = terminal_data.get("monte_carlo") or {}
    native_samples = list(native.get("pnl_samples") or [])
    if native_samples:
        samples = np.array([float(x) for x in native_samples], dtype=float)
        return {
            "samples": samples.tolist(),
            "mean": float(samples.mean()),
            "p5": float(np.quantile(samples, 0.05)),
            "p95": float(np.quantile(samples, 0.95)),
        }

    strategy = _strategy_from_payload(top)
    if strategy is None or underlying_price <= 0:
        return {"samples": [0.0, 0.0, 0.0], "mean": 0.0, "p5": 0.0, "p95": 0.0}

    underlying_analysis = report_json.get("underlying_analysis") or {}
    hv_annualized = _extract_hv(underlying_analysis)
    dte = max(
        1,
        int(
            _as_float((top.get("strategy") or {}).get("days_to_expiration"))
            or _as_float((underlying_analysis.get("expected_move") or {}).get("horizon_days"))
            or 30
        ),
    )

    rng = np.random.default_rng(7)
    n_paths = 1500
    dt = max(1.0 / 365.0, dte / 365.0)
    sigma = max(0.01, hv_annualized)
    terminal_prices = underlying_price * np.exp(
        (-0.5 * sigma * sigma) * dt + sigma *
        np.sqrt(dt) * rng.standard_normal(n_paths)
    )
    pnl = strategy_pnl_profile(strategy, terminal_prices)
    return {
        "samples": pnl.astype(float).tolist(),
        "mean": float(pnl.mean()),
        "p5": float(np.quantile(pnl, 0.05)),
        "p95": float(np.quantile(pnl, 0.95)),
    }


def _ranking_series(report_json: dict[str, Any]) -> dict[str, Any]:
    ranked = list(report_json.get("all_recommendations_ranked") or [])
    if not ranked:
        ranked = list(report_json.get("recommendations") or [])

    names: list[str] = []
    scores: list[float] = []
    for rec in ranked[:8]:
        strategy_name = str(
            (rec.get("strategy") or {}).get("name") or "unknown")
        score = _as_float((rec.get("metrics") or {}).get("composite_score"))
        if score is None:
            continue
        names.append(strategy_name)
        scores.append(float(score))

    if not names:
        names = ["no_data"]
        scores = [0.0]

    return {"names": names, "scores": scores}


def _clear_plot() -> None:
    if _plt is None:
        return
    for method_name in ("clear_data", "clear_figure", "cld", "clf"):
        method = getattr(_plt, method_name, None)
        if callable(method):
            method()


def _plt_call(method_name: str, *args: Any, **kwargs: Any) -> Any:
    """Call a plotext method if available and return the result."""
    if _plt is None:
        return None
    method = getattr(_plt, method_name, None)
    if callable(method):
        return method(*args, **kwargs)
    return None


def _render_plot(draw_fn: Any, *, width: int, height: int) -> str:
    if _plt is None:
        return ""
    _clear_plot()
    _plt_call("theme", "clear")
    _plt_call("limit_size", True, True)
    _plt_call("plotsize", width, height)
    draw_fn()

    built = _plt_call("build")
    if isinstance(built, str) and built.strip():
        return built.rstrip()

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        _plt_call("show")
    return buffer.getvalue().rstrip()


def _print_chart_block(
    console: Console,
    *,
    title: str,
    chart: str,
    note: str | None = None,
) -> None:
    """Print one chart block without wrapping it in an extra Rich panel."""
    console.rule(f"[bold]{title}[/bold]", style="cyan")
    if note:
        console.print(f"[dim]{note}[/dim]")
    if chart:
        console.print(Text(chart, no_wrap=True),
                      overflow="ignore", soft_wrap=False)
    else:
        console.print("[yellow]Chart rendering returned no output.[/yellow]")


def _render_payoff_chart(payload: dict[str, Any], console: Console, *, width: int) -> None:
    prices = [float(x) for x in payload.get("prices") or []]
    pnl = [float(y) for y in payload.get("pnl") or []]
    strategy_name = str(payload.get("strategy_name") or "top_strategy")
    expected_move = _as_float(payload.get("expected_move"))

    if not prices or not pnl:
        _print_chart_block(console, title="Strategy Payoff Diagram",
                           chart="", note="No payoff data available.")
        return

    def _draw() -> None:
        _plt_call("xfrequency", 6)
        _plt_call("yfrequency", 5)
        _plt_call("xlim", min(prices), max(prices))
        _plt_call("plot", prices, pnl)

    chart = _render_plot(_draw, width=width, height=14)
    note = f"Strategy: {strategy_name.replace('_', ' ')}"
    if expected_move is not None:
        note = f"{note} | Expected 1sd move: {expected_move:.2f}"
    _print_chart_block(
        console, title="Strategy Payoff Diagram", chart=chart, note=note)


def _render_greeks_chart(payload: dict[str, float], console: Console, *, width: int) -> None:
    raw_items = [
        ("Delta", float(payload.get("delta") or 0.0)),
        ("Gamma", float(payload.get("gamma") or 0.0)),
        ("Theta", float(payload.get("theta") or 0.0)),
        ("Vega", float(payload.get("vega") or 0.0)),
    ]
    labels = [
        f"{name} {'+' if value >= 0 else '-'}{abs(value):.3f}" for name, value in raw_items]
    values = [max(abs(value), 0.0001) for _, value in raw_items]
    bar_width = max(24, min(56, width - 20))

    def _draw() -> None:
        _plt_call("simple_bar", labels, values, width=bar_width)

    chart = _render_plot(_draw, width=width, height=8)
    note = "Bar length uses absolute exposure; sign is embedded in the label."
    _print_chart_block(console, title="Greeks Summary", chart=chart, note=note)


def _render_monte_carlo_chart(payload: dict[str, Any], console: Console, *, width: int) -> None:
    samples = [float(x) for x in payload.get("samples") or []]
    mean = _as_float(payload.get("mean")) or 0.0
    p5 = _as_float(payload.get("p5")) or 0.0
    p95 = _as_float(payload.get("p95")) or 0.0

    def _draw() -> None:
        _plt_call("xfrequency", 6)
        _plt_call("yfrequency", 5)
        _plt_call("hist", samples, bins=24)

    chart = _render_plot(_draw, width=width, height=12)
    note = f"Mean: {mean:.2f} | P5: {p5:.2f} | P95: {p95:.2f}"
    _print_chart_block(
        console, title="Monte Carlo Distribution", chart=chart, note=note)


def _render_ranking_chart(payload: dict[str, Any], console: Console, *, width: int) -> None:
    names = [str(x) for x in payload.get("names") or []]
    scores = [float(x) for x in payload.get("scores") or []]

    trimmed_names = [name.replace("_", " ")[:20] for name in names[:6]]
    trimmed_scores = scores[:6]
    bar_width = max(24, min(56, width - 20))

    def _draw() -> None:
        _plt_call("simple_bar", trimmed_names, trimmed_scores, width=bar_width)

    chart = _render_plot(_draw, width=width, height=9)
    note = "Composite score ranking for the highest-ranked strategies."
    _print_chart_block(console, title="Strategy Ranking",
                       chart=chart, note=note)
