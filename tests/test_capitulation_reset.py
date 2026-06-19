from __future__ import annotations

import pandas as pd

from trading.crypto.analysis.capitulation_reset import (
    assess_cot_early_trend_entry,
    assess_crowded_long_failed_reset_short,
    assess_crowded_long_reset,
)
from trading.crypto.cot.cot_analyzer import COTBias


def _frame(closes: list[float], *, freq: str = "4h") -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(closes), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=idx,
    )


def _cot() -> COTBias:
    return COTBias(
        asset="BTC",
        net_non_commercial=10_000,
        pct_oi_non_com=18.0,
        weekly_change=500,
        bias="bearish",
        confidence=0.86,
        historical_percentile=96,
    )


def _daily() -> pd.DataFrame:
    return _frame([100.0] * 10 + [95, 90, 84, 80, 78, 76], freq="D")


def _oi(contracting: bool = True) -> pd.Series:
    values = [100.0] * 20 + ([85.0] if contracting else [115.0])
    return pd.Series(values)


def test_crowded_long_liquidation_without_reclaim_is_watch_only() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 71, 70, 70.5, 71])

    result = assess_crowded_long_reset(
        daily=_daily(),
        setup=setup,
        trigger=None,
        cot_bias=_cot(),
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert result is not None
    assert result.action == "watch"
    assert result.size_fraction == 0.0


def test_one_hour_reclaim_allows_reduced_starter_only() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 72])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")

    result = assess_crowded_long_reset(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert result is not None
    assert result.action == "starter_long"
    assert result.size_fraction <= 0.25


def test_four_hour_retest_hold_allows_confirmed_long() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 70.8, 71.4, 72])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")

    result = assess_crowded_long_reset(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert result is not None
    assert result.action == "confirmed_long"
    assert result.size_fraction == 0.5


def test_confirmed_long_full_size_when_daily_structure_bullish() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 70.8, 71.4, 72])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")
    daily = _frame(
        [100.0] * 10 + [95, 90, 84, 80, 78, 76, 74, 72, 70, 68, 70, 72, 75, 78, 82],
        freq="D",
    )

    result = assess_crowded_long_reset(
        daily=daily,
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert result is not None
    assert result.action == "confirmed_long"
    assert result.size_fraction == 1.0


def test_positive_funding_and_rising_oi_block_starter_after_bounce() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 72])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")

    result = assess_crowded_long_reset(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=0.0002,
        open_interest=_oi(False),
    )

    assert result is not None
    assert result.action == "watch"
    assert any("Positive funding" in blocker for blocker in result.blockers)


def test_positive_funding_and_rising_oi_emit_failed_reset_short() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 72])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")

    result = assess_crowded_long_failed_reset_short(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=0.0002,
        open_interest=_oi(False),
    )

    assert result is not None
    assert result.kind == "failed_reset_continuation_short"
    assert result.direction == "short"
    assert result.action == "watch"
    assert result.size_fraction == 0.5
    assert any("Funding/OI did not reset" in item for item in result.reset_evidence)


def test_confirmed_clean_reset_does_not_emit_failed_reset_short() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 70.8, 71.4, 72])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")

    result = assess_crowded_long_failed_reset_short(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert result is None


def test_small_oi_contraction_is_not_enough_for_reset_long() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 72])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")
    shallow_oi_reset = pd.Series([100.0] * 20 + [98.0])

    result = assess_crowded_long_reset(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=-0.0001,
        open_interest=shallow_oi_reset,
    )

    assert result is not None
    assert result.action == "watch"
    assert any("below reset threshold" in blocker for blocker in result.blockers)


def test_four_hour_confirm_requires_actual_retest_near_reclaim_level() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 75, 76, 77, 78])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")

    result = assess_crowded_long_reset(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert result is not None
    assert result.action == "starter_long"


def test_new_low_after_reclaim_invalidates_setup() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 68.5, 70.5])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")

    result = assess_crowded_long_reset(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert result is not None
    assert result.action == "watch"
    assert any("New low" in blocker for blocker in result.blockers)


def test_early_trend_long_requires_reclaim_trigger_and_oi_expansion() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 70.8, 71.4, 72])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")
    oi_expanding = pd.Series([100.0] * 20 + [112.0])

    results = assess_cot_early_trend_entry(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=-0.0001,
        open_interest=oi_expanding,
    )

    long = next(item for item in results if item.kind == "early_trend_long")
    assert long.action == "starter_trend_long"
    assert long.size_fraction == 0.25
    assert long.context
    assert long.trigger
    assert long.confirmation


def test_early_trend_short_uses_failed_reclaim_and_1h_breakdown() -> None:
    setup = _frame([100, 96, 92, 88, 84, 80, 78, 76, 74, 72, 70, 69, 71, 70, 69, 68])
    trigger = _frame([70.2, 70.0, 69.8, 69.5, 69.2, 68.7], freq="1h")
    oi_expanding = pd.Series([100.0] * 20 + [110.0])

    results = assess_cot_early_trend_entry(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=0.0001,
        open_interest=oi_expanding,
    )

    short = next(item for item in results if item.kind == "early_trend_short")
    assert short.action in {"starter_trend_short", "confirmed_trend_short"}
    assert short.direction == "short"
    assert short.size_fraction >= 0.25
    assert any("COT crowded long" in item for item in short.reset_evidence)


def test_early_trend_short_requires_explicit_derivative_confirmation() -> None:
    setup = _frame([100, 96, 92, 88, 84, 80, 78, 76, 74, 72, 70, 69, 71, 70, 69, 68])
    trigger = _frame([70.2, 70.0, 69.8, 69.5, 69.2, 68.7], freq="1h")

    results = assess_cot_early_trend_entry(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=None,
        open_interest=None,
    )

    assert results
    assert all(item.action == "watch" for item in results)
    assert any(
        "No OI/funding confirmation" in blocker
        for item in results
        for blocker in item.blockers
    )


def test_early_trend_short_can_use_oi_expansion_when_funding_missing() -> None:
    setup = _frame([100, 96, 92, 88, 84, 80, 78, 76, 74, 72, 70, 69, 71, 70, 69, 68])
    trigger = _frame([70.2, 70.0, 69.8, 69.5, 69.2, 68.7], freq="1h")
    oi_expanding = pd.Series([100.0] * 20 + [110.0])

    results = assess_cot_early_trend_entry(
        daily=_daily(),
        setup=setup,
        trigger=trigger,
        cot_bias=_cot(),
        funding_rate=None,
        open_interest=oi_expanding,
    )

    short = next(item for item in results if item.kind == "early_trend_short")
    assert short.action in {"starter_trend_short", "confirmed_trend_short"}


def test_incomplete_early_trend_stack_is_watch_only() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 71, 70, 70.5, 71])

    results = assess_cot_early_trend_entry(
        daily=_daily(),
        setup=setup,
        trigger=None,
        cot_bias=_cot(),
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert results
    assert all(item.action == "watch" for item in results)
