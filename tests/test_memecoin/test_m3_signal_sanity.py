from datetime import datetime, timedelta, timezone

from research.memecoin.m3_signal_sanity import (
    binary_metrics,
    bootstrap_delta,
    deterministic_identity_permutation,
    point_in_time_rows,
    remove_top_wallet,
    right_censor_summary,
    temporal_role_audit,
    validate_signal_contract,
)
from research.memecoin.research_primitives import (
    activity_match_controls,
    beta_binomial_reputation,
    participant_excluded_outcomes,
)


UTC = timezone.utc
T0 = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _contract():
    return {
        "decision_times_seconds": [60, 180, 300, 600],
        "feature_sets": {"A": ["a"], "B": ["a", "b"], "C": ["a", "c"], "D": ["a", "b", "c"]},
        "comparisons": {"B_minus_A": 1, "C_minus_A": 1, "D_minus_C": 1, "D_minus_B": 1},
        "temporal_split": {"primary_validation": "day_2", "random_k_fold": False},
    }


def test_contract_freezes_nested_feature_sets_and_chronological_validation():
    result = validate_signal_contract(_contract())
    assert result["valid"] is True


def test_day_separation_has_no_random_leakage():
    result = temporal_role_audit(
        [{"day": "2026-08-27"}, {"day": "2026-08-28"}],
        development_day="2026-08-27",
        validation_day="2026-08-28",
    )
    assert result["valid"] is True
    assert result["random_mixing"] is False
    assert result["counts"] == {"day_1_development": 1, "day_2_validation": 1}


def test_available_at_enforcement_rejects_future_and_unknown():
    result = point_in_time_rows(
        [
            {"available_at": T0},
            {"available_at": T0 + timedelta(seconds=1)},
            {},
        ],
        decision_time=T0,
    )
    assert result["counts"] == {"VALID": 1, "LEAKED_FEATURE": 1, "UNKNOWN": 1}
    assert result["valid"] == 1


def test_participant_excluded_flow_and_right_censoring_are_explicit():
    flow = participant_excluded_outcomes(
        [
            {"mint": "m", "wallet": "trigger", "side": "buy", "quote_amount_sol": 2, "event_ts": T0},
            {"mint": "m", "wallet": "new", "side": "buy", "quote_amount_sol": 3, "event_ts": T0},
        ],
        {"m": {"trigger"}},
    )
    assert flow["raw"]["buy_volume_sol"] == 5
    assert flow["exogenous"]["buy_volume_sol"] == 3
    assert right_censor_summary([{"outcome_status": "RIGHT_CENSORED"}])["right_censored"] == 1


def test_beta_binomial_reputation_uses_only_matured_outcomes():
    result = beta_binomial_reputation(
        [
            {"wallet": "w", "outcome": "SUCCESS", "outcome_ts": T0},
            {"wallet": "w", "outcome": "FAIL", "outcome_ts": T0 + timedelta(days=2)},
        ],
        as_of=T0 + timedelta(days=1),
    )[0]
    assert result["prior_eligible_events"] == 1


def test_activity_matching_placebo_and_top_wallet_removal_are_deterministic():
    pairs = activity_match_controls(
        [{"id": "treated", "eligible_launches_observed": 3, "launches_entered": 1, "launch_hour_exposure": 2, "market_regime": "a"}],
        [{"id": "control", "eligible_launches_observed": 3, "launches_entered": 1, "launch_hour_exposure": 2, "market_regime": "a"}],
    )
    assert pairs[0]["control_id"] == "control"
    assert deterministic_identity_permutation(["a", "b", "c"]) == deterministic_identity_permutation(["a", "b", "c"])
    assert remove_top_wallet([{"wallet": "top"}, {"wallet": "other"}], "top") == [{"wallet": "other"}]


def test_rare_event_metrics_and_bootstrap_are_reproducible():
    metrics = binary_metrics([0, 1, 0, 1], [0.1, 0.8, 0.2, 0.7])
    assert metrics["pr_auc"] is not None
    assert "accuracy" not in metrics
    assert bootstrap_delta([0.1, 0.2, 0.3], iterations=100) == bootstrap_delta([0.1, 0.2, 0.3], iterations=100)
