from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from trading.crypto.analysis.regime import assess_regime
from trading.crypto.analysis.regime_config import load_regime_config


def _frame(closes: list[float], freq: str = "D") -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.02 for c in closes],
            "low": [c * 0.98 for c in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=idx,
    )


def test_bull_leg_up_when_cot_long_and_rally():
    daily = _frame([60_000.0] * 8 + list(range(60_000, 75_000, 1500)))
    setup = _frame(list(range(70_000, 76_000, 200)), freq="4h")
    cot = MagicMock(
        bias="bullish",
        confidence=0.7,
        historical_percentile=92,
    )
    result = assess_regime(daily=daily, setup=setup, cot_bias=cot, best_plan=None)
    assert result.bias == "bullish"
    assert result.phase in {"leg_up", "cot_bull_bias", "pullback_buy", "continuation_long"}