from __future__ import annotations

import pandas as pd
import pytest

from scripts.secondary_lane_experiment import simulate_secondary_trade


def _trigger_frame(rows: list[tuple[float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "open": [close for _, _, close in rows],
            "high": [high for high, _, _ in rows],
            "low": [low for _, low, _ in rows],
            "close": [close for _, _, close in rows],
            "volume": [1000.0] * len(rows),
        },
        index=idx,
    )


def test_short_secondary_trade_enters_on_zone_touch_and_hits_target():
    path = _trigger_frame(
        [
            (101.0, 99.0, 100.0),
            (103.0, 98.0, 99.0),
            (100.0, 94.0, 95.0),
        ]
    )

    trade = simulate_secondary_trade(
        period="test",
        symbol="BTCUSDT",
        kind="relief_rally_fade",
        side="short",
        setup_time=path.index[0],
        entry_zone=[102.0, 104.0],
        invalidation=106.0,
        targets=[98.0, 94.0],
        future_trigger=path,
        max_bars=10,
        size_fraction=0.5,
        confidence=0.72,
    )

    assert trade is not None
    assert trade.entry_time == path.index[1]
    assert trade.exit_time == path.index[2]
    assert trade.r_multiple == 2.0
    assert trade.sized_r == 1.0


def test_long_secondary_trade_checks_stop_before_target_on_same_bar():
    path = _trigger_frame(
        [
            (101.0, 99.0, 100.0),
            (112.0, 94.0, 108.0),
        ]
    )

    trade = simulate_secondary_trade(
        period="test",
        symbol="ETHUSDT",
        kind="notrend_range_long",
        side="long",
        setup_time=path.index[0],
        entry_zone=[98.0, 100.0],
        invalidation=95.0,
        targets=[106.0, 110.0],
        future_trigger=path,
        max_bars=10,
        size_fraction=0.25,
        confidence=0.55,
        target_policy="tp2",
    )

    assert trade is not None
    assert trade.exit_price == 95.0
    assert trade.r_multiple == -1.0
    assert trade.sized_r == -0.25


def test_playbook_target_policy_exits_notrend_at_first_target():
    path = _trigger_frame(
        [
            (101.0, 99.0, 100.0),
            (107.0, 99.0, 106.0),
            (112.0, 105.0, 110.0),
        ]
    )

    trade = simulate_secondary_trade(
        period="test",
        symbol="ETHUSDT",
        kind="notrend_range_long",
        side="long",
        setup_time=path.index[0],
        entry_zone=[98.0, 100.0],
        invalidation=95.0,
        targets=[106.0, 110.0],
        future_trigger=path,
        max_bars=10,
        size_fraction=0.25,
        confidence=0.55,
        target_policy="playbook",
    )

    assert trade is not None
    assert trade.target_price == 106.0
    assert trade.exit_price == 106.0
    assert trade.r_multiple == 1.2


def test_rejection_mode_waits_for_directional_rejection_after_touch():
    idx = pd.date_range("2025-01-01", periods=4, freq="1h", tz="UTC")
    path = pd.DataFrame(
        {
            "open": [100.0, 102.5, 99.0, 95.0],
            "high": [101.0, 103.0, 104.0, 100.0],
            "low": [99.0, 99.0, 97.0, 94.0],
            "close": [100.0, 102.5, 98.0, 95.0],
            "volume": [1000.0] * 4,
        },
        index=idx,
    )

    trade = simulate_secondary_trade(
        period="test",
        symbol="BTCUSDT",
        kind="relief_rally_fade",
        side="short",
        setup_time=path.index[0],
        entry_zone=[102.0, 104.0],
        invalidation=106.0,
        targets=[98.0, 94.0],
        future_trigger=path,
        max_bars=10,
        size_fraction=0.5,
        confidence=0.72,
        daily_trend="short",
        setup_trend="long",
        entry_mode="rejection",
        target_policy="tp2",
    )

    assert trade is not None
    assert trade.entry_time == path.index[2]
    assert trade.entry_price == 98.0
    assert trade.trend_alignment == "mixed"
    assert trade.entry_mode == "rejection"
    assert trade.target_policy == "tp2"


def test_rejection_mode_excludes_rejection_candle_range_from_exits():
    idx = pd.date_range("2025-01-01", periods=4, freq="1h", tz="UTC")
    path = pd.DataFrame(
        {
            "open": [100.0, 102.5, 99.0, 96.0],
            "high": [101.0, 103.0, 104.0, 97.0],
            "low": [99.0, 99.0, 93.0, 95.0],
            "close": [100.0, 102.5, 98.0, 96.0],
            "volume": [1000.0] * 4,
        },
        index=idx,
    )

    trade = simulate_secondary_trade(
        period="test",
        symbol="BTCUSDT",
        kind="relief_rally_fade",
        side="short",
        setup_time=path.index[0],
        entry_zone=[102.0, 104.0],
        invalidation=106.0,
        targets=[98.0, 94.0],
        future_trigger=path,
        max_bars=10,
        size_fraction=0.5,
        confidence=0.72,
        entry_mode="rejection",
        target_policy="tp2",
    )

    assert trade is not None
    assert trade.entry_time == path.index[2]
    assert trade.exit_time == path.index[3]
    assert trade.exit_price == 96.0
    assert trade.r_multiple == pytest.approx(0.25)
