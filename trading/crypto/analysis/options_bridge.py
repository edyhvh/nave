"""Normalize options scan output for BTC/ETH review."""

from __future__ import annotations

from typing import Any


def _normalize_pct(value: object) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1.5:
        return round(v, 2)
    return round(v * 100, 2)


def _normalize_ev(value: object) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if abs(v) > 10_000:
        return round(v / 1000, 2)
    return round(v, 2)


def normalize_options_metrics(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    return {
        "composite_score": raw.get("composite_score"),
        "pop_pct": _normalize_pct(raw.get("pop")),
        "expected_value": _normalize_ev(raw.get("expected_value")),
        "probability_of_touch_pct": _normalize_pct(raw.get("probability_of_touch")),
    }


def summarize_options_opportunity(opp: dict[str, Any]) -> dict[str, Any]:
    """Compact options card from ``OptionsAnalyzer.scan_crypto_opportunities`` row."""
    if opp.get("status") != "ready":
        return {
            "status": opp.get("status", "unavailable"),
            "reason": opp.get("reason") or opp.get("error"),
        }
    exec_m = normalize_options_metrics(opp.get("executable_metrics"))
    top_m = normalize_options_metrics(opp.get("top_metrics"))
    strategy = opp.get("executable_strategy") or opp.get("top_strategy")
    metrics = exec_m if exec_m.get("composite_score") is not None else top_m
    trade_decision = opp.get("trade_decision") or {}
    status = trade_decision.get("status") if isinstance(trade_decision, dict) else None
    return {
        "status": "ready",
        "directional_bias": opp.get("directional_bias"),
        "strategy": strategy,
        "trade_decision": status,
        "metrics": metrics,
        "executable_strategy": opp.get("executable_strategy"),
        "top_strategy": opp.get("top_strategy"),
    }