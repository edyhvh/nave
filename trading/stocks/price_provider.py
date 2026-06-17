"""Stock daily price helpers for ISM short backtests."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol

import pandas as pd


class PriceProviderLike(Protocol):
    def fetch_daily_closes(
        self,
        symbols: list[str],
        *,
        start: date,
        end: date,
    ) -> dict[str, pd.Series]:
        ...


class YFinancePriceProvider:
    """Fetch adjusted daily closes via yfinance (research proxy for Ondo perps)."""

    def fetch_daily_closes(
        self,
        symbols: list[str],
        *,
        start: date,
        end: date,
    ) -> dict[str, pd.Series]:
        import yfinance as yf

        if not symbols:
            return {}
        start_s = start.isoformat()
        end_s = end.isoformat()
        raw = yf.download(
            tickers=" ".join(symbols),
            start=start_s,
            end=end_s,
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
        out: dict[str, pd.Series] = {}
        if raw.empty:
            return out
        if len(symbols) == 1:
            symbol = symbols[0]
            closes = _extract_close_series(raw, symbol)
            if not closes.empty:
                out[symbol] = closes.astype(float)
            return out
        for symbol in symbols:
            if symbol not in raw.columns.get_level_values(0):
                continue
            closes = _extract_close_series(raw, symbol)
            if not closes.empty:
                out[symbol] = closes.astype(float)
        return out


class StaticPriceProvider:
    """Injected closes for offline tests."""

    def __init__(self, prices: dict[str, pd.Series]):
        self._prices = {symbol.upper(): series.astype(float) for symbol, series in prices.items()}

    def fetch_daily_closes(
        self,
        symbols: list[str],
        *,
        start: date,
        end: date,
    ) -> dict[str, pd.Series]:
        start_ts = pd.Timestamp(start, tz="UTC")
        end_ts = pd.Timestamp(end, tz="UTC")
        out: dict[str, pd.Series] = {}
        for symbol in symbols:
            series = self._prices.get(symbol.upper())
            if series is None:
                continue
            normalized = series.copy()
            if normalized.index.tz is None:
                normalized.index = normalized.index.tz_localize("UTC")
            else:
                normalized.index = normalized.index.tz_convert("UTC")
            window = normalized.loc[(normalized.index >= start_ts) & (normalized.index <= end_ts)]
            if not window.empty:
                out[symbol.upper()] = window
        return out


def price_on_or_before(series: pd.Series, as_of: date) -> float | None:
    if series.empty:
        return None
    ts = pd.Timestamp(as_of, tz="UTC")
    normalized = series.copy()
    if normalized.index.tz is None:
        normalized.index = normalized.index.tz_localize("UTC")
    else:
        normalized.index = normalized.index.tz_convert("UTC")
    eligible = normalized.loc[normalized.index <= ts]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1])


def _extract_close_series(raw: pd.DataFrame, symbol: str) -> pd.Series:
    """Handle yfinance single-index and ticker-grouped MultiIndex outputs."""
    if isinstance(raw.columns, pd.MultiIndex):
        if symbol in raw.columns.get_level_values(0):
            frame = raw[symbol]
            if "Close" in frame.columns:
                return frame["Close"].dropna()
        if "Close" in raw.columns.get_level_values(0):
            close_block = raw["Close"]
            if isinstance(close_block, pd.DataFrame) and symbol in close_block.columns:
                return close_block[symbol].dropna()
            if isinstance(close_block, pd.Series):
                return close_block.dropna()
        return pd.Series(dtype=float)
    if "Close" in raw.columns:
        return raw["Close"].dropna()
    return pd.Series(dtype=float)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()
