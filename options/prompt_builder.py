"""Prompt-building helpers for options analysis payloads."""

from __future__ import annotations

import json
from pathlib import Path


def _as_float(value: object) -> float | None:
    try:
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float, str)):
            return float(value)
    except (TypeError, ValueError):
        return None
    return None


def _filtered_prompt_strategy_names(recs: list[dict]) -> list[str]:
    names: list[str] = []
    for rec in recs[:3]:
        strategy = (rec.get("strategy") or {}).get("name")
        metrics = rec.get("metrics") or {}
        score = _as_float(metrics.get("composite_score"))
        expected_value = _as_float(metrics.get("expected_value"))
        if not strategy:
            continue
        if (score is not None and score > 30.0) or (expected_value is not None and expected_value > 0.0):
            names.append(str(strategy))
    return names


def build_llm_prompt(payload: dict) -> str:
    ticker = str(payload.get("ticker") or "UNKNOWN")
    underlying = payload.get("underlying_analysis") or {}
    overlay = payload.get("analysis_overlay") or {}
    recs = payload.get("recommendations") or []

    top_names = _filtered_prompt_strategy_names(recs)
    strategy_list = ", ".join(
        top_names) if top_names else "none met the quality filter"
    overlay_sections = [
        name
        for name in [
            "executive_summary",
            "volatility_market_context",
            "strategy_comparison",
            "final_recommendations",
            "risk_management_framework",
            "what_to_monitor_next",
        ]
        if overlay.get(name)
    ]
    overlay_summary = ", ".join(
        overlay_sections) if overlay_sections else "none"

    payload_for_prompt = strip_paths_for_prompt(payload)
    payload_blob = json.dumps(payload_for_prompt, indent=2, default=str)

    return "\n".join(
        [
            "You are an advanced options strategy analyst with quantitative + practical short-premium execution expertise.",
            f"Analyze ticker: {ticker}",
            f"Current price: {underlying.get('price')}",
            f"Top strategies in report: {strategy_list}",
            f"Structured practical overlay sections: {overlay_summary}",
            "Input data will be provided separately as JSON payload and llm_paths block.",
            "Use the analyzer's structured overlay as the preferred practical interpretation layer when it is present.",
            "Always apply trader_income_lens: rich IV selective premium selling, 3-6% OTM short strikes, realistic width, and strict risk management.",
            "Tasks:",
            "1. Summarize volatility regime and market context from the report.",
            "2. Compare strategies by PoP, EV, max loss, probability of touch, forgivingness score, theta/day, and executable realism.",
            "3. Distinguish clearly between highest modeled setup, best conservative executable setup, and best aggressive setup.",
            "3a. Distinguish clearly between the highest modeled setup, the best conservative executable setup, and the best aggressive setup.",
            "4. If IV Rank >= 90 or IV Percentile >= 80, actively test whether a 3-6% OTM bull put credit spread is the best income expression before recommending long volatility.",
            "5. Lower confidence in long straddles/strangles when Probability of Touch > 85%; describe the psychological path risk instead of treating PoP as sufficient.",
            "6. Do not call a setup conservative if EV is materially negative, touch risk is above 75-80%, theta is negative, or max loss is disproportionate to account risk.",
            "7. If trade_decision.status is no_trade, say no trade/wait clearly; do not turn the relative rank #1 into an actionable recommendation.",
            "8. Provide invalidation logic, risk guardrails, and position-sizing guidance.",
            "9. Warn explicitly if highest modeled setup has negative EV or Probability of Touch > 85%.",
            "8a. Warn the user if the highest-ranked strategy has negative expected value.",
            "10. Explicitly call out tight condors/spreads when too narrow vs expected move, and mention wider 3-6% OTM bull put spreads when execution quality is better.",
            "Output format:",
            "- Executive Summary (3-4 bullets)",
            "- Strategy Comparison Table (Strategy, PoP, EV, Max Loss, Prob. Touch, Forgivingness Score, Theta/Day, Key Commentary)",
            "- Practical Trader Lens",
            "- Final Recommendation (highest modeled vs conservative executable vs aggressive)",
            "- Risks, Invalidation Logic, and What to Monitor Next",
            "JSON data (paths removed):",
            "```json",
            payload_blob,
            "```",
        ]
    )


def strip_paths_for_prompt(value: object) -> object:
    if isinstance(value, dict):
        cleaned: dict[str, object] = {}
        for key, item in value.items():
            k = str(key).lower()
            if k == "llm_paths":
                continue
            if k == "charts" and isinstance(item, dict):
                cleaned[str(key)] = {
                    str(name): "[path omitted]" for name in item.keys()}
                continue
            if "path" in k:
                continue
            cleaned[str(key)] = strip_paths_for_prompt(item)
        return cleaned
    if isinstance(value, list):
        return [strip_paths_for_prompt(item) for item in value]
    return value


def build_llm_paths(payload: dict, json_report_path: Path | None) -> dict:
    return {
        "json_report_path": str(json_report_path) if json_report_path is not None else None,
        "charts": payload.get("charts") or {},
    }
