"""Agent-facing formatters for options analysis payloads."""

from __future__ import annotations

from typing import Any


def render_options_scan_markdown_v2(payload: dict[str, Any]) -> list[str]:
    """Render a compact Telegram MarkdownV2 digest for Hermes output."""
    ticker = str(payload.get("ticker") or "?")
    underlying = payload.get("underlying_analysis") or {}
    price = underlying.get("price")
    iv = (underlying.get("implied_volatility") or {}).get("iv_mean")
    hv = (underlying.get("historical_volatility") or {}).get("hv_30")

    recs = payload.get("recommendations") or []
    lines = [
        "*NAVE Options Scan*",
        f"Ticker: *{ticker}*",
        f"Price: {price}",
        f"IV mean / HV30: {iv} / {hv}",
    ]

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

    return ["\n".join(lines)]
