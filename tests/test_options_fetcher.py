from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from options.config import load_options_config
from options.fetchers import yfinance_fetcher
from options.fetchers.yfinance_fetcher import YFinanceOptionsFetcher


@dataclass(frozen=True)
class _FakeChain:
    calls: pd.DataFrame
    puts: pd.DataFrame


class _FakeTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.options = ["2099-12-15"]

    def history(self, period: str, interval: str) -> pd.DataFrame:
        _ = (period, interval)
        return pd.DataFrame({"Close": [418.0, 420.0]})

    def option_chain(self, expiration: str) -> _FakeChain:
        _ = expiration
        calls = pd.DataFrame(
            {
                "contractSymbol": ["MSFTC_good", "MSFTC_bad"],
                "strike": [420.0, 440.0],
                "lastPrice": [6.2, 2.0],
                "bid": [6.1, 1.0],
                "ask": [6.3, 3.5],
                "volume": [250, 10],
                "openInterest": [900, 20],
                "impliedVolatility": [0.24, 0.35],
                "inTheMoney": [False, False],
                "lastTradeDate": ["2026-05-10", "2026-05-10"],
            }
        )
        puts = pd.DataFrame(
            {
                "contractSymbol": ["MSFTP_good"],
                "strike": [415.0],
                "lastPrice": [5.8],
                "bid": [5.7],
                "ask": [5.9],
                "volume": [220],
                "openInterest": [880],
                "impliedVolatility": [0.27],
                "inTheMoney": [False],
                "lastTradeDate": ["2026-05-10"],
            }
        )
        return _FakeChain(calls=calls, puts=puts)


class _FakeYFModule:
    @staticmethod
    def Ticker(symbol: str) -> _FakeTicker:
        return _FakeTicker(symbol)


def _config(tmp_path: Path):
    _ = tmp_path
    return load_options_config()


def test_fetcher_fetch_chain_filters_liquidity(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(yfinance_fetcher, "yf", _FakeYFModule())
    fetcher = YFinanceOptionsFetcher(_config(tmp_path))

    result = fetcher.fetch_chain("MSFT")

    assert result.ticker == "MSFT"
    assert result.underlying_price == 420.0
    assert result.expirations == ["2099-12-15"]
    assert len(result.frame) == 2
    assert set(result.frame["contract_symbol"].tolist()) == {
        "MSFTC_good", "MSFTP_good"}
