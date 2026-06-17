from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from trading.crypto.analysis.opportunities import _demand_zone, _supply_zone, detect_secondary_opportunities
from trading.crypto.analysis.regime import RegimeAssessment, assess_regime


def _frame(closes: list[float], *, freq: str = "D") -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": idx,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        }
    ).set_index("timestamp")


def test_directional_cot_arms_bear_regime_without_crowded_percentile():
    daily_closes = [95_000.0] * 10 + list(range(95_000, 68_000, -2_000)) + [70_000, 72_000, 71_500]
    setup_closes = daily_closes[-30:]
    daily = _frame(daily_closes)
    setup = _frame(setup_closes, freq="4h")

    cot = MagicMock(bias="bearish", confidence=0.72, historical_percentile=50)

    result = assess_regime(daily=daily, setup=setup, cot_bias=cot, best_plan=None)
    assert result.bias == "bearish"
    assert result.phase != "neutral"


def test_relief_rally_fade_secondary_when_primary_stand_aside():
    daily_closes = [95_000.0] * 10 + list(range(95_000, 68_000, -2_000)) + [70_000, 72_000, 71_500]
    setup_closes = daily_closes[-30:]
    daily = _frame(daily_closes)
    setup = _frame(setup_closes, freq="4h")

    cot = MagicMock(bias="bearish", confidence=0.72, historical_percentile=50)
    regime = assess_regime(daily=daily, setup=setup, cot_bias=cot, best_plan=None)

    plans = [
        {
            "side": "short",
            "confidence_score": 52,
            "setup_status": "invalid",
            "tradeable": False,
            "diagnostics": {
                "theory_overlay": {
                    "passed": False,
                    "reason": "daily theory confirmation is missing",
                }
            },
        }
    ]

    opps = detect_secondary_opportunities(
        daily=daily,
        setup=setup,
        cot_bias=cot,
        regime=regime,
        plans=plans,
        primary_action="stand_aside",
    )
    kinds = {o["kind"] for o in opps}
    assert "relief_rally_fade" in kinds or "forming_short" in kinds


def test_relief_rally_fade_rejects_bounce_below_threshold():
    """Bounce metrics are stored as percent; thresholds are fractions in config."""
    daily_closes = [95_000.0] * 30
    setup_closes = [70_000.0] * 30
    daily = _frame(daily_closes)
    setup = _frame(setup_closes, freq="4h")

    cot = MagicMock(bias="bearish", confidence=0.72, historical_percentile=50)
    regime = RegimeAssessment(
        phase="leg_down",
        bias="bearish",
        confidence=0.7,
        playbook="test",
        supply_zone=[70_000, 72_000],
        continuation_trigger=None,
        metrics={"bounce_from_14d_low_pct": 0.5, "drawdown_from_28d_high_pct": 12.0},
    )

    opps = detect_secondary_opportunities(
        daily=daily,
        setup=setup,
        cot_bias=cot,
        regime=regime,
        plans=[],
        primary_action="watch",
    )
    assert not any(o["kind"] == "relief_rally_fade" for o in opps)


def test_forming_breakdown_short_when_momentum_blocked_by_daily():
    cot = MagicMock(bias="bearish", confidence=0.73, historical_percentile=50)
    regime = RegimeAssessment(
        phase="neutral",
        bias="neutral",
        confidence=0.0,
        playbook="test",
        supply_zone=None,
        continuation_trigger=None,
        metrics={"bounce_from_14d_low_pct": 5.0, "drawdown_from_28d_high_pct": 10.0},
    )
    daily = _frame([100.0] * 30)
    setup = _frame([100.0] * 30, freq="4h")
    plans = [
        {
            "side": "short",
            "confidence_score": 52,
            "setup_status": "invalid",
            "entry_zone": [1640.0, 1670.0],
            "invalidation": 1700.0,
            "tp1": 1600.0,
            "tp2": 1550.0,
            "diagnostics": {
                "theory_overlay": {
                    "passed": False,
                    "reason": "daily theory confirmation is missing",
                }
            },
        }
    ]

    opps = detect_secondary_opportunities(
        daily=daily,
        setup=setup,
        cot_bias=cot,
        regime=regime,
        plans=plans,
        primary_action="stand_aside",
    )
    forming = [o for o in opps if o["kind"] == "forming_short"]
    assert len(forming) == 1
    assert forming[0]["direction"] == "short"
    assert forming[0]["entry_zone"] == [1640.0, 1670.0]
    assert forming[0]["invalidation"] == 1700.0
    assert forming[0]["size_fraction"] == 0.5


def test_forming_breakdown_short_uses_structured_daily_stage():
    cot = MagicMock(bias="bearish", confidence=0.73, historical_percentile=50)
    regime = RegimeAssessment(
        phase="neutral",
        bias="neutral",
        confidence=0.0,
        playbook="test",
        supply_zone=None,
        continuation_trigger=None,
        metrics={"bounce_from_14d_low_pct": 5.0, "drawdown_from_28d_high_pct": 10.0},
    )
    daily = _frame([100.0] * 30)
    setup = _frame([100.0] * 30, freq="4h")
    plans = [
        {
            "side": "short",
            "confidence_score": 52,
            "setup_status": "invalid",
            "entry_zone": [1640.0, 1670.0],
            "invalidation": 1700.0,
            "tp1": 1600.0,
            "tp2": 1550.0,
            "diagnostics": {
                "theory_overlay": {
                    "passed": False,
                    "stage": "daily",
                    "reason": "confirmation missing",
                }
            },
        }
    ]

    opps = detect_secondary_opportunities(
        daily=daily,
        setup=setup,
        cot_bias=cot,
        regime=regime,
        plans=plans,
        primary_action="stand_aside",
    )

    assert any(o["kind"] == "forming_short" for o in opps)


def test_supply_and_demand_zones_are_ordered():
    supply = _supply_zone(high_28d=100.0, ema_fast_s=120.0, close_s=110.0)
    demand = _demand_zone(low_28d=100.0, ema_fast_s=80.0, close_s=90.0)

    assert supply[0] < supply[1]
    assert demand[0] < demand[1]


def test_no_secondary_when_primary_enter():
    daily = _frame([100.0] * 30)
    setup = _frame([100.0] * 30, freq="4h")
    cot = MagicMock(bias="bearish", confidence=0.8, historical_percentile=90)
    regime = RegimeAssessment(
        phase="leg_down",
        bias="bearish",
        confidence=0.7,
        playbook="test",
        supply_zone=None,
        continuation_trigger=None,
        metrics={},
    )
    assert (
        detect_secondary_opportunities(
            daily=daily,
            setup=setup,
            cot_bias=cot,
            regime=regime,
            plans=[],
            primary_action="enter",
        )
        == []
    )
