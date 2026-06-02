from __future__ import annotations

import pandas as pd

from trading.crypto.cot_gate import load_cot_history_frame
from trading.crypto.momentum.config import CotOverlayConfig
from trading.crypto.momentum.cot_overlay import evaluate_cot_overlay


def _history(net_values: list[float], start: str = "2022-01-04") -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=len(net_values), freq="W-TUE", tz="UTC")
    return pd.DataFrame({"report_date": dates, "net_non_commercial": net_values})


def test_historical_mode_uses_permission_not_live_fetch(monkeypatch):
    history = _history([300] * 20 + [9_999])
    monkeypatch.setattr(
        "trading.crypto.cot.context.cot_history_for_coin",
        lambda _coin: history,
    )
    monkeypatch.setattr(
        "trading.crypto.cot.context.fetch_cot_biases",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("no live fetch in historical")),
    )
    as_of = history["report_date"].iloc[-1]
    result = evaluate_cot_overlay(
        side="short",
        symbol="BTCUSDT",
        config=CotOverlayConfig(),
        as_of=as_of,
        mode="historical",
    )
    assert result.passed is True
    assert result.aligned is True
    assert result.contrarian_bias == "bearish"