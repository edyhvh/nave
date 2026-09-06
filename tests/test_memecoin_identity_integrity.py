from datetime import UTC, datetime, timedelta

import pytest

from research.core.contracts import ResearchStatus
from research.core.store import ResearchStore
from research.memecoin_workflow import MemecoinResearchWorkflow, discover_rows


NOW = datetime(2026, 9, 4, tzinfo=UTC)


def snapshot(address="0x" + "1" * 40, **overrides):
    return {
        "asset": "SAME",
        "chain_id": "eip155:1",
        "contract_address": address,
        "decision_time": NOW.isoformat(),
        "available_at": NOW.isoformat(),
        "features": {"volume_acceleration": 3, "liquidity_usd": 50_000,
                     "risk_status": "PASS", "holder_structure": "observed",
                     "wallet_activity": "observed"},
        **overrides,
    }


def test_same_symbol_contracts_and_decisions_never_share_outcomes(tmp_path):
    workflow = MemecoinResearchWorkflow(store=ResearchStore(tmp_path))
    good = snapshot()
    rejected = snapshot("0x" + "2" * 40)
    rejected["features"]["risk_status"] = "FAIL"
    scan = workflow.discover([good, rejected])
    outcomes = [{**item, "observed_at": (NOW + timedelta(hours=1)).isoformat(),
                 "later_move_pct": 0.5} for item in (good, rejected)]
    evaluation = workflow.evaluate(scan_result=scan, outcomes=outcomes)
    assert len(evaluation.payload["evaluated"]) == 1
    missed = workflow.missed_moves(scan_result=scan, outcomes=outcomes)
    assert len(missed.payload["missed_moves"]) == 1
    assert missed.payload["missed_moves"][0]["contract_address"] == rejected["contract_address"]
    assert scan.payload["case_study"] is None
    wrong_time = {**outcomes[0], "decision_time": (NOW - timedelta(days=1)).isoformat()}
    assert not workflow.evaluate(scan_result=scan, outcomes=[wrong_time]).payload["evaluated"]


@pytest.mark.parametrize("change", [
    {"chain_id": None}, {"contract_address": "unknown"},
    {"decision_time": "garbage"}, {"decision_time": "2026-09-04T00:00:00"},
    {"feature_available_at": {"wallet_activity": (NOW + timedelta(seconds=1)).isoformat()}},
    {"feature_available_at": {"liquidity_usd": None}},
    {"features": {"volume_acceleration": float("nan"), "liquidity_usd": float("inf"),
                  "risk_status": "PASS", "holder_structure": "observed", "wallet_activity": "observed"}},
])
def test_unknown_identity_or_evidence_is_not_a_valid_empty_scan(tmp_path, change):
    if "decision_time" in change:
        with pytest.raises(ValueError, match="snapshot decision_time"):
            MemecoinResearchWorkflow(store=ResearchStore(tmp_path)).discover([snapshot(**change)])
        return
    result = MemecoinResearchWorkflow(store=ResearchStore(tmp_path)).discover([snapshot(**change)])
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert not result.payload["selected"]


def test_duplicate_snapshot_cannot_double_the_sample_or_hide_conflicting_inputs():
    good = snapshot()
    duplicate = snapshot()
    duplicate["features"]["risk_status"] = "FAIL"
    result = discover_rows([good, duplicate])
    assert not result["selected"]
    assert all("duplicate_snapshot_identity" in r["rejection_filters"] for r in result["rejected"])
