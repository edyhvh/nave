from datetime import datetime, timedelta, timezone

from research.nave.outcome_coverage import (
    COMPLETE,
    FAILED,
    INTERNAL_GAP,
    RIGHT_CENSORED,
    UNRESOLVED,
    classify_provider_hours,
    decision_time_eligible,
    filter_selected_events,
    required_hour_keys,
    token_horizon_status,
)


UTC = timezone.utc
T0 = datetime(2026, 8, 28, 0, 59, 30, tzinfo=UTC)


def hours(*values: str) -> dict[str, str]:
    return {value: COMPLETE for value in values}


def test_hour_mask_is_half_open_in_construction_but_includes_target_hour():
    assert required_hour_keys(T0, T0 + timedelta(minutes=1)) == (
        "2026-08-28T00",
        "2026-08-28T01",
    )


def test_token_horizon_is_full_when_another_hour_is_missing_elsewhere():
    status = token_horizon_status(
        launch_time=datetime(2026, 8, 28, 20, tzinfo=UTC),
        horizon_seconds=3600,
        hour_status=hours("2026-08-28T20", "2026-08-28T21"),
        collection_end=datetime(2026, 8, 28, 23, 59, tzinfo=UTC),
        has_horizon_observation=True,
    )
    assert status == "FULL_60M"


def test_internal_gap_is_not_relabelled_as_right_censoring():
    status = token_horizon_status(
        launch_time=datetime(2026, 8, 28, 0, 30, tzinfo=UTC),
        horizon_seconds=3600,
        hour_status={"2026-08-28T00": COMPLETE, "2026-08-28T01": FAILED},
        collection_end=datetime(2026, 8, 28, 23, 59, tzinfo=UTC),
        has_horizon_observation=True,
    )
    assert status == INTERNAL_GAP


def test_future_collection_end_is_right_censored_not_unknown_or_dead():
    status = token_horizon_status(
        launch_time=datetime(2026, 8, 28, 23, 30, tzinfo=UTC),
        horizon_seconds=3600,
        hour_status=hours("2026-08-28T23"),
        collection_end=datetime(2026, 8, 28, 23, 59, tzinfo=UTC),
        has_horizon_observation=False,
    )
    assert status == RIGHT_CENSORED


def test_complete_interval_without_mark_is_unresolved():
    status = token_horizon_status(
        launch_time=datetime(2026, 8, 28, 12, tzinfo=UTC),
        horizon_seconds=900,
        hour_status=hours("2026-08-28T12"),
        collection_end=datetime(2026, 8, 28, 23, 59, tzinfo=UTC),
        has_horizon_observation=False,
    )
    assert status == UNRESOLVED


def test_decision_time_features_require_availability_timestamp():
    decision = datetime(2026, 8, 28, 12, 0, 1, tzinfo=UTC)
    assert decision_time_eligible(available_at=decision - timedelta(seconds=1), decision_time=decision)
    assert not decision_time_eligible(available_at=decision + timedelta(seconds=1), decision_time=decision)
    assert not decision_time_eligible(available_at=None, decision_time=decision)


def test_provider_gap_handling_preserves_missing_hours():
    mask = classify_provider_hours(
        complete_hours={"2026-08-28T00"}, partial_hours={"2026-08-28T01"}
    )
    assert mask == {"2026-08-28T00": COMPLETE, "2026-08-28T01": "PARTIAL"}


def test_pumpapi_filtering_keeps_only_the_frozen_mint_sample():
    events = [{"mint": "keep", "price": 1}, {"mint": "drop", "price": 999}]
    assert filter_selected_events(events, {"keep"}) == [{"mint": "keep", "price": 1}]
