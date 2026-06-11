"""ETH weekly options decision rules for small-account execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BULLISH_STRUCTURES = {
    "bull_call_debit_spread",
    "bull_put_credit_spread",
    "long_straddle",
    "long_strangle",
}
BEARISH_STRUCTURES = {
    "bear_put_debit_spread",
    "bear_call_credit_spread",
    "long_straddle",
    "long_strangle",
}
DEBIT_SPREADS = {"bull_call_debit_spread", "bear_put_debit_spread"}
CREDIT_SPREADS = {"bull_put_credit_spread", "bear_call_credit_spread"}
LONG_VOL = {"long_straddle", "long_strangle"}


@dataclass(frozen=True)
class EthWeeklyOptionsProfile:
    account_equity: float = 1000.0
    max_loss_usd: float = 20.0
    max_a_plus_loss_usd: float = 30.0
    min_confidence: float = 90.0
    a_plus_confidence: float = 95.0
    a_plus_min_rr: float = 2.0
    min_pop: float = 55.0
    max_touch: float = 82.0
    min_expected_value: float = 0.0


def _as_float(value: Any) -> float | None:
    try:
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float, str)):
            return float(value)
    except (TypeError, ValueError):
        return None
    return None


def _strategy_name(candidate: dict[str, Any]) -> str | None:
    name = candidate.get("strategy_name")
    if name:
        return str(name)
    strategy = candidate.get("strategy") or {}
    name = strategy.get("name")
    return str(name) if name else None


def _metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    return dict(candidate.get("metrics") or {})


def _candidate_snapshot(candidate: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    name = _strategy_name(candidate)
    if not name:
        return None
    metrics = _metrics(candidate)
    return {
        "source": source,
        "strategy_name": name,
        "metrics": {
            "composite_score": _as_float(metrics.get("composite_score")),
            "pop": _as_float(metrics.get("pop")),
            "expected_value": _as_float(metrics.get("expected_value")),
            "probability_of_touch": _as_float(metrics.get("probability_of_touch")),
            "max_loss": _as_float(metrics.get("max_loss")),
            "risk_reward": _as_float(metrics.get("risk_reward")),
        },
        "setup_summary": candidate.get("setup_summary"),
        "thesis": candidate.get("thesis"),
        "rationale": candidate.get("rationale"),
    }


def _extract_candidates(options_payload: dict[str, Any]) -> list[dict[str, Any]]:
    overlay = options_payload.get("analysis_overlay") or {}
    final = overlay.get("final_recommendations") or {}
    raw: list[tuple[str, dict[str, Any]]] = []
    for key in (
        "best_overall_executable_setup",
        "best_conservative_executable_setup",
        "best_aggressive_setup",
    ):
        value = final.get(key)
        if isinstance(value, dict):
            raw.append((key, value))

    snapshots: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source, candidate in raw:
        snap = _candidate_snapshot(candidate, source=source)
        if snap is None:
            continue
        key = (snap["strategy_name"], source)
        if key in seen:
            continue
        seen.add(key)
        snapshots.append(snap)
    return snapshots


def _allowed_for_side(strategy_name: str, side: str | None) -> bool:
    normalized = str(side or "").lower()
    if normalized == "long":
        return strategy_name in BULLISH_STRUCTURES
    if normalized == "short":
        return strategy_name in BEARISH_STRUCTURES
    return False


def _structure_priority(strategy_name: str) -> int:
    if strategy_name in DEBIT_SPREADS:
        return 4
    if strategy_name in CREDIT_SPREADS:
        return 3
    if strategy_name in LONG_VOL:
        return 2
    return 1


def _candidate_passes(
    candidate: dict[str, Any],
    profile: EthWeeklyOptionsProfile,
    *,
    a_plus: bool,
) -> tuple[bool, list[str]]:
    metrics = candidate.get("metrics") or {}
    blockers: list[str] = []
    max_loss = _as_float(metrics.get("max_loss"))
    pop = _as_float(metrics.get("pop"))
    touch = _as_float(metrics.get("probability_of_touch"))
    ev = _as_float(metrics.get("expected_value"))
    strategy_name = str(candidate.get("strategy_name") or "")

    if max_loss is None:
        blockers.append("missing_max_loss")
    elif max_loss > profile.max_loss_usd:
        if a_plus and max_loss <= profile.max_a_plus_loss_usd:
            blockers.append("requires_a_plus_manual_review")
        elif a_plus:
            blockers.append(f"max_loss_above_{profile.max_a_plus_loss_usd:.0f}_usd")
        else:
            blockers.append(f"max_loss_above_{profile.max_loss_usd:.0f}_usd")

    if pop is not None and pop < profile.min_pop and strategy_name not in DEBIT_SPREADS:
        blockers.append(f"pop_below_{profile.min_pop:.0f}")
    if touch is not None and touch > profile.max_touch:
        blockers.append(f"touch_above_{profile.max_touch:.0f}")
    if ev is not None and ev < profile.min_expected_value:
        blockers.append("negative_expected_value")

    return not blockers, blockers


def _rank_candidate(candidate: dict[str, Any]) -> tuple[int, float, float, float]:
    metrics = candidate.get("metrics") or {}
    return (
        _structure_priority(str(candidate.get("strategy_name") or "")),
        _as_float(metrics.get("composite_score")) or 0.0,
        _as_float(metrics.get("expected_value")) or -1e9,
        -(_as_float(metrics.get("probability_of_touch")) or 100.0),
    )


def build_eth_weekly_decision(
    scan_payload: dict[str, Any],
    *,
    profile: EthWeeklyOptionsProfile | None = None,
) -> dict[str, Any]:
    """Convert a crypto options scan into a clear ETH weekly options decision."""
    prof = profile or EthWeeklyOptionsProfile()
    opportunity = (scan_payload.get("opportunities") or {}).get("ETH") or {}
    status = str(opportunity.get("status") or "missing")
    momentum = opportunity.get("momentum") or {}
    side = str(momentum.get("side") or "").lower() or None
    confidence = _as_float(momentum.get("confidence_score")) or 0.0
    rr_estimated = _as_float(momentum.get("rr_estimated")) or 0.0
    tradeable = bool(momentum.get("tradeable"))
    a_plus = confidence >= prof.a_plus_confidence and rr_estimated >= prof.a_plus_min_rr

    base = {
        "coin": "ETH",
        "strategy": "eth_weekly_options_cot_momentum_v1",
        "decision": "STAND_ASIDE",
        "reason": "",
        "profile": {
            "account_equity": prof.account_equity,
            "max_loss_usd": prof.max_loss_usd,
            "max_a_plus_loss_usd": prof.max_a_plus_loss_usd,
            "min_confidence": prof.min_confidence,
            "a_plus_confidence": prof.a_plus_confidence,
            "a_plus_min_rr": prof.a_plus_min_rr,
            "min_pop": prof.min_pop,
            "max_touch": prof.max_touch,
            "min_expected_value": prof.min_expected_value,
        },
        "momentum": {
            "side": side,
            "tradeable": tradeable,
            "confidence_score": confidence,
            "entry_zone": momentum.get("entry_zone"),
            "invalidation": momentum.get("invalidation"),
            "rr_estimated": rr_estimated,
            "setup_status": momentum.get("setup_status"),
            "a_plus": a_plus,
        },
        "option": None,
        "watch": [],
        "blockers": [],
        "source_summary": scan_payload.get("summary") or {},
    }

    if status != "ready":
        base["decision"] = "WATCH" if status in {"filtered_by_momentum", "options_unavailable"} else "STAND_ASIDE"
        base["reason"] = str(opportunity.get("reason") or opportunity.get("error") or status)
        base["blockers"].append(status)
        return base

    if not tradeable:
        base["decision"] = "WATCH"
        base["reason"] = "ETH has options data, but the 4H/1H momentum setup is not tradeable."
        base["blockers"].append("momentum_not_tradeable")
        return base

    if confidence < prof.min_confidence:
        base["decision"] = "WATCH"
        base["reason"] = f"Momentum confidence {confidence} is below weekly-options threshold {prof.min_confidence}."
        base["blockers"].append("confidence_below_threshold")
        return base

    candidates = [
        candidate
        for candidate in _extract_candidates(opportunity.get("options") or {})
        if _allowed_for_side(str(candidate.get("strategy_name") or ""), side)
    ]
    if not candidates:
        base["decision"] = "WATCH"
        base["reason"] = "No executable ETH option structure is aligned with the current momentum side."
        base["blockers"].append("no_side_aligned_executable_structure")
        return base

    evaluated: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for candidate in candidates:
        ok, blockers = _candidate_passes(candidate, prof, a_plus=a_plus)
        item = {**candidate, "small_account_ok": ok, "blockers": blockers}
        evaluated.append(item)
        if ok:
            passed.append(item)

    if not passed:
        base["decision"] = "WATCH"
        base["reason"] = "Underlying setup is valid, but no ETH option structure fits the small-account risk guard."
        base["watch"] = evaluated[:5]
        base["blockers"].append("no_small_account_option_structure")
        return base

    selected = max(passed, key=_rank_candidate)
    base["decision"] = "ENTER"
    base["reason"] = "COT/momentum gate passed and a small-account-valid ETH option structure is available."
    base["option"] = selected
    base["watch"] = evaluated[:5]
    return base
