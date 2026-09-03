from datetime import datetime, timedelta, timezone

from research.memecoin.research_primitives import (
    activity_match_controls,
    beta_binomial_reputation,
    build_cooccurrence_cohorts,
    derive_available_at,
    participant_excluded_outcomes,
    post_rejection_followup_audit,
    validate_feature_derivability,
)

UTC = timezone.utc
T0 = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _trade(mint, wallet, seconds, side="buy", quote=1.0, rank=None):
    return {
        "mint": mint,
        "wallet": wallet,
        "event_ts": T0 + timedelta(seconds=seconds),
        "side": side,
        "quote_amount_sol": quote,
        "slot": seconds,
        "buyer_rank": rank,
    }


def test_derivability_rejects_future_available_feature_and_missing_time():
    result = validate_feature_derivability([
        {"feature": "x", "available_at": T0, "decision_time": T0 + timedelta(seconds=1)},
        {"feature": "x", "available_at": T0 + timedelta(seconds=2), "decision_time": T0 + timedelta(seconds=1)},
        {"feature": "x", "decision_time": T0},
    ])
    assert result["counts"] == {"VALID": 1, "LEAKED_FEATURE": 1, "UNKNOWN": 1}


def test_available_at_includes_source_latency_and_local_derivation():
    assert derive_available_at(T0, source_latency_ms=1000) == T0 + timedelta(seconds=1)
    assert derive_available_at(T0, source_latency_ms=1000, derived_at=T0 + timedelta(seconds=2)) == T0 + timedelta(seconds=2)


def test_participant_self_flow_exclusion_preserves_raw_and_exogenous_flow():
    rows = [_trade("m", "trigger", 1, quote=2), _trade("m", "new", 2, quote=3), _trade("m", "trigger", 3, "sell", quote=1)]
    result = participant_excluded_outcomes(rows, {"m": {"trigger"}})
    assert result["raw"]["buyer_count"] == 2
    assert result["raw"]["net_inflow_sol"] == 4
    assert result["exogenous"]["buyer_count"] == 1
    assert result["exogenous"]["net_inflow_sol"] == 3


def test_prfs_join_keeps_gate_reason_and_future_outcome():
    result = post_rejection_followup_audit(
        [{"candidate_id": "c1", "mint": "m", "gate": "liquidity", "accepted": False, "rejection_reason": "thin", "decision_time": T0}],
        [{"candidate_id": "c1", "observed_at": T0 + timedelta(minutes=5), "return_pct": 42, "status": "BURST"}],
    )[0]
    assert result["decision"] == "REJECT"
    assert result["rejection_reason"] == "thin"
    assert result["future_return_pct"] == 42


def test_beta_reputation_shrinks_small_sample_and_respects_cutoff():
    rows = [
        {"wallet": "small", "mint": "a", "outcome": "SUCCESS", "outcome_ts": T0},
        {"wallet": "small", "mint": "b", "outcome": "FAIL", "outcome_ts": T0 + timedelta(days=1)},
        *({"wallet": "large", "mint": str(i), "outcome": "SUCCESS" if i < 35 else "FAIL", "outcome_ts": T0} for i in range(100)),
    ]
    result = {row["wallet"]: row for row in beta_binomial_reputation(rows, as_of=T0 + timedelta(days=2))}
    assert result["small"]["prior_eligible_events"] == 2
    assert result["large"]["prior_eligible_events"] == 100
    assert result["small"]["posterior_lower_95"] < result["small"]["posterior_success_estimate"]
    assert result["large"]["posterior_success_estimate"] < 0.5


def test_cooccurrence_is_repeated_cohort_not_economic_actor_claim():
    rows = []
    for mint, offset in (("a", 0), ("b", 10), ("c", 20)):
        rows.extend([_trade(mint, "w1", offset, rank=1), _trade(mint, "w2", offset + 1, rank=2)])
    result = build_cooccurrence_cohorts(rows, first_buyer_limit=2, min_shared_launches=3)
    assert len(result["cohorts"]) == 1
    assert result["cohorts"][0]["classification"] == "REPEATED_COHORT"
    assert result["cohorts"][0]["economic_cluster_proven"] is False


def test_activity_matching_is_deterministic_without_control_reuse():
    treated = [{"id": "t1", "eligible_launches_observed": 10, "launches_entered": 2, "launch_hour_exposure": 3, "market_regime": "a"}, {"id": "t2", "eligible_launches_observed": 20, "launches_entered": 4, "launch_hour_exposure": 3, "market_regime": "a"}]
    controls = [{"id": "c1", "eligible_launches_observed": 11, "launches_entered": 2, "launch_hour_exposure": 3, "market_regime": "a"}, {"id": "c2", "eligible_launches_observed": 19, "launches_entered": 4, "launch_hour_exposure": 3, "market_regime": "a"}, {"id": "c3", "eligible_launches_observed": 99, "launches_entered": 9, "launch_hour_exposure": 3, "market_regime": "b"}]
    pairs = activity_match_controls(treated, controls)
    assert [(p["treated_id"], p["control_id"]) for p in pairs] == [("t1", "c1"), ("t2", "c2")]
