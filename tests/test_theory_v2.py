"""Tests for the theory v2 execution engine."""

from __future__ import annotations

import pandas as pd
import pytest

from trading.execution import build_execution_plan
from trading.signals import Direction, Timeframe
from trading.theory_v2 import (
    TheoryV2Engine,
    chase_gate,
    daily_atr,
    daily_confirms,
    detect_climax_cooldown,
    find_impulse_leg,
    four_h_setup_valid,
    one_h_entry,
    trend,
    weekly_bias,
)


def _series_close(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=len(values), freq="h", tz="UTC"),
            "close": values,
            "high": [v * 1.01 for v in values],
            "low": [v * 0.99 for v in values],
            "open": values,
        }
    )


def _ohlc(values: list[float], spread: float = 0.5) -> pd.DataFrame:
    """Build a tight OHLC frame around ``values`` with controlled bar range.

    Tight, fixed spread keeps true range small enough that simple ramps do
    not accidentally trip the climax gate.
    """
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=len(values), freq="h", tz="UTC"),
            "open": values,
            "close": values,
            "high": [v + spread for v in values],
            "low": [v - spread for v in values],
        }
    )


def test_trend_long_when_close_above_ma():
    df = _series_close([100.0] * 9 + [110.0])
    assert trend(df["close"], window=8) == "long"


def test_trend_short_when_close_below_ma():
    df = _series_close([100.0] * 9 + [90.0])
    assert trend(df["close"], window=8) == "short"


def test_trend_neutral_inside_deadband():
    df = _series_close([100.0] * 9 + [100.2])
    assert trend(df["close"], window=8) == "neutral"


def test_weekly_bias_neutral_on_empty():
    assert weekly_bias(pd.DataFrame()) == "neutral"


def test_daily_confirms_matches_bias():
    rising = _series_close([100.0] * 21 + [115.0])
    assert daily_confirms(rising, "long") is True
    assert daily_confirms(rising, "short") is False


def test_four_h_setup_requires_alignment():
    rising = _series_close([100.0] * 13 + [115.0])
    assert four_h_setup_valid(rising, "long") is True
    assert four_h_setup_valid(rising, "short") is False


def test_one_h_entry_long_geometry():
    closes = [100.0] * 23 + [110.0]
    h1 = _series_close(closes)
    result = one_h_entry(h1, "long")
    assert result is not None
    entry, sl, tp = result
    assert entry == pytest.approx(110.0)
    # stop is min low across last 24 bars: 99 (from first bars) wait — last 24 includes the 110 bar with low 108.9
    # min low across all 24 bars = min of (99, 99, ..., 108.9) = 99
    assert sl == pytest.approx(99.0)
    assert tp == pytest.approx(110.0 + 2 * (110.0 - 99.0))


def test_one_h_entry_returns_none_on_zero_risk():
    # Force swing low == close so the long-side risk distance is zero.
    h1 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=25, freq="h", tz="UTC"),
            "open": [100.0] * 25,
            "close": [100.0] * 25,
            "high": [100.0] * 25,
            "low": [100.0] * 25,
        }
    )
    assert one_h_entry(h1, "long") is None


def test_engine_returns_neutral_when_weekly_bias_neutral():
    flat = _series_close([100.0] * 30)
    engine = TheoryV2Engine()
    decision = engine.evaluate("BTC", flat, flat, flat, flat)
    assert decision.signal is None
    assert decision.stage == "weekly"


def test_engine_stops_at_daily_when_daily_disagrees():
    weekly_up = _series_close([100.0] * 9 + [115.0])
    daily_flat = _series_close([100.0] * 21)
    engine = TheoryV2Engine()
    decision = engine.evaluate("BTC", weekly_up, daily_flat, weekly_up, weekly_up)
    assert decision.stage == "daily"
    assert decision.signal is None


def test_engine_fires_full_long_signal_through_execution_contract():
    """Smooth monotonic uptrend produces no climax, no swing extrema → all
    refinement gates pass and the engine fires a long signal."""
    weekly = _ohlc([100.0 + i for i in range(30)])
    daily = _ohlc([100.0 + i * 0.5 for i in range(40)])
    h4 = _ohlc([100.0 + i * 0.2 for i in range(30)])
    h1 = _ohlc([100.0 + i * 0.1 for i in range(30)])

    engine = TheoryV2Engine()
    decision = engine.evaluate("BTC", weekly, daily, h4, h1)

    assert decision.stage == "fired", decision.reason
    signal = decision.signal
    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.bias_timeframe == Timeframe.WEEKLY
    assert signal.setup_timeframe == Timeframe.H4
    assert signal.trigger_timeframe == Timeframe.H1
    assert signal.metadata["bias"] == "long"
    assert signal.invalidation < signal.metadata["entry_price"]
    assert signal.targets[0] > signal.metadata["entry_price"]

    plan = build_execution_plan(signal)
    assert plan is not None
    assert plan.coin == "BTC"
    assert plan.direction == Direction.LONG
    assert plan.risk_distance > 0


# --------------------------------------------------------------------------- #
# Iter 6 — ATR stop floor
# --------------------------------------------------------------------------- #


def test_daily_atr_basic_computation():
    df = _ohlc([100.0 + i for i in range(20)], spread=1.0)
    atr = daily_atr(df, window=14)
    assert atr is not None
    assert atr > 0


def test_one_h_entry_uses_atr_floor_when_wider_than_swing():
    # 1H structural risk is tiny: only 1 bar deviation, swing low ≈ entry.
    h1 = _ohlc([100.0] * 23 + [100.5])
    # Daily ATR forces a much wider stop (~2.0 with spread=1.0).
    daily = _ohlc([100.0 + i for i in range(20)], spread=1.0)
    result = one_h_entry(h1, "long", daily=daily, atr_floor_mult=1.5)
    assert result is not None
    entry, sl, tp = result
    # Risk must be the ATR floor, not the structural 1.5 distance.
    structural_risk = 100.5 - 99.5  # last 24 bar low is 99.5 (100 - 0.5)
    risk = entry - sl
    assert risk > structural_risk


def test_one_h_entry_keeps_structural_when_wider_than_atr():
    h1 = _ohlc([100.0] * 23 + [100.5])  # tiny structural
    daily = _ohlc([100.0 + i * 0.01 for i in range(20)], spread=0.01)  # tiny ATR
    result = one_h_entry(h1, "long", daily=daily, atr_floor_mult=1.5)
    assert result is not None
    entry, sl, _tp = result
    risk = entry - sl
    structural_risk = 100.5 - 99.5
    assert risk == pytest.approx(structural_risk)


# --------------------------------------------------------------------------- #
# Iter 4 — post-climax cooldown
# --------------------------------------------------------------------------- #


def test_climax_cooldown_inactive_on_quiet_series():
    df = _ohlc([100.0 + i * 0.1 for i in range(40)], spread=0.5)
    in_cd, bars_since = detect_climax_cooldown(df)
    assert in_cd is False
    assert bars_since is None


def test_climax_cooldown_fires_on_recent_spike():
    base = [100.0 + i * 0.1 for i in range(40)]
    df = _ohlc(base, spread=0.5)
    # Inject a giant spike on the very last bar.
    df.loc[df.index[-1], "high"] = 200.0
    df.loc[df.index[-1], "low"] = 90.0
    in_cd, bars_since = detect_climax_cooldown(df)
    assert in_cd is True
    assert bars_since == 0


def test_climax_cooldown_clears_after_window():
    base = [100.0 + i * 0.1 for i in range(60)]
    df = _ohlc(base, spread=0.5)
    # Climax 12 bars ago — outside the 10-bar cooldown window.
    spike_idx = df.index[-12]
    df.loc[spike_idx, "high"] = 200.0
    df.loc[spike_idx, "low"] = 90.0
    in_cd, _ = detect_climax_cooldown(df, cooldown_bars=10)
    assert in_cd is False


def test_engine_blocks_on_climax_cooldown():
    weekly = _ohlc([100.0 + i for i in range(30)])
    daily_base = [100.0 + i * 0.5 for i in range(40)]
    daily = _ohlc(daily_base, spread=0.5)
    daily.loc[daily.index[-1], "high"] = 250.0
    daily.loc[daily.index[-1], "low"] = 50.0
    h4 = _ohlc([100.0 + i * 0.2 for i in range(30)])
    h1 = _ohlc([100.0 + i * 0.1 for i in range(30)])
    decision = TheoryV2Engine().evaluate("BTC", weekly, daily, h4, h1)
    assert decision.stage == "climax_cooldown"
    assert decision.signal is None


# --------------------------------------------------------------------------- #
# Iter 5 — impulse-leg + chase prevention
# --------------------------------------------------------------------------- #


def test_find_impulse_leg_returns_none_on_monotonic():
    # No strict local extrema → no detected leg.
    df = _ohlc([100.0 + i for i in range(70)])
    assert find_impulse_leg(df) is None


def _zigzag_with_pullback(end_value: float) -> pd.DataFrame:
    """70-bar daily series with a strict swing low at i=29 and a strict swing
    high at i=49, then a configurable terminal pullback to ``end_value``.

    Steps are ≤2 per bar so no candle trips the climax gate.
    """
    values: list[float] = []
    for i in range(70):
        if i <= 14:
            values.append(100.0 + i * 0.5)             # 100 → 107
        elif i <= 29:
            values.append(107.0 - (i - 14) * 0.8)      # 107 → 95
        elif i <= 49:
            values.append(95.0 + (i - 29) * 2.0)       # 95  → 135
        else:
            # 20 bars from 135 → end_value
            values.append(135.0 - (i - 49) * (135.0 - end_value) / 20.0)
    return _ohlc(values, spread=0.3)


def test_find_impulse_leg_detects_swings_in_zigzag():
    df = _zigzag_with_pullback(end_value=115.0)
    leg = find_impulse_leg(df, lookback=60, swing_window=5)
    assert leg is not None
    low, high, low_idx, high_idx = leg
    # find_impulse_leg returns the low/high columns, not the close.
    assert low == pytest.approx(95.0 - 0.3)
    assert high == pytest.approx(135.0 + 0.3)
    assert low_idx < high_idx  # up-leg


def test_chase_gate_blocks_when_price_too_extended():
    # End at 133 → retrace = (135-133)/(135-95) = 5% → blocked.
    df = _zigzag_with_pullback(end_value=133.0)
    passes, retrace, reason = chase_gate(df, "long")
    assert passes is False
    assert retrace is not None and retrace < 0.5
    assert "chase gate" in reason


def test_chase_gate_passes_on_deep_retrace():
    # End at 113 → retrace = (135-113)/40 = 55% → passes.
    df = _zigzag_with_pullback(end_value=113.0)
    passes, retrace, _ = chase_gate(df, "long")
    assert passes is True
    assert retrace is not None and 0.50 <= retrace <= 0.95


# --------------------------------------------------------------------------- #
# TheoryV2Strategy wiring (engine → execution contract → fake client)
# --------------------------------------------------------------------------- #


class _FakeClient:
    """Minimal HyperliquidClient stand-in for strategy unit tests."""

    def __init__(self) -> None:
        self.opens: list[tuple[str, str, float]] = []
        self.closes: list[str] = []

    def get_open_positions(self) -> list[dict]:
        return []

    def market_open(self, coin: str, side: str, size_usd: float) -> dict:
        self.opens.append((coin, side, size_usd))
        return {"ok": True, "coin": coin, "side": side, "size_usd": size_usd}

    def market_close(self, coin: str) -> dict:
        self.closes.append(coin)
        return {"ok": True, "coin": coin}


def test_theory_v2_strategy_routes_signals_through_execution_contract(monkeypatch):
    from trading.strategy import TheoryV2Strategy
    from trading.theory_v2 import TheoryV2Decision, TheoryV2Engine

    # Build a single fired decision and patch the loader so the strategy
    # never touches data_loader during the unit test.
    weekly = _ohlc([100.0 + i for i in range(30)])
    daily = _ohlc([100.0 + i * 0.5 for i in range(40)])
    h4 = _ohlc([100.0 + i * 0.2 for i in range(30)])
    h1 = _ohlc([100.0 + i * 0.1 for i in range(30)])
    fired = TheoryV2Engine().evaluate("BTC", weekly, daily, h4, h1)
    assert fired.signal is not None  # sanity

    rejected = TheoryV2Decision(
        coin="ETH", bias="neutral", daily_confirmed=False, setup_valid=False,
        stage="weekly", reason="no weekly bias", signal=None,
    )

    def fake_build(coins):
        assert coins == ["BTC", "ETH"]
        return [fired.signal], [fired, rejected]

    monkeypatch.setattr(
        "trading.theory_v2.build_signals_for_coins", fake_build, raising=True
    )

    client = _FakeClient()
    strategy = TheoryV2Strategy(client, coins=["BTC", "ETH"], dry_run=False)

    signals = strategy.compute_signals()
    assert len(signals) == 1
    assert signals[0].coin == "BTC"

    strategy.execute_signals(signals)
    assert len(client.opens) == 1
    coin, side, size = client.opens[0]
    assert coin == "BTC"
    assert side == "long"
    assert size > 0


def test_theory_v2_strategy_drops_signals_failing_execution_contract(monkeypatch):
    """A signal missing the 4H/1H tags must be rejected, not opened."""
    from trading.strategy import TheoryV2Strategy
    from trading.signals import Direction, Signal

    bad = Signal(
        coin="BTC",
        direction=Direction.LONG,
        confidence=0.7,
        source="theory_v2",
        # missing setup_timeframe / trigger_timeframe / invalidation
    )

    monkeypatch.setattr(
        "trading.theory_v2.build_signals_for_coins",
        lambda coins: ([bad], []),
        raising=True,
    )

    client = _FakeClient()
    strategy = TheoryV2Strategy(client, coins=["BTC"], dry_run=False)
    strategy.execute_signals(strategy.compute_signals())
    assert client.opens == []  # contract violation → no order
