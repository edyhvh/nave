from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from trading.crypto.analysis.regime import assess_regime


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


def test_relief_rally_fade_when_cot_bearish_and_bounce_into_supply():
    # Leg down then bounce: lows ~80k, recovery toward 72k from 68k
    daily_closes = [95_000.0] * 10 + list(range(95_000, 68_000, -2_000)) + [70_000, 72_000, 71_500]
    setup_closes = daily_closes[-30:]
    daily = _frame(daily_closes)
    setup = _frame(setup_closes, freq="4h")

    cot = MagicMock(bias="bearish", confidence=0.7, historical_percentile=97)

    result = assess_regime(daily=daily, setup=setup, cot_bias=cot, best_plan=None)
    assert result.bias == "bearish"
    assert result.phase in {"relief_rally_fade", "leg_down", "cot_bear_bias", "breakdown_retest"}