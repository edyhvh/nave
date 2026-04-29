from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import Mock, patch

import pandas as pd

from trading.crypto.momentum import MomentumBacktester, MomentumSetupEngine, TradePlan
from trading.crypto.momentum.config import load_momentum_config
from trading.crypto.momentum.filters import ParticipationAssessment, VolatilityAssessment, assess_breakout, assess_volatility, normalize_frame
from trading.crypto.momentum.structure import assess_retest


def _frame(
    index: pd.DatetimeIndex,
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def _build_long_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily_idx = pd.date_range("2025-01-01", periods=80, freq="D", tz="UTC")
    daily_close = [100 + (idx * 0.9) for idx in range(80)]
    daily = _frame(
        daily_idx,
        [value - 0.6 for value in daily_close],
        [value + 1.2 for value in daily_close],
        [value - 1.4 for value in daily_close],
        daily_close,
        [1200 + idx * 5 for idx in range(80)],
    )

    setup_idx = pd.date_range("2025-03-01", periods=80, freq="4h", tz="UTC")
    setup_close = [108 + (idx * 0.1) for idx in range(60)]
    setup_close += [114.0, 114.2, 114.4, 114.7, 114.9, 115.1, 114.8, 115.0, 114.7, 115.1,
                    114.9, 115.2, 114.8, 115.0, 116.6, 117.1, 116.8, 117.8, 118.7, 119.4]
    setup_open = [value - 0.5 for value in setup_close]
    setup_high = [value + 0.8 for value in setup_close]
    setup_low = [value - 0.8 for value in setup_close]
    for idx in range(40, 60):
        setup_high[idx] = 111.0 + ((idx - 40) * 0.04)
        setup_low[idx] = 107.6 + ((idx - 40) * 0.04)
        setup_close[idx] = 109.0 + ((idx - 40) * 0.03)
        setup_open[idx] = setup_close[idx] - 0.2
    for idx in range(60, 74):
        setup_high[idx] = setup_close[idx] + 0.35
        setup_low[idx] = setup_close[idx] - 0.35
        setup_open[idx] = setup_close[idx] - 0.12
    setup_open[74] = 115.0
    setup_high[74] = 118.3
    setup_low[74] = 114.7
    setup_close[74] = 116.6
    for idx in range(75, 80):
        setup_high[idx] = setup_close[idx] + 0.75
        setup_low[idx] = setup_close[idx] - 0.65
        setup_open[idx] = setup_close[idx] - 0.25
    setup_volume = [900 + idx * 4 for idx in range(80)]
    setup_volume[74] = 3200
    setup = _frame(setup_idx, setup_open, setup_high, setup_low, setup_close, setup_volume)

    trigger_idx = pd.date_range("2025-03-09", periods=160, freq="1h", tz="UTC")
    trigger_close = [111.0 + (idx * 0.05) for idx in range(130)]
    trigger_close += [115.9, 116.2, 116.6, 116.0, 115.6, 115.8, 116.2, 116.6, 116.9, 117.1,
                      117.3, 117.5, 117.7, 117.9, 118.0, 118.1, 118.2, 118.3, 118.4, 118.5,
                      118.6, 118.7, 118.8, 118.9, 119.0, 119.1, 119.2, 119.3, 119.4, 119.5]
    trigger_open = [value - 0.35 for value in trigger_close]
    trigger_high = [value + 0.8 for value in trigger_close]
    trigger_low = [value - 0.8 for value in trigger_close]
    retest_start = 130
    trigger_low[retest_start + 4] = 114.9
    trigger_close[retest_start + 4] = 115.9
    trigger_open[retest_start + 4] = 115.3
    trigger = _frame(
        trigger_idx,
        trigger_open,
        trigger_high,
        trigger_low,
        trigger_close,
        [550 + idx * 2 for idx in range(160)],
    )

    oi = pd.DataFrame(
        {
            "timestamp": setup_idx,
            "open_interest": [1000 + idx * 2 for idx in range(60)]
            + [1180, 1190, 1205, 1225, 1240, 1255, 1270, 1285, 1300, 1315, 1330, 1345, 1360, 1375, 1390, 1405, 1420, 1435, 1450, 1465],
        }
    )
    return daily, setup, trigger, oi


def test_momentum_engine_confirms_high_quality_long_setup() -> None:
    daily, setup, trigger, oi = _build_long_frames()
    engine = MomentumSetupEngine()

    with patch.object(
        engine,
        "_assess_volatility",
        return_value=VolatilityAssessment(
            passed=True,
            atr_ratio=1.08,
            range_expansion=2.36,
            score=0.92,
            atr_fast=0.75,
        ),
    ):
        plans = engine.evaluate_symbol(
            symbol="BTCUSDT",
            daily_frame=daily,
            setup_frame=setup,
            trigger_frame=trigger,
            open_interest=oi,
            funding_rate=0.0002,
            account_equity=20000.0,
            risk_pct=0.005,
            side="long",
        )

    plan = plans[0]
    assert plan.side == "long"
    assert plan.setup_status == "confirmed"
    assert plan.tradeable is True
    assert plan.confidence_score >= 75
    assert plan.rr_estimated >= 1.8
    assert plan.expected_move_pct >= 0.08
    assert plan.leverage_constraints["recommended"] <= 4.0
    assert "daily_ema_gap_pct" in plan.diagnostics
    assert "setup_ema_gap_pct" in plan.diagnostics
    assert plan.reasoning["machine"][3]["passed"] is True
    breakout_level = plan.diagnostics["breakout_level"]
    tolerance = breakout_level * load_momentum_config().breakout.retest_tolerance
    assert plan.entry_zone[1] <= breakout_level + tolerance + 1e-6


def test_momentum_engine_rejects_crowded_funding_even_when_structure_is_good() -> None:
    daily, setup, trigger, oi = _build_long_frames()
    engine = MomentumSetupEngine()

    plan = engine.evaluate_symbol(
        symbol="BTCUSDT",
        daily_frame=daily,
        setup_frame=setup,
        trigger_frame=trigger,
        open_interest=oi,
        funding_rate=0.0018,
        side="long",
    )[0]

    assert plan.setup_status == "invalid"
    assert plan.tradeable is False
    assert plan.reasoning["machine"][5]["value"]["crowded"] is True


def test_momentum_engine_requires_volatility_confirmation_for_tradeability() -> None:
    daily, setup, trigger, oi = _build_long_frames()
    engine = MomentumSetupEngine()

    with patch.object(
        engine,
        "_assess_volatility",
        return_value=VolatilityAssessment(
            passed=False,
            atr_ratio=0.92,
            range_expansion=1.05,
            score=0.9,
            atr_fast=0.75,
        ),
    ):
        plan = engine.evaluate_symbol(
            symbol="BTCUSDT",
            daily_frame=daily,
            setup_frame=setup,
            trigger_frame=trigger,
            open_interest=oi,
            funding_rate=0.0002,
            side="long",
        )[0]

    assert plan.setup_status == "confirmed"
    assert plan.tradeable is False


def test_assess_volatility_requires_atr_support_for_range_expansion() -> None:
    config = load_momentum_config()
    idx = pd.date_range("2025-01-01", periods=60, freq="4h", tz="UTC")
    opens = [100.0] * len(idx)
    highs = [100.5] * 59 + [101.3]
    lows = [99.5] * 59 + [99.1]
    closes = [100.1] * len(idx)
    volumes = [1000.0] * len(idx)
    frame = _frame(idx, opens, highs, lows, closes, volumes).set_index("timestamp")
    atr_fast = pd.Series([0.94] * len(idx), index=idx)
    atr_slow = pd.Series([1.0] * len(idx), index=idx)

    with patch("trading.crypto.momentum.filters.atr", side_effect=[atr_fast, atr_slow]):
        assessment = assess_volatility(frame, idx[-1], config)

    assert assessment.atr_ratio == 0.94
    assert assessment.range_expansion > config.volatility.min_range_expansion
    assert assessment.passed is False


def test_momentum_engine_requires_rr_floor_for_tradeability() -> None:
    daily, setup, trigger, oi = _build_long_frames()
    engine = MomentumSetupEngine()

    with patch.object(
        engine,
        "_reward_profile",
        return_value=(0.08, 0.05, 1.6),
    ):
        plan = engine.evaluate_symbol(
            symbol="BTCUSDT",
            daily_frame=daily,
            setup_frame=setup,
            trigger_frame=trigger,
            open_interest=oi,
            funding_rate=0.0002,
            side="long",
        )[0]

    assert plan.setup_status == "confirmed"
    assert plan.tradeable is False
    assert plan.rr_estimated == 1.6


def test_momentum_engine_requires_stronger_volume_for_swing_horizon() -> None:
    daily, setup, trigger, oi = _build_long_frames()
    engine = MomentumSetupEngine()

    with patch.object(
        engine,
        "_reward_profile",
        return_value=(0.12, 0.04, 3.0),
    ), patch(
        "trading.crypto.momentum.engine.assess_participation",
        return_value=ParticipationAssessment(
            passed=True,
            score=0.9,
            volume_ratio=1.6,
            oi_change_pct=0.1,
            oi_supported=True,
            funding_rate=0.0002,
            crowded=False,
            squeeze_risk=False,
        ),
    ):
        plan = engine.evaluate_symbol(
            symbol="BTCUSDT",
            daily_frame=daily,
            setup_frame=setup,
            trigger_frame=trigger,
            open_interest=oi,
            funding_rate=0.0002,
            side="long",
        )[0]

    assert plan.expected_move_pct == 0.12
    assert plan.tradeable is False


def test_momentum_engine_requires_stronger_atr_for_swing_horizon() -> None:
    daily, setup, trigger, oi = _build_long_frames()
    engine = MomentumSetupEngine()

    with patch.object(
        engine,
        "_reward_profile",
        return_value=(0.12, 0.04, 3.0),
    ), patch.object(
        engine,
        "_assess_volatility",
        return_value=VolatilityAssessment(
            passed=True,
            atr_ratio=0.98,
            range_expansion=2.3,
            score=0.9,
            atr_fast=0.75,
        ),
    ), patch(
        "trading.crypto.momentum.engine.assess_participation",
        return_value=ParticipationAssessment(
            passed=True,
            score=0.9,
            volume_ratio=2.5,
            oi_change_pct=0.1,
            oi_supported=True,
            funding_rate=0.0002,
            crowded=False,
            squeeze_risk=False,
        ),
    ):
        plan = engine.evaluate_symbol(
            symbol="BTCUSDT",
            daily_frame=daily,
            setup_frame=setup,
            trigger_frame=trigger,
            open_interest=oi,
            funding_rate=0.0002,
            side="long",
        )[0]

    assert plan.expected_move_pct == 0.12
    assert plan.tradeable is False


def test_momentum_engine_rejects_stretched_intraday_setup_when_daily_gap_is_thin() -> None:
    daily, setup, trigger, oi = _build_long_frames()
    engine = MomentumSetupEngine()

    with patch.object(
        engine,
        "_reward_profile",
        return_value=(0.095, 0.04, 2.4),
    ), patch.object(
        engine,
        "_ema_gap_pct",
        side_effect=[0.061, 0.073],
    ), patch.object(
        engine,
        "_assess_volatility",
        return_value=VolatilityAssessment(
            passed=True,
            atr_ratio=1.2,
            range_expansion=2.3,
            score=0.9,
            atr_fast=0.75,
        ),
    ), patch(
        "trading.crypto.momentum.engine.assess_participation",
        return_value=ParticipationAssessment(
            passed=True,
            score=0.9,
            volume_ratio=2.5,
            oi_change_pct=0.1,
            oi_supported=True,
            funding_rate=0.0002,
            crowded=False,
            squeeze_risk=False,
        ),
    ):
        plan = engine.evaluate_symbol(
            symbol="BTCUSDT",
            daily_frame=daily,
            setup_frame=setup,
            trigger_frame=trigger,
            open_interest=oi,
            funding_rate=0.0002,
            side="long",
        )[0]

    assert plan.expected_move_pct == 0.095
    assert plan.tradeable is False


def test_backtester_returns_metrics_and_baseline_delta() -> None:
    daily, setup, trigger, oi = _build_long_frames()
    backtester = MomentumBacktester()

    payload = backtester.evaluate(
        symbol="ETHUSDT",
        daily_frame=daily,
        setup_frame=setup,
        trigger_frame=trigger,
        funding_rate=0.0001,
        open_interest=oi,
    )

    assert payload["strategy"] == "momentum_breakout_retest"
    assert "baseline" in payload
    assert set(payload["metrics"].keys()) == {
        "win_rate",
        "expectancy",
        "max_drawdown",
        "average_realized_move",
        "pct_reaching_8",
        "pct_reaching_12",
        "pct_reaching_20",
    }


def test_backtester_does_not_stack_overlapping_entries_from_same_setup() -> None:
    daily_idx = pd.date_range("2025-01-01", periods=90, freq="D", tz="UTC")
    setup_idx = pd.date_range("2025-03-01", periods=70, freq="4h", tz="UTC")
    trigger_idx = pd.date_range("2025-03-01", periods=420, freq="1h", tz="UTC")

    daily = _frame(
        daily_idx,
        [100.0] * len(daily_idx),
        [101.0] * len(daily_idx),
        [99.0] * len(daily_idx),
        [100.5] * len(daily_idx),
        [1_000.0] * len(daily_idx),
    )
    setup = _frame(
        setup_idx,
        [100.0] * len(setup_idx),
        [101.0] * len(setup_idx),
        [99.0] * len(setup_idx),
        [100.5] * len(setup_idx),
        [1_000.0] * len(setup_idx),
    )

    trigger_close = [100.0] * len(trigger_idx)
    trigger_high = [103.0] * len(trigger_idx)
    trigger_low = [99.0] * len(trigger_idx)
    trigger_high[300] = 108.5
    trigger = _frame(
        trigger_idx,
        [100.0] * len(trigger_idx),
        trigger_high,
        trigger_low,
        trigger_close,
        [500.0] * len(trigger_idx),
    )

    plan = TradePlan(
        symbol="BTCUSDT",
        side="long",
        setup_status="confirmed",
        entry_zone=[100.0, 100.0],
        invalidation=95.0,
        tp1=104.0,
        tp2=108.0,
        tp3=112.0,
        expected_move_pct=0.08,
        rr_estimated=1.8,
        holding_horizon_estimate="intraday",
        confidence_score=95,
        tradeable=True,
        score_breakdown={},
        reasoning={"machine": []},
        sizing={},
        leverage_constraints={},
    )

    backtester = MomentumBacktester()
    backtester.engine.evaluate_symbol = Mock(return_value=[plan])

    payload = backtester.evaluate(
        symbol="BTCUSDT",
        daily_frame=daily,
        setup_frame=setup,
        trigger_frame=trigger,
        baseline=True,
    )

    assert payload["trade_count"] == 1
    assert payload["trades"][0]["exit_price"] == 108.0
    assert payload["trades"][0]["best_move_pct"] >= 0.08
    assert payload["trades"][0]["worst_move_pct"] <= -0.01
    assert payload["trades"][0]["score_breakdown"] == {}
    assert payload["trades"][0]["diagnostics"] == {}


def test_assess_retest_invalidates_stale_confirmation() -> None:
    breakout_level = 100.0
    breakout_index = pd.Timestamp("2025-01-01T00:00:00Z")
    trigger_idx = pd.date_range(breakout_index, periods=36, freq="1h", tz="UTC")
    closes = [101.2] * 30 + [100.4, 100.8, 101.0, 101.1, 101.2, 101.3]
    highs = [close + 0.4 for close in closes]
    lows = [100.95] * 30 + [99.95, 100.1, 100.2, 100.3, 100.4, 100.5]
    frame = _frame(
        trigger_idx,
        [close - 0.1 for close in closes],
        highs,
        lows,
        closes,
        [500] * len(trigger_idx),
    )

    retest = assess_retest(
        frame.set_index("timestamp"),
        "long",
        breakout_level,
        breakout_index,
        load_momentum_config(),
    )

    assert retest.confirmed is False
    assert retest.status == "invalid"


def test_assess_retest_requires_maturation_before_confirmation() -> None:
    breakout_level = 100.0
    breakout_index = pd.Timestamp("2025-01-01T00:00:00Z")
    trigger_idx = pd.date_range(breakout_index, periods=6, freq="1h", tz="UTC")
    closes = [101.2, 100.3, 100.6, 100.8, 100.9, 101.1]
    highs = [close + 0.3 for close in closes]
    lows = [100.8, 99.95, 100.0, 100.1, 100.2, 100.3]
    frame = _frame(
        trigger_idx,
        [close - 0.1 for close in closes],
        highs,
        lows,
        closes,
        [500] * len(trigger_idx),
    )

    retest = assess_retest(
        frame.set_index("timestamp"),
        "long",
        breakout_level,
        breakout_index,
        load_momentum_config(),
    )

    assert retest.confirmed is False
    assert retest.status == "pending"