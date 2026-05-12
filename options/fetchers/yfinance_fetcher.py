"""Yahoo Finance options chain fetcher with normalization and liquidity filters."""

from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd
try:
    import yfinance as yf
except Exception:  # noqa: BLE001
    yf = None

from core.logger import configure_logger
from options.config import OptionsConfig
from options.exceptions import OptionsDataError

logger = configure_logger(__name__)

_REQUIRED_COLUMNS = {
    "contractSymbol",
    "strike",
    "lastPrice",
    "bid",
    "ask",
    "volume",
    "openInterest",
    "impliedVolatility",
    "inTheMoney",
    "lastTradeDate",
}


@dataclass(frozen=True)
class FetchedOptionChain:
    """Raw normalized option chain result."""

    ticker: str
    underlying_price: float
    expirations: list[str]
    frame: pd.DataFrame


class YFinanceOptionsFetcher:
    """Fetches full option chains and applies baseline quality filters."""

    def __init__(self, config: OptionsConfig):
        self.config = config
        if yf is None:
            raise OptionsDataError(
                "yfinance is not installed. Install dependency 'yfinance' to fetch option chains."
            )

    def fetch_chain(self, ticker: str) -> FetchedOptionChain:
        symbol = ticker.upper().strip()
        if not symbol:
            raise OptionsDataError("ticker must be a non-empty string")

        for attempt in range(1, self.config.max_retries + 1):
            try:
                return self._fetch_chain_once(symbol)
            except Exception as exc:  # noqa: BLE001 - yfinance can throw mixed errors.
                if attempt >= self.config.max_retries:
                    raise OptionsDataError(
                        f"Failed to fetch option chain for {symbol}: {exc}") from exc
                sleep_for = self.config.retry_backoff_seconds * attempt
                logger.warning(
                    "yfinance fetch attempt %d/%d failed for %s (%s); retrying in %.1fs",
                    attempt,
                    self.config.max_retries,
                    symbol,
                    exc,
                    sleep_for,
                )
                time.sleep(sleep_for)

        raise OptionsDataError(f"Unexpected fetch flow for {symbol}")

    def _fetch_chain_once(self, ticker: str) -> FetchedOptionChain:
        if yf is None:
            raise OptionsDataError("yfinance module is unavailable")
        tk = yf.Ticker(ticker)
        expirations = list(tk.options)
        if not expirations:
            raise OptionsDataError(
                f"No options expirations available for {ticker}")

        history = tk.history(period="1d", interval="1m")
        if history.empty:
            history = tk.history(period="5d", interval="1d")
        if history.empty:
            raise OptionsDataError(f"No price history available for {ticker}")

        underlying_price = float(history["Close"].dropna().iloc[-1])
        frames: list[pd.DataFrame] = []
        for expiration in expirations:
            chain = tk.option_chain(expiration)
            calls = self._normalize_side(
                chain.calls, ticker=ticker, expiration=expiration, option_type="call")
            puts = self._normalize_side(
                chain.puts, ticker=ticker, expiration=expiration, option_type="put")
            if not calls.empty:
                frames.append(calls)
            if not puts.empty:
                frames.append(puts)

        if not frames:
            raise OptionsDataError(
                f"No option contracts returned for {ticker}")

        merged = pd.concat(frames, ignore_index=True)
        filtered = self._filter_liquidity(merged)
        if filtered.empty:
            raise OptionsDataError(
                f"No contracts passed liquidity filters for {ticker}")

        return FetchedOptionChain(
            ticker=ticker,
            underlying_price=underlying_price,
            expirations=expirations,
            frame=filtered,
        )

    def _normalize_side(
        self,
        frame: pd.DataFrame,
        *,
        ticker: str,
        expiration: str,
        option_type: str,
    ) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame()
        missing = _REQUIRED_COLUMNS.difference(frame.columns)
        if missing:
            raise OptionsDataError(
                f"Missing expected option chain columns for {ticker}: {sorted(missing)}")

        subset = frame.copy()
        subset["ticker"] = ticker
        subset["option_type"] = option_type
        subset["expiration"] = expiration
        subset["lastTradeDate"] = subset["lastTradeDate"].astype("string")

        numeric_cols = ["strike", "lastPrice", "bid", "ask",
                        "volume", "openInterest", "impliedVolatility"]
        for col in numeric_cols:
            subset[col] = pd.to_numeric(subset[col], errors="coerce")

        subset["mid_price"] = (subset["bid"].fillna(
            0.0) + subset["ask"].fillna(0.0)) / 2.0
        subset["spread_pct"] = 1.0
        valid_mid = subset["mid_price"] > 0.0
        subset.loc[valid_mid, "spread_pct"] = (
            (subset.loc[valid_mid, "ask"] -
             subset.loc[valid_mid, "bid"]).clip(lower=0.0)
            / subset.loc[valid_mid, "mid_price"]
        )
        subset["liquidity_score"] = (
            subset["volume"].fillna(0.0)
            + 0.5 * subset["openInterest"].fillna(0.0)
            - 100.0 * subset["spread_pct"].fillna(1.0)
        )

        renamed = subset.rename(
            columns={
                "contractSymbol": "contract_symbol",
                "lastPrice": "last_price",
                "openInterest": "open_interest",
                "impliedVolatility": "implied_volatility",
                "inTheMoney": "in_the_money",
                "lastTradeDate": "last_trade_date",
            }
        )
        selected = renamed[
            [
                "ticker",
                "contract_symbol",
                "option_type",
                "expiration",
                "strike",
                "last_price",
                "bid",
                "ask",
                "mid_price",
                "volume",
                "open_interest",
                "implied_volatility",
                "in_the_money",
                "last_trade_date",
                "spread_pct",
                "liquidity_score",
            ]
        ]
        return selected.dropna(subset=["strike", "implied_volatility"])

    def _filter_liquidity(self, frame: pd.DataFrame) -> pd.DataFrame:
        filtered = frame[
            (frame["volume"] >= self.config.min_volume)
            & (frame["open_interest"] >= self.config.min_open_interest)
            & (frame["spread_pct"] <= self.config.max_bid_ask_spread_pct)
            & (frame["mid_price"] > 0.0)
        ].copy()
        if filtered.empty:
            return filtered
        return filtered.sort_values(["expiration", "liquidity_score"], ascending=[True, False]).reset_index(drop=True)
