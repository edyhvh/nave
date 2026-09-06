"""Point-in-time memecoin discovery, evaluation, and missed-move audits."""

from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from research.core.contracts import EvidenceKind, EvidenceReference, PointInTime, ResearchResult, ResearchStatus, RunMetadata
from research.core.store import ResearchStore
from research.memecoin.research_primitives import validate_feature_derivability


STRATEGY_NAME = "memecoin-point-in-time-discovery"
STRATEGY_VERSION = "1.1.0"
FEATURES = ("volume_acceleration", "liquidity_usd", "risk_status", "holder_structure_presence", "wallet_activity_presence")


def _strict_time(value: Any) -> datetime | None:
    """Parse a supplied timestamp without turning malformed data into now."""
    if value in (None, ""):
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def _asset(row: Mapping[str, Any]) -> str:
    return str(row.get("asset") or row.get("symbol") or row.get("mint") or "").strip()


def canonical_identity(row: Mapping[str, Any]) -> str | None:
    """Resolve explicit chain/address identity; labels never join research rows."""
    chain = str(row.get("chain_id") or "").strip()
    address = str(row.get("contract_address") or row.get("mint") or "").strip()
    if re.fullmatch(r"eip155:[1-9][0-9]*", chain):
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address) or int(address, 16) == 0:
            return None
        address = address.lower()
    elif chain == "solana:mainnet":
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        if not 32 <= len(address) <= 44 or any(char not in alphabet for char in address):
            return None
        number = 0
        for char in address:
            number = number * 58 + alphabet.index(char)
        leading = len(address) - len(address.lstrip("1"))
        if leading + (number.bit_length() + 7) // 8 != 32:
            return None
    else:
        return None
    return f"{chain}:{address}"


def _snapshot_key(row: Mapping[str, Any]) -> tuple[str, datetime] | None:
    identity, decision = canonical_identity(row), _strict_time(row.get("decision_time"))
    return (identity, decision) if identity and decision else None


def _eligible(row: Mapping[str, Any], *, min_volume_acceleration: float, min_liquidity_usd: float) -> tuple[bool, list[str]]:
    decision_time = _strict_time(row.get("decision_time"))
    if decision_time is None:
        return False, ["invalid_decision_time"]
    available_at = row.get("available_at")
    if not available_at:
        return False, ["unknown_feature_availability"]
    available = _strict_time(available_at)
    if available is None:
        return False, ["invalid_feature_availability"]
    if available > decision_time:
        return False, ["hindsight_feature_not_available_at_decision"]
    blockers: list[str] = []
    features = row.get("features") if isinstance(row.get("features"), Mapping) else row
    clocks = row.get("feature_available_at")
    if clocks is not None:
        if not isinstance(clocks, Mapping):
            blockers.append("invalid_feature_availability")
        else:
            for feature, clock in clocks.items():
                stamp = _strict_time(clock)
                if stamp is None or stamp > decision_time:
                    blockers.append(f"unknown_or_late_feature:{feature}")
    try:
        volume = float(features.get("volume_acceleration"))
        if not math.isfinite(volume):
            blockers.append("volume_acceleration_missing")
        elif volume < min_volume_acceleration:
            blockers.append("volume_acceleration")
    except (TypeError, ValueError):
        blockers.append("volume_acceleration_missing")
    try:
        liquidity = float(features.get("liquidity_usd"))
        if not math.isfinite(liquidity):
            blockers.append("liquidity_missing")
        elif liquidity < min_liquidity_usd:
            blockers.append("liquidity")
    except (TypeError, ValueError):
        blockers.append("liquidity_missing")
    risk = str(features.get("risk_status") or "UNKNOWN").upper()
    if risk != "PASS":
        blockers.append("safety_or_contract_risk" if risk in {"FAIL", "REJECT"} else "safety_evidence_missing")
    if features.get("holder_structure") in (None, "UNKNOWN"):
        blockers.append("holder_structure")
    if features.get("wallet_activity") in (None, "UNKNOWN"):
        blockers.append("wallet_activity")
    return not blockers, blockers


def discover_rows(
    rows: list[Mapping[str, Any]],
    *,
    min_volume_acceleration: float = 2.0,
    min_liquidity_usd: float = 25_000.0,
) -> dict[str, Any]:
    """Apply a small evidence-backed feature set without using future values."""
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("snapshot rows must be a list of objects")
    if any(not math.isfinite(value) or value <= 0 for value in (min_volume_acceleration, min_liquidity_usd)):
        raise ValueError("discovery thresholds must be finite and positive")
    derivability = validate_feature_derivability(rows)
    keys = Counter(_snapshot_key(row) for row in rows)
    for raw in rows:
        row = dict(raw)
        name = _asset(row)
        passed, blockers = _eligible(
            row,
            min_volume_acceleration=min_volume_acceleration,
            min_liquidity_usd=min_liquidity_usd,
        )
        if canonical_identity(row) is None:
            blockers.append("missing_or_invalid_canonical_identity")
        key = _snapshot_key(row)
        if key is not None and keys[key] > 1:
            blockers.append("duplicate_snapshot_identity")
        passed = passed and not blockers
        snapshot = {
            "asset": name,
            "chain_id": row.get("chain_id"),
            "contract_address": row.get("contract_address"),
            "canonical_identity": canonical_identity(row),
            "mint": row.get("mint"),
            "decision_time": row.get("decision_time"),
            "available_at": row.get("available_at"),
            "features": dict(row.get("features") or {}),
            "feature_available_at": row.get("feature_available_at"),
            "source_references": row.get("source_references", []),
            "feature_set": list(FEATURES),
            "point_in_time": passed,
        }
        if passed:
            selected.append({
                **snapshot,
                "thesis": "volume acceleration and liquidity thresholds; risk PASS; holder/wallet presence only",
                "research_only": True,
                "edge_validated": False,
                "major_risks": ["contract risk and manipulation", "liquidity can disappear", "social/narrative signals are noisy"],
            })
        else:
            rejected.append({**snapshot, "rejection_filters": blockers})
    return {
        "universe_count": len(rows),
        "eligible_count": len(selected),
        "selected": selected,
        "rejected": rejected,
        "feature_set": list(FEATURES),
        "derivability": derivability,
        "decision_time_rule": "available_at <= decision_time; missing/late data is not eligible",
    }


def missed_moves(scan_payload: Mapping[str, Any], outcomes: list[Mapping[str, Any]], *, move_threshold: float) -> list[dict[str, Any]]:
    if not math.isfinite(move_threshold) or move_threshold <= 0:
        raise ValueError("move_threshold must be finite and positive")
    selected = {_snapshot_key(row) for row in scan_payload.get("selected") or []}
    rejected = {_snapshot_key(row): row for row in scan_payload.get("rejected") or [] if _snapshot_key(row)}
    seen: set[tuple[str, datetime]] = set()
    output: list[dict[str, Any]] = []
    for outcome in outcomes:
        asset = _asset(outcome)
        try:
            move = float(outcome.get("later_move_pct", outcome.get("forward_return")))
        except (TypeError, ValueError):
            continue
        key = _snapshot_key(outcome)
        observed = _strict_time(outcome.get("observed_at"))
        if key is None or observed is None or observed <= key[1]:
            continue
        if not math.isfinite(move) or move < move_threshold or key in selected or key in seen:
            continue
        seen.add(key)
        row = rejected.get(key)
        decision_time = key[1]
        info_time_raw = outcome.get("information_available_at")
        info_time = _strict_time(info_time_raw) if info_time_raw else None
        information_state = "UNKNOWN" if info_time is None else (
            "BEFORE_MOVE" if info_time <= decision_time else "AFTER_DECISION"
        )
        output.append({
            "asset": asset,
            "chain_id": outcome.get("chain_id"),
            "contract_address": outcome.get("contract_address"),
            "mint": outcome.get("mint"),
            "canonical_identity": key[0],
            "decision_time": decision_time.isoformat(),
            "observed_at": observed.isoformat(),
            "decision_time_snapshot": row,
            "later_move_pct": move,
            "available_information": outcome.get("available_information", row.get("features") if row else None),
            "information_existed_before_move": information_state,
            "universe_membership": outcome.get("universe_membership", row is not None),
            "failed_filter": (row or {}).get("rejection_filters") or ["not_in_observed_universe"],
            "possible_missing_feature": outcome.get("possible_missing_feature") or "inspect the recorded rejected snapshot",
        })
    return output


def _json_snapshot(value: Any) -> Any:
    """Keep unavailable numeric values null and serialize known timestamps."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {key: _json_snapshot(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_snapshot(item) for item in value]
    return value


class MemecoinResearchWorkflow:
    def __init__(self, *, store: ResearchStore | None = None):
        self.store = store or ResearchStore()

    def _result(self, workflow: str, status: ResearchStatus, payload: Mapping[str, Any], *, warnings: list[str] | None = None, now: datetime | None = None) -> ResearchResult:
        now = now or datetime.now(UTC)
        return ResearchResult(
            workflow=workflow,
            status=status,
            metadata=RunMetadata(
                strategy_name=STRATEGY_NAME,
                strategy_version=STRATEGY_VERSION,
                run_id=str(uuid.uuid4()),
                decision_time=now,
                started_at=now,
                completed_at=now,
                input_available_at=now,
            ),
            payload=_json_snapshot(payload),
            evidence=(EvidenceReference(
                reference_id=f"memecoin-{workflow}",
                source="nave.memecoin.research",
                claim="Memecoin research was calculated from decision-time snapshots",
                kind=EvidenceKind.INFERENCE,
                point_in_time=PointInTime(event_time=now, available_at=now, decision_time=now),
            ),),
            warnings=tuple(warnings or []),
        )

    def discover(self, rows: list[Mapping[str, Any]], *, dune_cache: Path | None = None) -> ResearchResult:
        dune_usage = {
            "mode": "materialized_cache" if dune_cache else "local_input",
            "query_executed": False,
            "estimated_credits": None,
            "actual_credits": None,
            "source": str(dune_cache) if dune_cache else "caller-provided rows",
        }
        payload_rows = rows
        if dune_cache:
            raw = json.loads(dune_cache.read_text(encoding="utf-8"))
            if not isinstance(raw, Mapping) or raw.get("provider") != "dune":
                raise ValueError("Dune cache is stale or untrusted: materialized envelope required")
            if raw.get("provider") == "dune":
                fetched = _strict_time(raw.get("fetched_at"))
                ttl = float(raw.get("max_age_seconds") or 0)
                age = (datetime.now(UTC) - fetched).total_seconds() if fetched else -1
                if not math.isfinite(ttl) or ttl <= 0 or not 0 <= age <= min(ttl, 86400) or raw.get("row_count") != len(raw.get("rows") or []) or not raw.get("query_id") or not raw.get("query_sha256") or raw.get("query_identity") != f"{raw.get('query_id')}:{raw.get('query_sha256')}:limit={raw.get('requested_limit')}" or not isinstance(raw.get("requested_limit"), int):
                    raise ValueError("Dune cache is stale or incomplete; explicit refresh required")
            payload_rows = raw.get("rows", raw) if isinstance(raw, Mapping) else raw
            if isinstance(raw, Mapping):
                usage = raw.get("credit_usage") if isinstance(raw.get("credit_usage"), Mapping) else {}
                dune_usage.update(
                    {
                        "query_identity": raw.get("query_identity"),
                        "query_id": raw.get("query_id"),
                        "estimated_credits": usage.get("estimated"),
                        "actual_credits": usage.get("actual"),
                        "mode": "materialized_cache" if raw.get("provider") == "dune" else "cached",
                    }
                )
        clocks = {_strict_time(row.get("decision_time")) for row in payload_rows}
        known_clocks = clocks - {None}
        if not known_clocks:
            raise ValueError("discovery requires a known snapshot decision_time")
        decision_time = max(known_clocks)
        result_payload = discover_rows(payload_rows)
        result_payload["dune_usage"] = dune_usage
        cases = [{"asset": _asset(row), "canonical_identity": canonical_identity(row),
                  "source": row["case_study_source"], "used_as": "explicit caller case study only",
                  "overfit_guard": "no asset-specific rule added"}
                 for row in payload_rows if row.get("case_study_source") and canonical_identity(row)]
        result_payload["case_studies"] = cases
        result_payload["case_study"] = cases[0] if len(cases) == 1 else None
        status = ResearchStatus.SETUP_FOUND if result_payload["selected"] else ResearchStatus.NO_SETUP
        evidence_gaps = any(any(reason not in {"volume_acceleration", "liquidity", "safety_or_contract_risk"}
                                for reason in row["rejection_filters"])
                            for row in result_payload["rejected"])
        result_payload["partial_universe"] = evidence_gaps
        if (evidence_gaps or not payload_rows) and not result_payload["selected"]:
            status = ResearchStatus.INSUFFICIENT_EVIDENCE
        result = self._result(
            "memecoin.discover",
            status,
            result_payload,
            now=decision_time,
            warnings=["discovery is research-only; no automatic portfolio action"] if result_payload["selected"] else [],
        )
        self.store.save_result(result)
        return result

    def evaluate(self, *, scan_result: ResearchResult, outcomes: list[Mapping[str, Any]]) -> ResearchResult:
        selected = {_snapshot_key(row) for row in scan_result.payload.get("selected") or [] if _snapshot_key(row)}
        evaluated = []
        seen = set()
        excluded = []
        for outcome in outcomes:
            key = _snapshot_key(outcome)
            observed = _strict_time(outcome.get("observed_at"))
            if key is None or key not in selected or observed is None or observed <= key[1] or key in seen:
                excluded.append({"canonical_identity": canonical_identity(outcome), "reason": "unmatched_duplicate_or_unproven_outcome_time"})
                continue
            try:
                value = float(outcome.get("later_move_pct", outcome.get("forward_return")))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                excluded.append({"canonical_identity": key[0], "reason": "nonfinite_outcome"})
                continue
            seen.add(key)
            evaluated.append({**dict(outcome), "canonical_identity": key[0], "forward_move": value, "hit": value > 0})
        hits = sum(bool(row["hit"]) for row in evaluated)
        payload = {
            "strategy": STRATEGY_NAME,
            "strategy_version": scan_result.metadata.strategy_version,
            "evaluated": evaluated,
            "excluded_outcomes": excluded,
            "cost_basis": "GROSS_UNCOSTED",
            "metrics": {
                "selected_count": len(selected),
                "evaluated_count": len(evaluated),
                "hit_rate": hits / len(evaluated) if evaluated else None,
                "mean_forward_move": sum(row["forward_move"] for row in evaluated) / len(evaluated) if evaluated else None,
                "cohort_comparison_required": True,
            },
            "source_scan_run_id": scan_result.metadata.run_id,
        }
        result = self._result(
            "memecoin.evaluate",
            ResearchStatus.STRATEGY_NOT_VALIDATED,
            payload,
            warnings=["evaluation is not validation; compare against cohorts and preserve out-of-sample data"],
        )
        self.store.save_result(result)
        return result

    def missed_moves(self, *, scan_result: ResearchResult, outcomes: list[Mapping[str, Any]], move_threshold: float = 0.50) -> ResearchResult:
        rows = missed_moves(scan_result.payload, outcomes, move_threshold=move_threshold)
        result = self._result(
            "memecoin.missed_moves",
            ResearchStatus.NO_SETUP,
            {"strategy": STRATEGY_NAME, "strategy_version": scan_result.metadata.strategy_version, "move_threshold": move_threshold, "missed_moves": rows, "source_scan_run_id": scan_result.metadata.run_id},
            warnings=["future outcomes are audit-only and are not used to alter the decision-time snapshot"],
        )
        self.store.save_result(result)
        return result

    def status(self) -> dict[str, Any]:
        output = {}
        for workflow in ("memecoin.discover", "memecoin.evaluate", "memecoin.missed_moves"):
            result = self.store.load_result(workflow)
            if result:
                output[workflow] = {"status": result.status.value, "run_id": result.metadata.run_id}
        return output
