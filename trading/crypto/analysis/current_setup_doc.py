"""Render ``docs/analysis/current_setup.md`` from the operator stack (not theory_v2 alone)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from trading.crypto.analysis.review import format_options_display, review_positions
from trading.crypto.theory_v2 import build_signals_for_coins


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 1000:
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def _fmt_zone(zone: list[float] | None) -> str:
    if not zone:
        return "—"
    if len(zone) == 1:
        return _fmt_price(zone[0])
    return f"{_fmt_price(zone[0])} – {_fmt_price(zone[1])}"


def _options_section(options: dict[str, Any] | None) -> list[str]:
    if not options or options.get("status") != "ready":
        status = (options or {}).get("status", "unavailable")
        reason = (options or {}).get("reason")
        lines = [f"- Deribit options: **{status}**"]
        if reason:
            lines.append(f"  - {reason}")
        return lines

    lane = options.get("execution_lane", "options_advisory")
    lines = [
        f"- Deribit options lane: **{lane.replace('_', ' ')}**",
        f"- Ranked structure: `{options.get('strategy')}` "
        f"(bias {options.get('directional_bias', '—')})",
    ]
    m = options.get("metrics") or {}
    if m:
        parts = []
        if m.get("pop_pct") is not None:
            parts.append(f"POP {m['pop_pct']}%")
        if m.get("probability_of_touch_pct") is not None:
            parts.append(f"touch {m['probability_of_touch_pct']}%")
        if m.get("expected_value") is not None:
            parts.append(f"EV {m['expected_value']}")
        if parts:
            lines.append(f"  - Metrics: {', '.join(parts)}")
    if lane == "options_advisory":
        lines.append(
            "  - **Advisory only** — quality gate blocked execution "
            "(income-first design; high touch / no conservative spread)."
        )
        if options.get("advisory_reason"):
            lines.append(f"  - {options['advisory_reason']}")
        blockers = options.get("quality_blockers") or []
        if blockers:
            lines.append(f"  - Blockers: `{', '.join(blockers[:3])}`")
    elif options.get("trade_decision") == "trade_candidate":
        lines.append("  - **Executable** — passed actionable quality gate.")
    display = format_options_display(options)
    if display:
        lines.append(f"  - Summary: {display}")
    return lines


def render_current_setup_markdown(
    review: dict[str, Any],
    *,
    theory_by_coin: dict[str, Any] | None = None,
) -> str:
    """Build markdown for BTC/ETH from ``review_positions`` output."""
    generated = review.get("generated_at") or datetime.now(timezone.utc).isoformat()
    theory_by_coin = theory_by_coin or {}

    lines = [
        "# Current Setup — BTC and ETH",
        "",
        f"> **Generated:** {generated[:10]} (operator stack: `nave daily` / `crypto position-review`)",
        "> **Canonical entry:** COT + regime thesis + momentum 4H/1H + optional Deribit options",
        "> **Theory v2 trace:** included per coin below — may differ from ENTER/WATCH when regime leads",
        "",
        "**Do not use theory_v2 alone for entries.** The unified review can be bearish while",
        "theory card still shows STAND ASIDE on weekly gates, or the reverse during transitions.",
        "",
        "## Operator summary",
        "",
    ]

    summary = review.get("summary") or {}
    lines.append(
        f"- Enter: **{summary.get('actionable_count', 0)}** · "
        f"Watch: **{summary.get('watch_count', 0)}** · "
        f"Stand aside: **{summary.get('stand_aside_count', 0)}**"
    )
    lines.append("")

    for rec in review.get("recommendations") or []:
        coin = rec.get("coin", "?")
        action = str(rec.get("action", "stand_aside")).upper()
        direction = rec.get("direction") or "—"
        lines.extend([
            f"## {coin}",
            "",
            "```",
            f"ACTION    : {action}",
            f"DIRECTION : {direction}",
            f"SOURCE    : {rec.get('primary_source', '—')}",
            f"REGIME    : {rec.get('regime_phase', '—')}",
            "```",
            "",
            f"- Confidence: **{float(rec.get('confidence') or 0):.0%}**",
            f"- Entry zone: {_fmt_zone(rec.get('entry_zone'))}",
            f"- Invalidation: {_fmt_price(rec.get('invalidation'))}",
        ])
        targets = rec.get("targets") or []
        if targets:
            lines.append(
                f"- Targets: {', '.join(_fmt_price(t) for t in targets)}"
            )
        lines.append(f"- Playbook: {rec.get('playbook') or '—'}")
        lines.append(f"- COT: **{rec.get('cot_bias') or '—'}** · Theory stage: `{rec.get('theory_stage')}`")

        thesis = rec.get("thesis") or {}
        if thesis.get("thesis_state") == "active":
            lines.append(
                f"- Regime thesis: **{thesis.get('thesis_status')}** "
                f"({thesis.get('thesis_phase')}, since {str(thesis.get('thesis_created_at', ''))[:10]})"
            )

        lines.append("")
        lines.append("**Reasons**")
        for reason in rec.get("reasons") or []:
            lines.append(f"- {reason}")
        blockers = rec.get("blockers") or []
        if blockers:
            lines.append("")
            lines.append("**Blockers**")
            for blocker in blockers:
                lines.append(f"- {blocker}")

        lines.append("")
        lines.append("**Instruments**")
        instruments = rec.get("instruments") or []
        if instruments:
            lines.append(f"- Active lanes: `{', '.join(instruments)}`")
        else:
            lines.append("- No directional lane")

        lines.append("")
        lines.extend(_options_section(rec.get("options")))

        secondary = rec.get("secondary_opportunities") or []
        if secondary:
            lines.append("")
            lines.append("**Secondary opportunities**")
            for opp in secondary:
                lines.append(
                    f"- `{opp.get('kind', '—')}` **{str(opp.get('direction', '—')).upper()}** "
                    f"({float(opp.get('confidence') or 0):.0%}) — {opp.get('playbook', '—')}"
                )
                lines.append(f"  - Entry: {_fmt_zone(opp.get('entry_zone'))}")
                if opp.get("invalidation") is not None:
                    lines.append(f"  - Stop: {_fmt_price(opp['invalidation'])}")
                if opp.get("size_fraction") is not None:
                    lines.append(f"  - Size: {float(opp['size_fraction']):.0%} of base risk")
                opp_targets = opp.get("targets") or []
                if opp_targets:
                    lines.append(
                        f"  - Targets: {', '.join(_fmt_price(t) for t in opp_targets[:3])}"
                    )
                for blocker in (opp.get("blockers") or [])[:2]:
                    lines.append(f"  - Blocker: {blocker}")

        ctx = rec.get("market_context") or {}
        if ctx.get("cot_percentile") is not None:
            lines.append("")
            lines.append("**Market context**")
            lines.append(f"- COT percentile: P{ctx['cot_percentile']}")
            metrics = ctx.get("regime_metrics") or {}
            if metrics.get("drawdown_from_28d_high_pct") is not None:
                lines.append(
                    f"- Drawdown from 28d high: {metrics['drawdown_from_28d_high_pct']:.1f}%"
                )
            if metrics.get("bounce_from_14d_low_pct") is not None:
                lines.append(
                    f"- Bounce from 14d low: {metrics['bounce_from_14d_low_pct']:.1f}%"
                )

        theory = theory_by_coin.get(coin)
        if theory is not None:
            fired = bool(getattr(theory, "fired", False) or getattr(theory, "signal", None))
            lines.extend([
                "",
                "**Theory v2 trace (reference)**",
                f"- Stage: `{getattr(theory, 'stage', '—')}`",
                f"- Fired: **{fired}**",
            ])
            if getattr(theory, "reason", None):
                lines.append(f"- Gate note: {theory.reason}")

        lines.append("")

    lines.extend([
        "## How to refresh",
        "",
        "```bash",
        "nave daily --coins BTC,ETH",
        "# or",
        "python scripts/refresh_current_setup.py",
        "python scripts/daily_scan.py --refresh-setup-doc",
        "```",
        "",
        "Writes this file from `review_positions()` plus theory_v2 trace. "
        "Regime theses persist in `var/state/regime_theses.json`.",
        "",
    ])
    return "\n".join(lines)


def build_current_setup_review(
    coins: list[str] | str = "BTC ETH",
    **review_kwargs: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(coins, str):
        coin_list = [c.strip().upper() for c in coins.replace(",", " ").split() if c.strip()]
    else:
        coin_list = [c.upper() for c in coins]
    review = review_positions(coin_list, **review_kwargs)
    _, theory_decisions = build_signals_for_coins(coin_list)
    theory_by_coin = {d.coin: d for d in theory_decisions}
    return review, theory_by_coin
