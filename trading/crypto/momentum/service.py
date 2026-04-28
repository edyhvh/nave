from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from trading.crypto.client import HyperliquidClient
from trading.crypto.momentum import MomentumBacktester, MomentumSetupEngine, load_momentum_config


BINANCE_FAPI_URL = "https://fapi.binance.com"
SUPPORTED_TRIGGER_TIMEFRAMES = {"1h", "15m"}


@dataclass(frozen=True)
class MomentumTimeframes:
    bias: str
    setup: str
    trigger: str


class MomentumMarketService:
    def __init__(
        self,
        *,
        market_client: HyperliquidClient | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.market_client = market_client or HyperliquidClient(wallet_name=None, testnet=False)
        self.session = session or requests.Session()
        self.config = load_momentum_config()
        self.engine = MomentumSetupEngine(self.config)
        self.backtester = MomentumBacktester(self.config)

    def scan_live(
        self,
        *,
        symbols: list[str],
        timeframes: MomentumTimeframes,
        account_equity: float = 10000.0,
        risk_pct: float | None = None,
        score_threshold: int | None = None,
    ) -> dict[str, Any]:
        plans_by_symbol: dict[str, dict[str, Any]] = {}
        tradeable_symbols: list[str] = []
        confirmed_count = 0
        threshold = score_threshold or self.config.score_tradeable_threshold
        for symbol in symbols:
            frames = self.load_live_frames(symbol, timeframes)
            plans = self.engine.evaluate_symbol(
                symbol=symbol,
                daily_frame=frames["daily"],
                setup_frame=frames["setup"],
                trigger_frame=frames["trigger"],
                open_interest=frames.get("open_interest"),
                funding_rate=frames.get("funding_rate"),
                account_equity=account_equity,
                risk_pct=risk_pct or self.config.risk.default_risk_pct,
            )
            serialized = [plan.to_dict() for plan in sorted(plans, key=lambda item: (-int(item.tradeable), -item.confidence_score))]
            tradeable = [plan for plan in serialized if plan["tradeable"] and plan["confidence_score"] >= threshold]
            confirmed_count += sum(1 for plan in serialized if plan["setup_status"] == "confirmed")
            if tradeable:
                tradeable_symbols.append(symbol)
            plans_by_symbol[symbol] = {
                "plans": serialized,
                "tradeable": tradeable,
                "market_data": {
                    "funding_rate": frames.get("funding_rate"),
                    "open_interest_points": len(frames.get("open_interest") or []),
                },
            }
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strategy": "derivatives_momentum_v1",
            "symbols": symbols,
            "timeframes": {
                "bias": timeframes.bias,
                "setup": timeframes.setup,
                "trigger": timeframes.trigger,
            },
            "summary": {
                "tradeable_count": sum(len(entry["tradeable"]) for entry in plans_by_symbol.values()),
                "confirmed_count": confirmed_count,
                "symbols_with_tradeable": tradeable_symbols,
                "score_threshold": threshold,
            },
            "results": plans_by_symbol,
        }

    def playbook_live(
        self,
        *,
        symbol: str,
        side: str,
        timeframes: MomentumTimeframes,
        account_equity: float = 10000.0,
        risk_pct: float | None = None,
        score_threshold: int | None = None,
    ) -> dict[str, Any]:
        frames = self.load_live_frames(symbol, timeframes)
        plans = self.engine.evaluate_symbol(
            symbol=symbol,
            daily_frame=frames["daily"],
            setup_frame=frames["setup"],
            trigger_frame=frames["trigger"],
            open_interest=frames.get("open_interest"),
            funding_rate=frames.get("funding_rate"),
            account_equity=account_equity,
            risk_pct=risk_pct or self.config.risk.default_risk_pct,
            side=side,
        )
        plan = plans[0]
        threshold = score_threshold or self.config.score_tradeable_threshold
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strategy": "derivatives_momentum_v1",
            "symbol": symbol,
            "requested_side": side,
            "timeframes": {
                "bias": timeframes.bias,
                "setup": timeframes.setup,
                "trigger": timeframes.trigger,
            },
            "score_threshold": threshold,
            "market_data": {
                "funding_rate": frames.get("funding_rate"),
                "open_interest_points": len(frames.get("open_interest") or []),
            },
            "plan": plan.to_dict(),
            "tradeable_under_threshold": bool(plan.tradeable and plan.confidence_score >= threshold),
        }

    def backtest_live(
        self,
        *,
        symbols: list[str],
        timeframes: MomentumTimeframes,
        lookback_days: int = 180,
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for symbol in symbols:
            frames = self.load_historical_frames(symbol, timeframes, lookback_days=lookback_days)
            results[symbol] = self.backtester.evaluate(
                symbol=symbol,
                daily_frame=frames["daily"],
                setup_frame=frames["setup"],
                trigger_frame=frames["trigger"],
                funding_rate=frames.get("funding_rate"),
                open_interest=frames.get("open_interest"),
            )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strategy": "derivatives_momentum_v1",
            "lookback_days": lookback_days,
            "timeframes": {
                "bias": timeframes.bias,
                "setup": timeframes.setup,
                "trigger": timeframes.trigger,
            },
            "results": results,
        }

    def load_live_frames(self, symbol: str, timeframes: MomentumTimeframes) -> dict[str, Any]:
        return self.load_historical_frames(symbol, timeframes, lookback_days=120)

    def load_historical_frames(
        self,
        symbol: str,
        timeframes: MomentumTimeframes,
        *,
        lookback_days: int,
    ) -> dict[str, Any]:
        coin = self._to_coin(symbol)
        now = datetime.now(timezone.utc)
        bias_start = now - timedelta(days=max(lookback_days, 120))
        setup_start = now - timedelta(days=max(lookback_days, 90))
        trigger_start = now - timedelta(days=max(lookback_days, 45))
        frames: dict[str, Any] = {
            "daily": self._candles_to_frame(
                self.market_client.get_historical_candles(
                    coin=coin,
                    interval=timeframes.bias,
                    start_time_ms=int(bias_start.timestamp() * 1000),
                    end_time_ms=int(now.timestamp() * 1000),
                    max_pages=32,
                    throttle_seconds=0,
                )
            ),
            "setup": self._candles_to_frame(
                self.market_client.get_historical_candles(
                    coin=coin,
                    interval=timeframes.setup,
                    start_time_ms=int(setup_start.timestamp() * 1000),
                    end_time_ms=int(now.timestamp() * 1000),
                    max_pages=64,
                    throttle_seconds=0,
                )
            ),
            "trigger": self._candles_to_frame(
                self.market_client.get_historical_candles(
                    coin=coin,
                    interval=timeframes.trigger,
                    start_time_ms=int(trigger_start.timestamp() * 1000),
                    end_time_ms=int(now.timestamp() * 1000),
                    max_pages=128,
                    throttle_seconds=0,
                )
            ),
        }
        try:
            frames["funding_rate"] = self.fetch_funding_rate(symbol)
        except requests.RequestException:
            frames["funding_rate"] = None
        try:
            frames["open_interest"] = self.fetch_open_interest_history(symbol, timeframes.setup)
        except requests.RequestException:
            frames["open_interest"] = None
        return frames

    def fetch_funding_rate(self, symbol: str) -> float | None:
        response = self.session.get(
            f"{BINANCE_FAPI_URL}/fapi/v1/premiumIndex",
            params={"symbol": self._to_binance_symbol(symbol)},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        value = payload.get("lastFundingRate")
        return float(value) if value is not None else None

    def fetch_open_interest_history(self, symbol: str, period: str) -> pd.DataFrame | None:
        binance_period = "4h" if period == "4h" else "1h"
        response = self.session.get(
            f"{BINANCE_FAPI_URL}/futures/data/openInterestHist",
            params={
                "symbol": self._to_binance_symbol(symbol),
                "period": binance_period,
                "limit": 30,
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            return None
        return pd.DataFrame(
            {
                "timestamp": [pd.to_datetime(entry["timestamp"], unit="ms", utc=True) for entry in payload],
                "open_interest": [float(entry["sumOpenInterest"]) for entry in payload],
            }
        )

    def parse_symbols(self, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            raw = value.replace(" ", ",").split(",")
        else:
            raw = [str(item) for item in value]
        symbols = []
        for item in raw:
            symbol = item.strip().upper()
            if not symbol:
                continue
            symbols.append(self._to_binance_symbol(symbol))
        return sorted(set(symbols or ["BTCUSDT", "ETHUSDT"]))

    def parse_timeframes(self, tf: str = "4h,1h") -> MomentumTimeframes:
        raw = [part.strip().lower() for part in tf.split(",") if part.strip()]
        if len(raw) != 2:
            raise ValueError("tf must have setup and trigger parts, e.g. '4h,1h'")
        setup, trigger = raw
        if setup != "4h":
            raise ValueError("setup timeframe must be 4h for the momentum engine")
        if trigger not in SUPPORTED_TRIGGER_TIMEFRAMES:
            raise ValueError("trigger timeframe must be 1h or 15m")
        return MomentumTimeframes(bias="1d", setup=setup, trigger=trigger)

    @staticmethod
    def _to_coin(symbol: str) -> str:
        normalized = symbol.upper().replace("USDT", "")
        return normalized

    @staticmethod
    def _to_binance_symbol(symbol: str) -> str:
        normalized = symbol.upper()
        return normalized if normalized.endswith("USDT") else f"{normalized}USDT"

    @staticmethod
    def _candles_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise ValueError("historical candle request returned no rows")
        keep = ["timestamp", "open", "high", "low", "close", "volume"]
        frame = frame[keep].copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        for column in keep[1:]:
            frame[column] = frame[column].astype(float)
        return frame