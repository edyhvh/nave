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


def _quality_blockers(trade_decision: dict[str, Any]) -> list[str]:
    gate = trade_decision.get("quality_gate")
    if not isinstance(gate, dict):
        return []
    blockers = gate.get("blockers")
    return [str(b) for b in blockers] if isinstance(blockers, list) else []


def _advisory_reason(
    *,
    trade_status: str | None,
    blockers: list[str],
    strategy: str | None,
) -> str | None:
    if trade_status == "trade_candidate":
        return None
    if blockers:
        human = ", ".join(b.replace("_", " ") for b in blockers[:2])
        return f"Ranked {strategy or 'setup'} failed quality gate: {human}."
    if trade_status and trade_status != "trade_candidate":
        return (
            f"Ranked {strategy or 'setup'} is research-only ({trade_status}); "
            "perp/regime lane is the actionable path."
        )
    return (
        "No structure passed the conservative executable filter; "
        "use perp thesis or wait for lower touch / richer premium."
    )


def summarize_options_opportunity(opp: dict[str, Any]) -> dict[str, Any]:
    """Compact options card from ``OptionsAnalyzer.scan_crypto_opportunities`` row."""
    if opp.get("status") != "ready":
        return {
            "status": opp.get("status", "unavailable"),
            "reason": opp.get("reason") or opp.get("error"),
            "execution_lane": "unavailable",
        }
    exec_m = normalize_options_metrics(opp.get("executable_metrics"))
    top_m = normalize_options_metrics(opp.get("top_metrics"))
    strategy = opp.get("executable_strategy") or opp.get("top_strategy")
    metrics = exec_m if exec_m.get("composite_score") is not None else top_m
    trade_decision = opp.get("trade_decision") or {}
    status = trade_decision.get("status") if isinstance(trade_decision, dict) else None
    blockers = _quality_blockers(trade_decision)
    executable = bool(opp.get("executable_strategy")) and status == "trade_candidate"
    execution_lane = "options_executable" if executable else "options_advisory"
    out: dict[str, Any] = {
        "status": "ready",
        "directional_bias": opp.get("directional_bias"),
        "strategy": strategy,
        "trade_decision": status,
        "metrics": metrics,
        "executable_strategy": opp.get("executable_strategy"),
        "top_strategy": opp.get("top_strategy"),
        "execution_lane": execution_lane,
        "quality_blockers": blockers,
    }
    if execution_lane == "options_advisory":
        out["advisory_reason"] = _advisory_reason(
            trade_status=status,
            blockers=blockers,
            strategy=strategy,
        )
    return out