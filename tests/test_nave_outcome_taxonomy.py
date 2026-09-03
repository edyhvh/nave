from research.nave.outcome_taxonomy import (
    OutcomeEvidence,
    OutcomeStatus,
    UnresolvedReason,
    classify_outcome,
)


def classify(**overrides: object) -> tuple[OutcomeStatus, str | None]:
    values = {"interval_complete": True, "target_right_censored": False, **overrides}
    evidence = OutcomeEvidence(**values)
    return classify_outcome(evidence)


def test_no_future_trade_is_not_provider_missing_or_dead():
    assert classify(future_trade_count=0) == (
        OutcomeStatus.UNRESOLVED,
        UnresolvedReason.NO_FUTURE_TRADE.value,
    )


def test_no_activity_through_horizon_is_horizon_specific_inactivity():
    assert classify(future_trade_count=0, no_activity_through_horizon=True) == (
        OutcomeStatus.UNRESOLVED,
        UnresolvedReason.TOKEN_INACTIVE.value,
    )


def test_provider_gap_precedes_economic_inactivity():
    assert classify(interval_complete=False, future_trade_count=0) == (
        OutcomeStatus.UNRESOLVED,
        UnresolvedReason.PROVIDER_EVENT_GAP.value,
    )


def test_migration_is_not_death():
    assert classify(migration_before_horizon=True) == (
        OutcomeStatus.UNRESOLVED,
        UnresolvedReason.MIGRATED_BEFORE_HORIZON.value,
    )


def test_valid_venue_aware_mark_resolves_even_if_migration_is_present():
    assert classify(valid_mark_count=1, migration_before_horizon=True) == (
        OutcomeStatus.RESOLVED,
        None,
    )


def test_price_input_failure_is_distinct_from_no_trade():
    assert classify(future_trade_count=2, missing_price_count=2) == (
        OutcomeStatus.UNRESOLVED,
        UnresolvedReason.PRICE_INPUT_MISSING.value,
    )


def test_right_censoring_is_not_unresolved():
    assert classify(target_right_censored=True) == (
        OutcomeStatus.RIGHT_CENSORED,
        UnresolvedReason.RIGHT_CENSORED.value,
    )
