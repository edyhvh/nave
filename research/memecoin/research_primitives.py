"""Provider-agnostic, offline primitives for NAVE research audits.

The functions in this module deliberately operate on already-acquired rows.
They do not call Dune, RPCs, market APIs, wallets, or execution services.
"""

from __future__ import annotations

import itertools
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

UTC = timezone.utc


def _time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if value is None:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def derive_available_at(
    feature_event_time: datetime,
    *,
    source_latency_ms: int | float = 0,
    derived_at: datetime | None = None,
) -> datetime:
    """Return a conservative availability timestamp for a feature.

    ``derived_at`` is optional metadata about local computation; it never
    moves availability earlier than the on-chain event plus source latency.
    """
    event_time = _time(feature_event_time)
    if event_time is None:
        raise ValueError("feature_event_time must be timezone-aware or parseable")
    available = event_time + timedelta(milliseconds=float(source_latency_ms))
    derived = _time(derived_at)
    return max(available, derived) if derived else available


def validate_feature_derivability(
    rows: Iterable[Mapping[str, Any]],
    *,
    decision_key: str = "decision_time",
    available_key: str = "available_at",
) -> dict[str, Any]:
    """Audit ``available_at <= decision_time`` without silently imputing time.

    Missing timestamps are ``UNKNOWN`` rather than valid.  The returned row
    records are compact and suitable for a research manifest.
    """
    audited: list[dict[str, Any]] = []
    counts = {"VALID": 0, "LEAKED_FEATURE": 0, "UNKNOWN": 0}
    for index, raw in enumerate(rows):
        available = _time(raw.get(available_key))
        decision = _time(raw.get(decision_key))
        if available is None or decision is None:
            status = "UNKNOWN"
            reason = "missing_availability_or_decision_time"
        elif available > decision:
            status = "LEAKED_FEATURE"
            reason = "available_after_decision"
        else:
            status = "VALID"
            reason = None
        counts[status] += 1
        record = {
            "row_index": index,
            "feature": raw.get("feature"),
            "feature_event_time": raw.get("feature_event_time"),
            "available_at": available,
            "decision_time": decision,
            "status": status,
            "reason": reason,
        }
        audited.append(record)
    return {
        "rows": audited,
        "counts": counts,
        "valid": counts["VALID"],
        "leaked": counts["LEAKED_FEATURE"],
        "unknown": counts["UNKNOWN"],
    }


def _event_order(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _time(row.get("event_ts") or row.get("event_time"))
        or datetime.max.replace(tzinfo=UTC),
        row.get("slot") if row.get("slot") is not None else 2**63,
        row.get("tx_index") if row.get("tx_index") is not None else 2**31,
        row.get("outer_instruction_index") if row.get("outer_instruction_index") is not None else 2**31,
        row.get("inner_instruction_index") if row.get("inner_instruction_index") is not None else 2**31,
        str(row.get("transaction") or row.get("tx_id") or ""),
    )


def _flow_metrics(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    buys = [e for e in events if str(e.get("side", "")).lower() == "buy"]
    sells = [e for e in events if str(e.get("side", "")).lower() == "sell"]
    buy_volume = sum(_number(e.get("quote_amount_sol")) or 0.0 for e in buys)
    sell_volume = sum(_number(e.get("quote_amount_sol")) or 0.0 for e in sells)
    return {
        "trade_count": len(events),
        "buyer_count": len({e.get("wallet") for e in buys if e.get("wallet")}),
        "seller_count": len({e.get("wallet") for e in sells if e.get("wallet")}),
        "buy_volume_sol": buy_volume,
        "sell_volume_sol": sell_volume,
        "net_inflow_sol": buy_volume - sell_volume,
    }


def participant_excluded_outcomes(
    events: Iterable[Mapping[str, Any]],
    triggering_wallets: Mapping[str, Iterable[str]] | Iterable[str],
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    """Return raw and participant-excluded flow for a bounded outcome window.

    ``triggering_wallets`` may be global or keyed by mint.  A wallet is never
    treated as an economic actor merely because it appears in this mapping.
    """
    global_wallets: set[str] = set()
    by_mint: dict[str, set[str]] = {}
    if isinstance(triggering_wallets, Mapping):
        by_mint = {str(k): {str(w) for w in v} for k, v in triggering_wallets.items()}
    else:
        global_wallets = {str(w) for w in triggering_wallets}
    start = _time(start_time)
    end = _time(end_time)
    selected: list[dict[str, Any]] = []
    for raw in events:
        row = dict(raw)
        ts = _time(row.get("event_ts") or row.get("event_time"))
        if ts is None or (start and ts < start) or (end and ts >= end):
            continue
        selected.append(row)
    excluded: list[dict[str, Any]] = []
    exogenous: list[dict[str, Any]] = []
    for row in selected:
        mint = str(row.get("mint", ""))
        wallets = by_mint.get(mint, global_wallets)
        if str(row.get("wallet")) in wallets:
            excluded.append(row)
        else:
            exogenous.append(row)
    return {
        "raw": _flow_metrics(selected),
        "exogenous": _flow_metrics(exogenous),
        "participant_self_flow": _flow_metrics(excluded),
        "excluded_wallet_count": len(global_wallets | {w for values in by_mint.values() for w in values}),
        "event_count": len(selected),
    }


def post_rejection_followup_audit(
    candidates: Iterable[Mapping[str, Any]],
    outcomes: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Join gate decisions to future observations for PRFS-style auditing."""
    outcome_rows = [dict(row) for row in outcomes]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in outcome_rows:
        key = row.get("candidate_id") or row.get("mint")
        if key is not None:
            grouped[str(key)].append(row)
    result: list[dict[str, Any]] = []
    for raw in candidates:
        candidate = dict(raw)
        key = candidate.get("candidate_id") or candidate.get("mint")
        decision = _time(candidate.get("decision_time"))
        future = []
        for row in grouped.get(str(key), []):
            observed = _time(row.get("observed_at") or row.get("event_time"))
            if decision is None or observed is None or observed >= decision:
                future.append((observed or datetime.max.replace(tzinfo=UTC), row))
        future.sort(key=lambda item: item[0])
        first = future[0][1] if future else {}
        result.append({
            "candidate_id": key,
            "mint": candidate.get("mint"),
            "gate": candidate.get("gate"),
            "decision_time": decision,
            "decision": "PASS" if candidate.get("accepted") is True else "REJECT",
            "rejection_reason": candidate.get("rejection_reason"),
            "candidate_state_before_gate": candidate.get("state_before_gate"),
            "future_observation_count": len(future),
            "first_future_observed_at": _time(first.get("observed_at") or first.get("event_time")),
            "future_return_pct": _number(first.get("return_pct")),
            "future_status": first.get("status") if first else ("NO_FOLLOWUP" if key is not None else "UNKNOWN"),
        })
    return result


def beta_binomial_reputation(
    episodes: Iterable[Mapping[str, Any]],
    *,
    as_of: datetime | None = None,
    alpha_prior: float = 1.0,
    beta_prior: float = 1.0,
) -> list[dict[str, Any]]:
    """Calculate uncertainty-aware participant success estimates.

    Only rows with an explicit ``success`` field or a recognized outcome label
    are counted.  This prevents unresolved PnL from becoming a failure.
    """
    if alpha_prior <= 0 or beta_prior <= 0:
        raise ValueError("Beta prior parameters must be positive")
    success_labels = {"FAST_BURST", "SUSTAINED_RUNNER", "RUNNER", "SUCCESS"}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in episodes:
        row = dict(raw)
        wallet = row.get("wallet") or row.get("participant")
        if not wallet or row.get("eligible", True) is False:
            continue
        event_time = _time(row.get("outcome_ts") or row.get("event_ts"))
        if as_of and event_time and event_time >= _time(as_of):
            continue
        if "success" not in row and not row.get("outcome"):
            continue
        grouped[str(wallet)].append(row)
    result = []
    for wallet, rows in sorted(grouped.items()):
        successes = sum(
            bool(row.get("success")) if "success" in row else str(row.get("outcome")).upper() in success_labels
            for row in rows
        )
        failures = len(rows) - successes
        alpha = alpha_prior + successes
        beta = beta_prior + failures
        mean = alpha / (alpha + beta)
        lower, upper = _beta_interval(alpha, beta)
        by_mint = defaultdict(int)
        for row in rows:
            if (bool(row.get("success")) if "success" in row else str(row.get("outcome")).upper() in success_labels):
                by_mint[str(row.get("mint", ""))] += 1
        max_winner_share = max(by_mint.values(), default=0) / successes if successes else 0.0
        result.append({
            "wallet": wallet,
            "prior_eligible_events": len(rows),
            "successes": successes,
            "failures": failures,
            "posterior_success_estimate": mean,
            "posterior_lower_95": lower,
            "posterior_upper_95": upper,
            "top_winner_dependence": max_winner_share,
        })
    return result


def _beta_interval(alpha: float, beta: float) -> tuple[float, float]:
    try:
        from scipy.stats import beta as beta_distribution

        return (
            float(beta_distribution.ppf(0.025, alpha, beta)),
            float(beta_distribution.ppf(0.975, alpha, beta)),
        )
    except Exception:  # pragma: no cover - fallback for minimal environments
        mean = alpha / (alpha + beta)
        variance = alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1))
        width = 1.96 * math.sqrt(variance)
        return max(0.0, mean - width), min(1.0, mean + width)


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, value: str) -> None:
        self.parent.setdefault(value, value)

    def find(self, value: str) -> str:
        parent = self.parent.setdefault(value, value)
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def build_cooccurrence_cohorts(
    events: Iterable[Mapping[str, Any]],
    *,
    first_buyer_limit: int = 10,
    min_shared_launches: int = 3,
) -> dict[str, Any]:
    """Build repeated wallet co-occurrence components without actor claims."""
    if first_buyer_limit < 2 or min_shared_launches < 1:
        raise ValueError("buyer limit must be >=2 and minimum shared launches >=1")
    per_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in events:
        row = dict(raw)
        if str(row.get("side", "")).lower() != "buy" or not row.get("wallet") or not row.get("mint"):
            continue
        per_mint[str(row["mint"])].append(row)
    pair_mints: dict[tuple[str, str], set[str]] = defaultdict(set)
    for mint, rows in per_mint.items():
        rows.sort(key=_event_order)
        first_by_wallet: dict[str, dict[str, Any]] = {}
        for row in rows:
            wallet = str(row["wallet"])
            first_by_wallet.setdefault(wallet, row)
        selected = sorted(
            first_by_wallet.values(),
            key=lambda row: (
                row.get("buyer_rank") if row.get("buyer_rank") is not None else 2**31,
                _event_order(row),
                str(row["wallet"]),
            ),
        )[:first_buyer_limit]
        for left, right in itertools.combinations(sorted(str(row["wallet"]) for row in selected), 2):
            pair_mints[(left, right)].add(mint)
    uf = _UnionFind()
    edges = []
    for (left, right), mints in sorted(pair_mints.items()):
        if len(mints) < min_shared_launches:
            continue
        uf.union(left, right)
        edges.append({"wallet_a": left, "wallet_b": right, "shared_launches": len(mints), "mints": sorted(mints)})
    components: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        components[uf.find(edge["wallet_a"])].update((edge["wallet_a"], edge["wallet_b"]))
    cohorts = []
    for index, wallets in enumerate(sorted(components.values(), key=lambda values: (-len(values), sorted(values)))):
        touched = sorted({mint for edge in edges if edge["wallet_a"] in wallets and edge["wallet_b"] in wallets for mint in edge["mints"]})
        cohorts.append({
            "cohort_id": f"LOCAL-COH-{index + 1:04d}",
            "wallets": sorted(wallets),
            "cohort_size": len(wallets),
            "n_launches": len(touched),
            "mints": touched,
            "classification": "REPEATED_COHORT",
            "economic_cluster_proven": False,
            "economic_cluster_status": "UNKNOWN_WITHOUT_FUNDING_OR_BUNDLE_EVIDENCE",
        })
    return {
        "cohorts": cohorts,
        "edges": edges,
        "parameters": {"first_buyer_limit": first_buyer_limit, "min_shared_launches": min_shared_launches},
    }


def activity_match_controls(
    treated: Iterable[Mapping[str, Any]],
    controls: Iterable[Mapping[str, Any]],
    *,
    numeric_keys: Sequence[str] = ("eligible_launches_observed", "launches_entered", "launch_hour_exposure"),
    categorical_keys: Sequence[str] = ("market_regime",),
) -> list[dict[str, Any]]:
    """Greedily pair treated rows to distinct, nearest activity controls."""
    treated_rows = [dict(row) for row in treated]
    control_rows = [dict(row) for row in controls]
    scales: dict[str, float] = {}
    for key in numeric_keys:
        values = [_number(row.get(key)) for row in treated_rows + control_rows]
        finite = sorted(value for value in values if value is not None)
        scales[key] = max(median(finite) if finite else 1.0, 1.0)
    available = list(range(len(control_rows)))
    pairs = []
    for treated_row in sorted(treated_rows, key=lambda row: str(row.get("id") or row.get("wallet") or row.get("mint"))):
        candidates = []
        for index in available:
            control = control_rows[index]
            if any(treated_row.get(key) != control.get(key) for key in categorical_keys):
                continue
            diffs = []
            for key in numeric_keys:
                left, right = _number(treated_row.get(key)), _number(control.get(key))
                if left is None or right is None:
                    diffs.append(1.0)
                else:
                    diffs.append(abs(left - right) / scales[key])
            candidates.append((sum(diffs), str(control.get("id") or control.get("wallet") or control.get("mint")), index))
        if not candidates:
            continue
        distance, control_id, index = min(candidates)
        available.remove(index)
        treated_id = str(treated_row.get("id") or treated_row.get("wallet") or treated_row.get("mint"))
        pairs.append({"treated_id": treated_id, "control_id": control_id, "distance": distance})
    return pairs

