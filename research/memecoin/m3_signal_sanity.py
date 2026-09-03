"""Offline contracts and diagnostics for the M3 statistical signal sanity check.

This module intentionally contains no provider, network, wallet, or execution
access.  It validates frozen experiment topology and computes small diagnostics
over already-acquired rows.  A missing Day 2 event panel must remain missing;
these helpers never turn unavailable data into a model result.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence


REQUIRED_FEATURE_SETS = ("A", "B", "C", "D")
REQUIRED_COMPARISONS = ("B_minus_A", "C_minus_A", "D_minus_C", "D_minus_B")


def validate_signal_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the frozen topology without fitting or tuning a model."""
    errors: list[str] = []
    if tuple(contract.get("decision_times_seconds", ())) != (60, 180, 300, 600):
        errors.append("decision_times_seconds must be [60, 180, 300, 600]")
    feature_sets = contract.get("feature_sets", {})
    missing_sets = [name for name in REQUIRED_FEATURE_SETS if name not in feature_sets]
    if missing_sets:
        errors.append(f"missing feature sets: {missing_sets}")
    else:
        a = set(feature_sets["A"])
        for name in ("B", "C", "D"):
            if not a.issubset(set(feature_sets[name])):
                errors.append(f"feature set {name} does not contain A")
        if not set(feature_sets["B"]).issubset(set(feature_sets["D"])):
            errors.append("D must contain B")
        if not set(feature_sets["C"]).issubset(set(feature_sets["D"])):
            errors.append("D must contain C")
    comparisons = set(contract.get("comparisons", {}))
    for name in REQUIRED_COMPARISONS:
        if name not in comparisons:
            errors.append(f"missing comparison: {name}")
    split = contract.get("temporal_split", {})
    if split.get("primary_validation") != "day_2":
        errors.append("primary validation must be chronological day_2")
    if split.get("random_k_fold", True):
        errors.append("random K-fold must not be primary validation")
    return {"valid": not errors, "errors": errors}


def temporal_role_audit(
    rows: Iterable[Mapping[str, Any]],
    *,
    development_day: str,
    validation_day: str,
) -> dict[str, Any]:
    """Audit that rows are assigned by calendar day, never by random mixing."""
    counts: Counter[str] = Counter()
    unexpected: list[str] = []
    for row in rows:
        day = str(row.get("day") or row.get("launch_day") or "")
        if day == development_day:
            counts["day_1_development"] += 1
        elif day == validation_day:
            counts["day_2_validation"] += 1
        else:
            counts["unexpected"] += 1
            if day not in unexpected:
                unexpected.append(day)
    return {
        "counts": dict(counts),
        "development_day": development_day,
        "validation_day": validation_day,
        "unexpected_days": unexpected,
        "random_mixing": False,
        "valid": not unexpected,
    }


def point_in_time_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    decision_time: Any,
    available_key: str = "available_at",
) -> dict[str, Any]:
    """Keep only rows valid at a decision time; missing values stay unknown."""
    from research.memecoin.research_primitives import _time

    decision = _time(decision_time)
    if decision is None:
        raise ValueError("decision_time must be parseable")
    counts = Counter()
    valid_rows: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        available = _time(row.get(available_key))
        if available is None:
            counts["UNKNOWN"] += 1
        elif available > decision:
            counts["LEAKED_FEATURE"] += 1
        else:
            counts["VALID"] += 1
            valid_rows.append(row)
    return {"rows": valid_rows, "counts": dict(counts), "valid": counts["VALID"]}


def average_precision(y_true: Sequence[int], scores: Sequence[float]) -> float | None:
    """Compute average precision without a third-party ML dependency."""
    if len(y_true) != len(scores) or not y_true:
        raise ValueError("y_true and scores must be equally sized and non-empty")
    positives = sum(int(value) for value in y_true)
    if positives == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), i))
    found = 0
    total = 0.0
    for rank, index in enumerate(order, 1):
        if int(y_true[index]):
            found += 1
            total += found / rank
    return total / positives


def binary_metrics(y_true: Sequence[int], scores: Sequence[float]) -> dict[str, float | None]:
    """Return rare-event metrics; accuracy is intentionally omitted."""
    if len(y_true) != len(scores) or not y_true:
        raise ValueError("y_true and scores must be equally sized and non-empty")
    base_rate = sum(int(value) for value in y_true) / len(y_true)
    clipped = [min(max(float(score), 1e-12), 1 - 1e-12) for score in scores]
    brier = sum((score - int(actual)) ** 2 for actual, score in zip(y_true, clipped)) / len(y_true)
    log_loss = -sum(
        int(actual) * math.log(score) + (1 - int(actual)) * math.log(1 - score)
        for actual, score in zip(y_true, clipped)
    ) / len(y_true)
    return {
        "n": len(y_true),
        "base_rate": base_rate,
        "pr_auc": average_precision(y_true, scores),
        "brier": brier,
        "log_loss": log_loss,
        "precision_lift": (average_precision(y_true, scores) / base_rate) if base_rate else None,
    }


def deterministic_identity_permutation(values: Sequence[str], seed: int = 20260901) -> list[str]:
    """Return a reproducible placebo permutation of participant identities."""
    result = list(values)
    random.Random(seed).shuffle(result)
    return result


def remove_top_wallet(rows: Iterable[Mapping[str, Any]], wallet: str) -> list[dict[str, Any]]:
    """Leave-one-wallet-out diagnostic; no wallet is called skilled."""
    return [dict(row) for row in rows if str(row.get("wallet")) != str(wallet)]


def right_censor_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize resolved, right-censored, and otherwise unknown outcomes."""
    counts = Counter(str(row.get("outcome_status") or row.get("status") or "UNKNOWN") for row in rows)
    resolved = counts.get("RESOLVED", 0)
    censored = counts.get("RIGHT_CENSORED", 0)
    return {"counts": dict(counts), "resolved": resolved, "right_censored": censored, "unknown": counts.get("UNKNOWN", 0)}


def bootstrap_delta(
    deltas: Sequence[float], *, seed: int = 20260901, iterations: int = 2000
) -> dict[str, Any]:
    """Paired bootstrap interval for a precomputed metric difference."""
    if not deltas:
        return {"n": 0, "estimate": None, "ci95": None}
    rng = random.Random(seed)
    values = [float(value) for value in deltas]
    samples = [sum(rng.choice(values) for _ in values) / len(values) for _ in range(iterations)]
    samples.sort()
    lower = samples[max(0, int(0.025 * iterations) - 1)]
    upper = samples[min(iterations - 1, int(0.975 * iterations))]
    return {"n": len(values), "estimate": sum(values) / len(values), "ci95": [lower, upper], "iterations": iterations}
