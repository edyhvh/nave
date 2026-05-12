"""Deribit options chain fetcher with normalization and liquidity filters."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from core.logger import configure_logger
from options.config import OptionsConfig
from options.exceptions import OptionsDataError
from options.fetchers.yfinance_fetcher import FetchedOptionChain

logger = configure_logger(__name__)


@dataclass(frozen=True)
class _DeribitMarketBundle:
    instruments: list[dict[str, Any]]
    summaries: list[dict[str, Any]]
    underlying_price: float


class DeribitOptionsFetcher:
    """Fetch options chains from Deribit REST API and normalize output rows."""

    def __init__(self, config: OptionsConfig):
        self.config = config
        self._base_url = config.deribit_base_url.rstrip("/")
        self._timeout = max(3, int(config.deribit_timeout_seconds))
        self._session = requests.Session()

    def fetch_chain(self, ticker: str) -> FetchedOptionChain:
        currency = self._normalize_currency(ticker)

        for attempt in range(1, self.config.max_retries + 1):
            try:
                return self._fetch_chain_once(currency)
            except OptionsDataError:
                raise
            except Exception as exc:  # noqa: BLE001
                if attempt >= self.config.max_retries:
                    raise OptionsDataError(
                        f"Failed to fetch Deribit option chain for {currency}: {exc}"
                    ) from exc
                sleep_for = self.config.retry_backoff_seconds * attempt
                logger.warning(
                    "deribit fetch attempt %d/%d failed for %s (%s); retrying in %.1fs",
                    attempt,
                    self.config.max_retries,
                    currency,
                    exc,
                    sleep_for,
                )
                time.sleep(sleep_for)

        raise OptionsDataError(f"Unexpected Deribit fetch flow for {currency}")

    def _fetch_chain_once(self, currency: str) -> FetchedOptionChain:
        bundle = self._fetch_market_bundle(currency)
        instrument_by_name = {
            str(item.get("instrument_name")): item
            for item in bundle.instruments
            if item.get("instrument_name")
        }

        rows: list[dict[str, Any]] = []
        expirations: set[str] = set()
        for summary in bundle.summaries:
            instrument_name = str(summary.get("instrument_name") or "").strip()
            instrument = instrument_by_name.get(instrument_name)
            if instrument is None:
                continue

            row = self._build_row(
                currency=currency,
                instrument_name=instrument_name,
                instrument=instrument,
                summary=summary,
                underlying_price=bundle.underlying_price,
            )
            if row is None:
                continue
            rows.append(row)
            expirations.add(str(row["expiration"]))

        if not rows:
            raise OptionsDataError(
                f"No option contracts were normalized from Deribit for {currency}"
            )

        frame = pd.DataFrame(rows)
        frame = frame.dropna(subset=["strike", "implied_volatility"])
        filtered = self._filter_liquidity(frame)
        if filtered.empty:
            raise OptionsDataError(
                f"No contracts passed liquidity filters for Deribit {currency}"
            )

        return FetchedOptionChain(
            ticker=currency,
            underlying_price=bundle.underlying_price,
            expirations=sorted(expirations),
            frame=filtered,
        )

    def _fetch_market_bundle(self, currency: str) -> _DeribitMarketBundle:
        instruments = self._http_get(
            method="public/get_instruments",
            params={"currency": currency,
                    "kind": "option", "expired": "false"},
        )
        if not isinstance(instruments, list) or not instruments:
            raise OptionsDataError(
                f"No active Deribit option instruments found for {currency}")

        summaries = self._http_get(
            method="public/get_book_summary_by_currency",
            params={"currency": currency, "kind": "option"},
        )
        if not isinstance(summaries, list) or not summaries:
            raise OptionsDataError(
                f"No Deribit option market summaries found for {currency}")

        underlying_price = self._resolve_underlying_price(currency, summaries)
        if underlying_price <= 0:
            raise OptionsDataError(
                f"Unable to resolve Deribit underlying price for {currency}")

        return _DeribitMarketBundle(
            instruments=instruments,
            summaries=summaries,
            underlying_price=underlying_price,
        )

    def _resolve_underlying_price(self, currency: str, summaries: list[dict[str, Any]]) -> float:
        index_result = self._http_get(
            method="public/get_index_price",
            params={"index_name": f"{currency.lower()}_usd"},
        )
        index_price = self._as_float((index_result or {}).get("index_price"))
        if index_price is not None and index_price > 0:
            return index_price

        prices = [
            self._as_float(item.get("underlying_price"))
            for item in summaries
            if self._as_float(item.get("underlying_price")) not in (None, 0.0)
        ]
        if prices:
            return float(pd.Series(prices, dtype=float).median())

        return 0.0

    def _build_row(
        self,
        *,
        currency: str,
        instrument_name: str,
        instrument: dict[str, Any],
        summary: dict[str, Any],
        underlying_price: float,
    ) -> dict[str, Any] | None:
        expiration = self._expiration_from_instrument(instrument)
        strike = self._as_float(instrument.get("strike"))
        option_type = self._option_type_from_instrument(
            instrument_name, instrument)

        if expiration is None or strike is None or option_type not in {"call", "put"}:
            return None

        bid = self._as_float(summary.get("bid_price"))
        ask = self._as_float(summary.get("ask_price"))
        mark = self._as_float(summary.get("mark_price"))
        last = self._as_float(summary.get("last"))
        mid = self._mid_price(bid=bid, ask=ask, mark=mark, last=last)
        if mid <= 0:
            return None

        implied_vol = self._implied_volatility(summary)
        if implied_vol is None or implied_vol <= 0:
            return None

        volume = self._as_float(summary.get("volume"))
        if volume is None:
            volume = self._as_float((summary.get("stats") or {}).get("volume"))
        open_interest = self._as_float(summary.get("open_interest")) or 0.0

        spread_pct = 1.0
        if bid is not None and ask is not None and mid > 0:
            spread_pct = max(0.0, (ask - bid) / mid)

        in_the_money = (
            (option_type == "call" and underlying_price > strike)
            or (option_type == "put" and underlying_price < strike)
        )

        return {
            "ticker": currency,
            "contract_symbol": instrument_name,
            "option_type": option_type,
            "expiration": expiration,
            "strike": float(strike),
            "last_price": float(last if last is not None else mark if mark is not None else mid),
            "bid": float(bid if bid is not None else max(mid * 0.99, 0.0)),
            "ask": float(ask if ask is not None else mid * 1.01),
            "mid_price": float(mid),
            "volume": float(volume if volume is not None else 0.0),
            "open_interest": float(open_interest),
            "implied_volatility": float(implied_vol),
            "in_the_money": bool(in_the_money),
            "last_trade_date": None,
            "spread_pct": float(spread_pct),
            "liquidity_score": float(
                (volume if volume is not None else 0.0)
                + 0.5 * open_interest
                - 100.0 * spread_pct
            ),
        }

    def _filter_liquidity(self, frame: pd.DataFrame) -> pd.DataFrame:
        baseline = frame[
            (frame["volume"] >= self.config.min_volume)
            & (frame["open_interest"] >= self.config.min_open_interest)
            & (frame["spread_pct"] <= self.config.max_bid_ask_spread_pct)
            & (frame["mid_price"] > 0.0)
        ].copy()

        if not baseline.empty:
            return baseline.sort_values(
                ["expiration", "liquidity_score"],
                ascending=[True, False],
            ).reset_index(drop=True)

        logger.warning(
            "deribit strict liquidity filter returned no rows; applying relaxed fallback"
        )
        relaxed = frame[
            (frame["mid_price"] > 0.0)
            & (frame["implied_volatility"] > 0.0)
            & (frame["open_interest"] > 0.0)
        ].copy()
        return relaxed.sort_values(
            ["expiration", "liquidity_score"],
            ascending=[True, False],
        ).reset_index(drop=True)

    def _http_get(self, *, method: str, params: dict[str, Any]) -> Any:
        url = f"{self._base_url}/{method}"
        try:
            response = self._session.get(
                url, params=params, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise OptionsDataError(
                f"Deribit request failed for {method}: {exc}") from exc
        except ValueError as exc:
            raise OptionsDataError(
                f"Invalid JSON response from Deribit {method}") from exc

        if "error" in payload and payload["error"]:
            raise OptionsDataError(
                f"Deribit API error for {method}: {payload['error']}")

        return payload.get("result")

    def _normalize_currency(self, ticker: str) -> str:
        value = str(ticker).strip().upper()
        if not value:
            raise OptionsDataError("ticker must be a non-empty symbol")

        if value in {"BTC", "BTC-USD", "BTCUSDT", "XBT"}:
            return "BTC"
        if value in {"ETH", "ETH-USD", "ETHUSDT"}:
            return "ETH"

        raise OptionsDataError(
            "Deribit options source currently supports BTC and ETH symbols only"
        )

    def _expiration_from_instrument(self, instrument: dict[str, Any]) -> str | None:
        timestamp = self._as_float(instrument.get("expiration_timestamp"))
        if timestamp is None:
            return None
        dt = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)
        return dt.date().isoformat()

    def _option_type_from_instrument(
        self,
        instrument_name: str,
        instrument: dict[str, Any],
    ) -> str | None:
        option_type = str(instrument.get("option_type") or "").strip().lower()
        if option_type in {"call", "put"}:
            return option_type

        suffix = instrument_name.rsplit("-", maxsplit=1)[-1].upper()
        if suffix == "C":
            return "call"
        if suffix == "P":
            return "put"
        return None

    def _implied_volatility(self, summary: dict[str, Any]) -> float | None:
        mark_iv = self._as_float(summary.get("mark_iv"))
        if mark_iv is not None and mark_iv > 0:
            return mark_iv / 100.0 if mark_iv > 2 else mark_iv

        bid_iv = self._as_float(summary.get("bid_iv"))
        ask_iv = self._as_float(summary.get("ask_iv"))
        iv_points = [value for value in (
            bid_iv, ask_iv) if value is not None and value > 0]
        if not iv_points:
            return None

        iv = sum(iv_points) / len(iv_points)
        return iv / 100.0 if iv > 2 else iv

    def _mid_price(
        self,
        *,
        bid: float | None,
        ask: float | None,
        mark: float | None,
        last: float | None,
    ) -> float:
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        if mark is not None and mark > 0:
            return mark
        if last is not None and last > 0:
            return last
        return 0.0

    def _as_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
