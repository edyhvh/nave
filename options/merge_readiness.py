"""Merge-readiness gates for per-ticker strategy (production playbook)."""

from __future__ import annotations

from typing import Any, Mapping

MIN_APPROVED_TICKERS = 6
MIN_WATCH_TICKERS = 15


def assess_merge_status(
    learned: Mapping[str, Any],
    walkforward: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Classify a ticker's learned strategy for merge/production use.

    Returns merge_status: approved | watch | reject
    """
    primary = learned.get("primary") or {}
    strat = primary.get("strategy")
    edge = float(primary.get("edge_score") or 0)
    wr = float(primary.get("win_rate") or 0)
    trades = int(primary.get("trades") or 0)
    conf = str(learned.get("confidence") or "low")
    wf = walkforward or {}
    oos_wr = wf.get("oos_win_rate")
    oos_n = int(wf.get("oos_trades") or 0)
    stable = bool(wf.get("primary_stable"))
    last_primary = wf.get("last_primary")

    reasons: list[str] = []
    if not strat:
        return {
            "merge_status": "reject",
            "validated_setup": None,
            "reasons": ["no_learned_strategy"],
        }

    validated = str(last_primary) if stable and last_primary else strat

    # --- approved (tradeable in production playbook) ---
    if edge >= 50 and wr >= 0.55 and trades >= 3 and conf in {"high", "medium"}:
        reasons.append("strong_in_sample_edge_and_win_rate")
        return _approved(validated, reasons)

    if edge >= 14 and trades >= 4 and wr >= 0.38:
        reasons.append("income_playbook_moderate_edge")
        return _approved(validated, reasons)

    if edge >= 20 and trades >= 2 and wr >= 0.5:
        reasons.append("high_win_rate_income")
        return _approved(validated, reasons)

    if edge >= 35 and oos_n >= 3 and oos_wr is not None and oos_wr >= 0.45:
        reasons.append("oos_validated")
        return _approved(validated, reasons)

    if edge >= 40 and oos_n >= 5 and oos_wr is not None and oos_wr >= 0.40:
        reasons.append("oos_volume_validated")
        return _approved(validated, reasons)

    if stable and edge >= 28 and oos_n >= 3 and oos_wr is not None and oos_wr >= 0.35:
        reasons.append("stable_walkforward_primary")
        return _approved(validated, reasons)

    # --- watch (learned but size small / OOS thin) ---
    if trades >= 2 and strat:
        reasons.append("income_playbook_has_history")
        return _watch(validated, reasons)

    if edge >= 22 and trades >= 2:
        reasons.append("moderate_edge_review_oos")
        return _watch(validated, reasons)

    if oos_n >= 2 and oos_wr is not None and oos_wr >= 0.5:
        reasons.append("promising_oos_small_sample")
        return _watch(validated, reasons)

    if trades >= 2 and wr >= 0.38:
        reasons.append("decent_win_rate_low_edge_score")
        return _watch(validated, reasons)

    # --- reject ---
    if edge < 12 and (oos_wr is None or (oos_n >= 2 and oos_wr < 0.35)):
        return _reject(reasons + ["low_edge_and_weak_oos"])

    if trades < 2:
        return _reject(reasons + ["insufficient_replay_trades"])

    return _reject(reasons + ["did_not_meet_approval_or_watch_gates"])


def _approved(setup: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "merge_status": "approved",
        "validated_setup": setup,
        "reasons": reasons,
        "horizon": "walkforward_replay",
        "horizon_note": (
            "Approved for the income playbook from replay/OOS — not a guarantee for "
            "this week's directional tape; align live bias before full size."
        ),
    }


def _watch(setup: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "merge_status": "watch",
        "validated_setup": setup,
        "reasons": reasons,
    }


def _reject(reasons: list[str]) -> dict[str, Any]:
    return {
        "merge_status": "reject",
        "validated_setup": None,
        "reasons": reasons,
    }


def summarize_registry_merge_readiness(
    profiles: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Universe-level merge verdict for branch merge."""
    approved: list[str] = []
    watch: list[str] = []
    reject: list[str] = []

    for sym, profile in sorted(profiles.items()):
        learned = profile.get("learned_strategy") or {}
        merge = learned.get("merge") or assess_merge_status(
            learned, learned.get("walkforward")
        )
        status = merge.get("merge_status", "reject")
        if status == "approved":
            approved.append(sym)
        elif status == "watch":
            watch.append(sym)
        else:
            reject.append(sym)

    ready = len(approved) >= MIN_APPROVED_TICKERS and len(watch) >= MIN_WATCH_TICKERS
    return {
        "ready_to_merge": ready,
        "min_approved": MIN_APPROVED_TICKERS,
        "min_watch": MIN_WATCH_TICKERS,
        "counts": {
            "approved": len(approved),
            "watch": len(watch),
            "reject": len(reject),
            "total": len(profiles),
        },
        "approved_tickers": approved,
        "watch_tickers": watch,
        "reject_tickers": reject,
        "blockers": [] if ready else _blockers(len(approved), len(watch)),
    }


def _blockers(approved: int, watch: int) -> list[str]:
    out: list[str] = []
    if approved < MIN_APPROVED_TICKERS:
        out.append(f"need {MIN_APPROVED_TICKERS} approved tickers (have {approved})")
    if watch < MIN_WATCH_TICKERS:
        out.append(f"need {MIN_WATCH_TICKERS} watch tickers (have {watch})")
    return out