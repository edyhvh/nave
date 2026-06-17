from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from trading.crypto.analysis.capitulation_reset import assess_crowded_long_reset
from trading.crypto.analysis.opportunities import detect_secondary_opportunities
from trading.crypto.analysis.regime import RegimeAssessment
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


def _crowded_cot() -> COTBias:
    return COTBias(
        asset="BTC",
        net_non_commercial=10_000,
        pct_oi_non_com=18.0,
        weekly_change=500,
        bias="bearish",
        confidence=0.86,
        historical_percentile=96,
    )


def _daily_drawdown() -> pd.DataFrame:
    return _frame([100.0] * 10 + [95, 90, 84, 80, 78, 76, 74, 72, 70, 68], freq="D")


def _oi(contracting: bool = True) -> pd.Series:
    values = [100.0] * 20 + ([85.0] if contracting else [115.0])
    return pd.Series(values)


def test_detect_secondary_opportunities_includes_capitulation_lane_when_crowded_long() -> None:
    daily = _daily_drawdown()
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 72])
    cot = _crowded_cot()
    regime = RegimeAssessment(
        phase="leg_down",
        bias="bearish",
        confidence=0.7,
        playbook="test",
        supply_zone=[72, 74],
        continuation_trigger=None,
        metrics={"bounce_from_14d_low_pct": 2.0, "drawdown_from_28d_high_pct": 30.0},
    )

    opps = detect_secondary_opportunities(
        daily=daily,
        setup=setup,
        trigger=None,
        cot_bias=cot,
        regime=regime,
        plans=[],
        primary_action="stand_aside",
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    kinds = {o["kind"] for o in opps}
    assert "capitulation_reclaim_long" in kinds
    reset = next(o for o in opps if o["kind"] == "capitulation_reclaim_long")
    assert reset["action"] == "watch"
    assert reset["size_fraction"] == 0.0


def test_detect_secondary_opportunities_includes_failed_reset_short_when_derivatives_stay_crowded(
) -> None:
    daily = _daily_drawdown()
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 72])
    cot = _crowded_cot()
    regime = RegimeAssessment(
        phase="leg_down",
        bias="bearish",
        confidence=0.7,
        playbook="test",
        supply_zone=[72, 74],
        continuation_trigger=None,
        metrics={"bounce_from_14d_low_pct": 2.0, "drawdown_from_28d_high_pct": 30.0},
    )

    opps = detect_secondary_opportunities(
        daily=daily,
        setup=setup,
        trigger=None,
        cot_bias=cot,
        regime=regime,
        plans=[],
        primary_action="stand_aside",
        funding_rate=0.0002,
        open_interest=_oi(False),
    )

    kinds = {o["kind"] for o in opps}
    assert "capitulation_reclaim_long" in kinds
    assert "failed_reset_continuation_short" in kinds
    failed = next(o for o in opps if o["kind"] == "failed_reset_continuation_short")
    assert failed["direction"] == "short"
    assert failed["size_fraction"] == 0.5
    assert any("short/fade priority" in reason for reason in failed["reasons"])


def test_confirmed_long_sizes_half_without_daily_confirm() -> None:
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 70.8, 71.4, 72])
    trigger = _frame([68.5, 69.0, 68.7, 69.5, 70.2, 70.8], freq="1h")

    result = assess_crowded_long_reset(
        daily=_daily_drawdown(),
        setup=setup,
        trigger=trigger,
        cot_bias=_crowded_cot(),
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert result is not None
    assert result.action == "confirmed_long"
    assert result.size_fraction == 0.5


def test_confirmed_long_sizes_full_when_daily_confirms_bullish() -> None:
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
        cot_bias=_crowded_cot(),
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert result is not None
    assert result.action == "confirmed_long"
    assert result.size_fraction == 1.0


def test_capitulation_lane_not_emitted_when_cot_not_crowded() -> None:
    daily = _daily_drawdown()
    setup = _frame([100, 95, 90, 84, 80, 76, 74, 73, 72, 70, 69, 71, 72])
    cot = MagicMock(bias="bearish", confidence=0.6, historical_percentile=50)
    regime = RegimeAssessment(
        phase="leg_down",
        bias="bearish",
        confidence=0.7,
        playbook="test",
        supply_zone=[72, 74],
        continuation_trigger=None,
        metrics={"bounce_from_14d_low_pct": 2.0, "drawdown_from_28d_high_pct": 30.0},
    )

    opps = detect_secondary_opportunities(
        daily=daily,
        setup=setup,
        cot_bias=cot,
        regime=regime,
        plans=[],
        primary_action="stand_aside",
        funding_rate=-0.0001,
        open_interest=_oi(True),
    )

    assert not any(o["kind"] == "capitulation_reclaim_long" for o in opps)
