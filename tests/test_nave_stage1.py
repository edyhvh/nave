from research.nave.stage1 import SurvivalStatus, future_trade_label


def test_label_excludes_decision_boundary_and_requires_future_window() -> None:
    label = future_trade_label(
        decision_ms=1000, window_start_ms=2000, window_end_ms=3000,
        collection_end_ms=4000, trade_times_ms=[1000, 2000, 2500, 3000],
    )
    assert label.status is SurvivalStatus.POSITIVE
    assert label.future_trade_count == 2


def test_no_trade_is_negative_only_when_interval_is_complete() -> None:
    label = future_trade_label(
        decision_ms=1000, window_start_ms=2000, window_end_ms=3000,
        collection_end_ms=2999, trade_times_ms=[],
    )
    assert label.status is SurvivalStatus.RIGHT_CENSORED


def test_provider_gap_is_not_inactivity() -> None:
    label = future_trade_label(
        decision_ms=1000, window_start_ms=2000, window_end_ms=3000,
        collection_end_ms=4000, trade_times_ms=[], provider_complete=False,
    )
    assert label.status is SurvivalStatus.PROVIDER_GAP


def test_migration_is_not_death_without_continuation() -> None:
    label = future_trade_label(
        decision_ms=1000, window_start_ms=2000, window_end_ms=3000,
        collection_end_ms=4000, trade_times_ms=[], migration_times_ms=[2500],
    )
    assert label.status is SurvivalStatus.MIGRATION_UNKNOWN
