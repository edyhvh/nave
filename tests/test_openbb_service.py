from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

from app.services import openbb


class _FakeObb:
    class economy:
        @staticmethod
        def fred_series(symbol: str):
            return pd.DataFrame({"date": ["2026-09-01"], "value": [4.75]})

    class equity:
        class price:
            @staticmethod
            def historical(**kwargs):
                assert kwargs["provider"] == "yfinance"
                return pd.DataFrame({"date": ["2026-09-01"], "close": [100.0]})

    class crypto:
        @staticmethod
        def price(symbol: str):
            return {"symbol": symbol, "price": 100.0}


def test_indicator_dispatches_fred_without_mock(monkeypatch):
    monkeypatch.setattr(openbb, "_get_obb", lambda: _FakeObb)
    payload = openbb.fetch_openbb_indicator("fed_balance_sheet")
    assert payload["series_id"] == "WALCL"
    assert payload["records"][0]["value"] == 4.75


def test_indicator_dispatches_yfinance_history(monkeypatch):
    monkeypatch.setattr(openbb, "_get_obb", lambda: _FakeObb)
    payload = openbb.fetch_openbb_indicator("xle_history")
    assert payload["symbol"] == "XLE"
    assert payload["records"][0]["close"] == 100.0


def test_yield_curve_fetches_both_real_series(monkeypatch):
    monkeypatch.setattr(openbb, "_get_obb", lambda: _FakeObb)
    payload = openbb.fetch_openbb_indicator("yield_curve_10y_2y")
    assert payload["long"]["records"][0]["value"] == 4.75
    assert payload["short"]["records"][0]["value"] == 4.75
