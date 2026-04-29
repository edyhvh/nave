from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from trading.crypto.client import HyperliquidClient
from trading.crypto.momentum import MomentumBacktester, MomentumSetupEngine, load_momentum_config
from trading.crypto.momentum.config import CadenceConfig


BINANCE_FAPI_URL = "https://fapi.binance.com"
SUPPORTED_TRIGGER_TIMEFRAMES = {"1h", "15m"}


@dataclass(frozen=True)
class MomentumTimeframes:
    bias: str
    setup: str
    trigger: str


def build_cadence_policy(
    results: dict[str, dict[str, Any]],
    *,
    base_threshold: int,
    cadence: CadenceConfig,
) -> dict[str, Any]:
    confirmed_setups = 0
    confirmed_symbols: set[str] = set()
    tradeable_at_base = 0
    tradeable_symbols: set[str] = set()
    top_score = 0

    for symbol, entry in results.items():
        for plan in entry.get("plans", []):
            score = int(plan.get("confidence_score", 0) or 0)
            top_score = max(top_score, score)
            if plan.get("setup_status") == "confirmed":
                confirmed_setups += 1
                confirmed_symbols.add(symbol)
            if plan.get("tradeable") and score >= base_threshold:
                tradeable_at_base += 1
                tradeable_symbols.add(symbol)

    target_trade_count_range = [0, cadence.baseline_trades_per_month]
    recommended_threshold = base_threshold
    state = "normal"
    note = "Stay selective: keep the base threshold until breadth expands across symbols and confirmed setups."

    if (
        confirmed_setups >= cadence.expansion_min_confirmed
        and tradeable_at_base >= cadence.expansion_min_tradeable
        and len(tradeable_symbols) >= cadence.expansion_min_symbols
    ):
        state = "expansion"
        recommended_threshold = max(cadence.min_score_floor, base_threshold - cadence.expansion_threshold_buffer)
        target_trade_count_range = [cadence.baseline_trades_per_month, cadence.expansion_trades_per_month]
        note = "Breadth and quality are both elevated; allow more trades if they keep clearing the recommended threshold."
    elif confirmed_setups <= 1 and tradeable_at_base == 0:
        state = "quiet"
        recommended_threshold = min(99, base_threshold + cadence.quiet_threshold_buffer)
        note = "Momentum breadth is thin; tighten selection and avoid forcing activity."

    return {
        "state": state,
        "base_threshold": base_threshold,
        "recommended_threshold": recommended_threshold,
        "target_trade_count_range": target_trade_count_range,
        "baseline_trades_per_month": cadence.baseline_trades_per_month,
        "breadth": {
            "confirmed_setups": confirmed_setups,
            "tradeable_at_base_threshold": tradeable_at_base,
            "symbols_with_confirmed": len(confirmed_symbols),
            "symbols_with_tradeable": len(tradeable_symbols),
            "top_score": top_score,
        },
        "note": note,
    }


def _filter_tradeable_plans(
    results: dict[str, dict[str, Any]],
    *,
    threshold: int,
) -> tuple[dict[str, dict[str, Any]], list[str], int]:
    tradeable_symbols: list[str] = []
    tradeable_count = 0
    filtered: dict[str, dict[str, Any]] = {}
    for symbol, entry in results.items():
        plans = entry.get("plans", [])
        tradeable = [plan for plan in plans if plan.get("tradeable") and int(plan.get("confidence_score", 0) or 0) >= threshold]
        if tradeable:
            tradeable_symbols.append(symbol)
        tradeable_count += len(tradeable)
        filtered[symbol] = {
            **entry,
            "tradeable": tradeable,
        }
    return filtered, tradeable_symbols, tradeable_count


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
        apply_cadence_policy: bool = False,
    ) -> dict[str, Any]:
        plans_by_symbol: dict[str, dict[str, Any]] = {}
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
            confirmed_count += sum(1 for plan in serialized if plan["setup_status"] == "confirmed")
            plans_by_symbol[symbol] = {
                "plans": serialized,
                "tradeable": [],
                "market_data": {
                    "funding_rate": frames.get("funding_rate"),
                    "open_interest_points": len(frames.get("open_interest") or []),
                },
            }
        cadence_policy = build_cadence_policy(
            plans_by_symbol,
            base_threshold=threshold,
            cadence=self.config.cadence,
        )
        effective_threshold = cadence_policy["recommended_threshold"] if apply_cadence_policy else threshold
        results_out, tradeable_symbols, tradeable_count = _filter_tradeable_plans(
            plans_by_symbol,
            threshold=effective_threshold,
        )
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
                "tradeable_count": tradeable_count,
                "confirmed_count": confirmed_count,
                "symbols_with_tradeable": tradeable_symbols,
                "score_threshold": threshold,
                "effective_score_threshold": effective_threshold,
                "recommended_score_threshold": cadence_policy["recommended_threshold"],
                "cadence_state": cadence_policy["state"],
                "cadence_policy_applied": apply_cadence_policy,
            },
            "cadence": {
                **cadence_policy,
                "applied": apply_cadence_policy,
                "effective_threshold": effective_threshold,
            },
            "results": results_out,
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