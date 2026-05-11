"""Agent-facing formatters for options analysis payloads."""

from __future__ import annotations

from typing import Any


def render_options_scan_markdown_v2(payload: dict[str, Any]) -> list[str]:
    """Render a compact Telegram MarkdownV2 digest for Hermes output."""
    ticker = str(payload.get("ticker") or "?")
    underlying = payload.get("underlying_analysis") or {}
    overlay = payload.get("analysis_overlay") or {}
    price = underlying.get("price")
    iv = (underlying.get("implied_volatility") or {}).get("iv_mean")
    hv = (underlying.get("historical_volatility") or {}).get("hv_30")
    final_recs = overlay.get("final_recommendations") or {}
    executive_summary = list(overlay.get("executive_summary") or [])
    warnings = list(overlay.get("warnings") or [])

    recs = payload.get("recommendations") or []
    lines = [
        "*NAVE Options Scan*",
        f"Ticker: *{ticker}*",
        f"Price: {price}",
        f"IV mean / HV30: {iv} / {hv}",
    ]

    if executive_summary:
        lines.append("Executive summary:")
        for bullet in executive_summary[:2]:
            lines.append(f"- {bullet}")

    conservative = final_recs.get("best_conservative_executable_setup") or {}
    aggressive = final_recs.get("best_aggressive_setup") or {}
    modeled = final_recs.get("best_modeled_setup") or {}
    if modeled:
        lines.append(
            "Modeled: "
            f"{str(modeled.get('strategy_name') or 'n/a').replace('_', ' ')}"
            f" | EV {(modeled.get('metrics') or {}).get('expected_value')}"
        )
    if conservative:
        lines.append(
            "Conservative: "
            f"{str(conservative.get('strategy_name') or 'n/a').replace('_', ' ')}"
            f" | EV {(conservative.get('metrics') or {}).get('expected_value')}"
        )
    if aggressive:
        lines.append(
            "Aggressive: "
            f"{str(aggressive.get('strategy_name') or 'n/a').replace('_', ' ')}"
            f" | EV {(aggressive.get('metrics') or {}).get('expected_value')}"
        )

    if recs:
        lines.append("Top strategies:")
        for idx, rec in enumerate(recs[:3], start=1):
            strategy = ((rec.get("strategy") or {}).get(
                "name") or "unknown").replace("_", " ")
            score = (rec.get("metrics") or {}).get("composite_score")
            pop = (rec.get("metrics") or {}).get("pop")
            ev = (rec.get("metrics") or {}).get("expected_value")
            touch = (rec.get("metrics") or {}).get("probability_of_touch")
            tradeoff = rec.get("tradeoff_comment") or ""
            lines.append(
                f"{idx}. {strategy} | score {score} | PoP {pop}% | EV {ev} | Touch {touch}%")
            if tradeoff:
                lines.append(f"   - {tradeoff}")

    if warnings:
        lines.append("Warnings:")
        for warning in warnings[:3]:
            lines.append(f"- {warning}")

    return ["\n".join(lines)]
