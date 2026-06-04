"""Human-readable position context for options scan / gem rows."""

from __future__ import annotations

from typing import Any, Mapping


def _fmt_num(value: Any, *, decimals: int = 1, prefix: str = "") -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if prefix == "$":
        return f"${num:,.{decimals}f}"
    return f"{num:,.{decimals}f}"


def position_context_from_scan_row(
    row: Mapping[str, Any],
    *,
    days_to_exp: int | None = None,
    congress_tickers: frozenset[str] | set[str] | None = None,
    registry_alignment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize scan row fields into a stable context dict for CLI/JSON."""
    setup = row.get("executable_setup") or {}
    metrics = row.get("executable_metrics") or {}
    decision = row.get("trade_decision") or {}
    modeled = row.get("top_modeled_metrics") or {}
    ticker = str(row.get("ticker") or "").upper()
    dte = days_to_exp if days_to_exp is not None else 30
    warnings = list(row.get("warnings") or [])
    if registry_alignment and registry_alignment.get("warning"):
        warnings.append(str(registry_alignment["warning"]))

    return {
        "ticker": ticker,
        "status": row.get("status"),
        "strategy": (
            row.get("executable_strategy")
            or setup.get("strategy_name")
            or decision.get("strategy_name")
        ),
        "bias": setup.get("bias"),
        "thesis": setup.get("thesis"),
        "rationale": setup.get("rationale") or decision.get("reason"),
        "setup_summary": setup.get("setup_summary"),
        "metrics": {
            "composite_score": metrics.get("composite_score"),
            "pop": metrics.get("pop"),
            "expected_value": metrics.get("expected_value"),
            "probability_of_touch": metrics.get("probability_of_touch"),
            "theta_per_day": metrics.get("theta_per_day"),
            "max_loss": metrics.get("max_loss"),
        },
        "modeled_alternative": {
            "strategy": row.get("top_modeled_strategy"),
            "composite_score": modeled.get("composite_score"),
            "pop": modeled.get("pop"),
            "expected_value": modeled.get("expected_value"),
        },
        "trade_decision": {
            "status": decision.get("status"),
            "open_recommended": decision.get("open_recommended"),
            "entry_quality": decision.get("entry_quality"),
            "reason": decision.get("reason"),
        },
        "warnings": warnings,
        "registry_alignment": dict(registry_alignment) if registry_alignment else None,
        "congress_boost": ticker in (congress_tickers or frozenset()),
        "days_to_exp": dte,
        "deep_dive_cmd": f"nave options analyze --ticker {ticker} --days-to-exp {dte}",
    }


def format_position_digest_line(ctx: Mapping[str, Any]) -> str:
    """Single-line summary for gem digest output."""
    metrics = ctx.get("metrics") or {}
    legs = ctx.get("setup_summary") or "legs n/a"
    strategy = str(ctx.get("strategy") or "").replace("_", " ")
    pop = _fmt_num(metrics.get("pop"), decimals=0)
    touch = _fmt_num(metrics.get("probability_of_touch"), decimals=0)
    ev = _fmt_num(metrics.get("expected_value"), decimals=0, prefix="$")
    max_loss = _fmt_num(metrics.get("max_loss"), decimals=0, prefix="$")
    bias = ctx.get("bias") or "n/a"
    congress = " [congress]" if ctx.get("congress_boost") else ""
    return (
        f"{ctx.get('ticker')}{congress} {strategy} ({bias}) | {legs} | "
        f"PoP {pop}% touch {touch}% EV {ev} max loss {max_loss}"
    )


def format_position_panel_lines(ctx: Mapping[str, Any]) -> list[str]:
    """Multi-line panel body for terminal detail cards."""
    metrics = ctx.get("metrics") or {}
    decision = ctx.get("trade_decision") or {}
    modeled = ctx.get("modeled_alternative") or {}
    lines = [
        f"Strategy: {str(ctx.get('strategy') or 'n/a').replace('_', ' ')}",
        f"Bias: {ctx.get('bias') or 'n/a'} | ~{ctx.get('days_to_exp')} DTE target",
        f"Position: {ctx.get('setup_summary') or 'n/a'}",
    ]
    if ctx.get("thesis"):
        lines.append(f"Thesis: {ctx['thesis']}")
    if ctx.get("rationale"):
        lines.append(f"Rationale: {ctx['rationale']}")
    lines.append(
        "Risk / reward: "
        f"score={_fmt_num(metrics.get('composite_score'), decimals=1)} "
        f"PoP={_fmt_num(metrics.get('pop'), decimals=1)}% "
        f"touch={_fmt_num(metrics.get('probability_of_touch'), decimals=1)}% "
        f"EV={_fmt_num(metrics.get('expected_value'), decimals=0, prefix='$')} "
        f"max_loss={_fmt_num(metrics.get('max_loss'), decimals=0, prefix='$')} "
        f"theta/day={_fmt_num(metrics.get('theta_per_day'), decimals=2, prefix='$')}"
    )
    if decision:
        open_rec = decision.get("open_recommended")
        lines.append(
            "Decision: "
            f"{decision.get('status') or 'n/a'} "
            f"| open_recommended={open_rec} "
            f"| quality={decision.get('entry_quality') or 'n/a'}"
        )
    if modeled.get("strategy"):
        lines.append(
            "Top modeled (not executable pick): "
            f"{str(modeled.get('strategy')).replace('_', ' ')} "
            f"score={_fmt_num(modeled.get('composite_score'), decimals=1)} "
            f"EV={_fmt_num(modeled.get('expected_value'), decimals=0, prefix='$')}"
        )
    if ctx.get("congress_boost"):
        lines.append("Congress: ticker appears in recent STOCK Act disclosures (boost applied).")
    warnings = ctx.get("warnings") or []
    if warnings:
        lines.append("Warnings: " + " | ".join(str(w) for w in warnings[:3]))
    lines.append(f"Deep dive: {ctx.get('deep_dive_cmd')}")
    return lines