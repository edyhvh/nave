"""Shared COT service layer for CLI, MCP, and backend API integrations."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from trading.client import HyperliquidClient
from trading.cot import (
    COTAnalyzer,
    COTHistoricalAnalyzer,
    COTPositionGenerator,
    COTReportGenerator,
    build_cot_sections_from_datasets,
    fetch_latest_cot,
)


class COTService:
    """Reusable COT application service with structured JSON payload outputs."""

    def __init__(self) -> None:
        self._analyzer = COTAnalyzer()
        self._history_analyzer = COTHistoricalAnalyzer()
        self._reporter = COTReportGenerator()
        self._position_generator = COTPositionGenerator(default_risk_pct=0.01)

    @staticmethod
    def _parse_coins(coins: str | list[str]) -> list[str]:
        if isinstance(coins, str):
            coin_list = [c.strip().upper() for c in coins.split() if c.strip()]
        else:
            coin_list = [str(c).strip().upper() for c in coins if str(c).strip()]
        return sorted(set(coin_list or ["BTC", "ETH"]))

    @staticmethod
    def _history_weeks_for_months(months: int) -> int:
        return max(16, months * 6 + 4)

    @staticmethod
    def _parse_date(value: str) -> date | None:
        try:
            if "T" in str(value):
                return datetime.fromisoformat(str(value)).date()
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return None

    def _compute_price_context(
        self,
        client: HyperliquidClient,
        coin: str,
        as_of_date: date | None,
    ) -> dict[str, object]:
        if as_of_date is None:
            return {
                "price_close": None,
                "weekly_price_delta_pct": None,
                "trend_4h": "unknown",
            }

        end_dt = datetime.combine(
            as_of_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
        )
        start_dt = end_dt - timedelta(days=14)
        end_ms = int(end_dt.timestamp() * 1000)
        start_ms = int(start_dt.timestamp() * 1000)

        daily = client.get_historical_candles(
            coin=coin,
            interval="1d",
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            max_pages=12,
            throttle_seconds=0,
        )
        by_day = [c for c in daily if c.get("timestamp")]
        by_day.sort(key=lambda x: x["timestamp_ms"])

        report_close = None
        for candle in by_day:
            cdate = candle["timestamp"].date()
            if cdate <= as_of_date:
                report_close = float(candle["close"])

        prev_week_target = as_of_date - timedelta(days=7)
        prev_week_close = None
        for candle in by_day:
            cdate = candle["timestamp"].date()
            if cdate <= prev_week_target:
                prev_week_close = float(candle["close"])

        weekly_delta = None
        if report_close and prev_week_close:
            weekly_delta = ((report_close - prev_week_close) / prev_week_close) * 100

        trend_4h = "unknown"
        four_h = client.get_historical_candles(
            coin=coin,
            interval="4h",
            start_time_ms=int((end_dt - timedelta(days=10)).timestamp() * 1000),
            end_time_ms=end_ms,
            max_pages=16,
            throttle_seconds=0,
        )
        if len(four_h) >= 8:
            first = float(four_h[0]["close"])
            last = float(four_h[-1]["close"])
            if last > first:
                trend_4h = "bullish"
            elif last < first:
                trend_4h = "bearish"
            else:
                trend_4h = "flat"

        return {
            "price_close": report_close,
            "weekly_price_delta_pct": weekly_delta,
            "trend_4h": trend_4h,
        }

    def _market_structure_4h(
        self,
        client: HyperliquidClient,
        coin: str,
        as_of_date: str,
    ) -> dict[str, Any]:
        as_of = datetime.fromisoformat(as_of_date).replace(tzinfo=timezone.utc)
        end_dt = as_of + timedelta(days=1)
        start_dt = end_dt - timedelta(days=10)
        candles = client.get_historical_candles(
            coin=coin,
            interval="4h",
            start_time_ms=int(start_dt.timestamp() * 1000),
            end_time_ms=int(end_dt.timestamp() * 1000),
            max_pages=32,
            throttle_seconds=0,
        )
        if not candles:
            return {
                "trend": "unknown",
                "price": 0.0,
                "swing_high": 0.0,
                "swing_low": 0.0,
                "atr": 1.0,
            }

        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        trend = "bullish" if closes[-1] >= closes[0] else "bearish"
        atr_window = list(zip(highs[-14:], lows[-14:]))
        atr = sum((high_val - low_val) for high_val, low_val in atr_window) / max(
            1, len(atr_window)
        )
        return {
            "trend": trend,
            "price": closes[-1],
            "swing_high": max(highs[-18:]),
            "swing_low": min(lows[-18:]),
            "atr": atr,
        }

    def get_latest_summary(
        self,
        *,
        coins: str | list[str] = "BTC ETH",
        report_type: str = "futures_and_options",
        include_micro: bool = False,
        debug: bool = False,
        include_price_context: bool = True,
    ) -> dict[str, Any]:
        coin_list = self._parse_coins(coins)
        primary_report_type = (
            "futures_only" if report_type == "futures_only" else "futures_and_options"
        )

        futures_only = fetch_latest_cot(
            report_type="futures_only",
            include_micro=include_micro,
            debug=debug,
        )
        combined = fetch_latest_cot(
            report_type="futures_and_options",
            include_micro=include_micro,
            debug=debug,
        )

        selected_data = futures_only if primary_report_type == "futures_only" else combined
        biases = self._analyzer.analyze(selected_data)
        sections = build_cot_sections_from_datasets(
            futures_only_data=futures_only,
            combined_data=combined,
        )

        price_client = HyperliquidClient(wallet_name=None, testnet=False)
        price_context: dict[str, dict[str, object]] = {}
        if include_price_context:
            for coin in coin_list:
                bias = biases.get(coin)
                if not bias:
                    continue
                as_of_raw = str(
                    bias.metadata.get("as_of_date", bias.metadata.get("report_date", ""))
                )
                as_of = self._parse_date(as_of_raw)
                try:
                    price_context[coin] = self._compute_price_context(price_client, coin, as_of)
                except Exception:
                    price_context[coin] = {
                        "price_close": None,
                        "weekly_price_delta_pct": None,
                        "trend_4h": "unknown",
                    }

        assets: dict[str, Any] = {}
        for coin in coin_list:
            bias = biases.get(coin)
            if not bias:
                continue
            metadata = bias.metadata
            assets[coin] = {
                "bias": bias.bias,
                "confidence": round(bias.confidence, 2),
                "bias_label": metadata.get("bias_label", bias.bias.upper()),
                "fits_score": metadata.get("fits_weighted_score", 0),
                "bias_strength": metadata.get("bias_strength", "weak"),
                "market_regime": metadata.get("market_regime", "unknown"),
                "net_non_commercial": bias.net_non_commercial,
                "net_commercial": bias.net_commercial,
                "weekly_change": bias.weekly_change,
                "open_interest": bias.open_interest,
                "oi_change_pct": bias.oi_change_pct,
                "historical_percentile": bias.historical_percentile,
                "as_of_date": metadata.get("as_of_date", metadata.get("report_date", "N/A")),
                "release_date": metadata.get("release_date", "N/A"),
                "price_context": price_context.get(coin, {}),
                "sections": sections.get(coin, {}),
            }

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_type": primary_report_type,
            "assets": assets,
        }

    def get_historical_variation(
        self,
        *,
        months: int,
        coins: str | list[str] = "BTC ETH",
        report_type: str = "futures_and_options",
        include_micro: bool = False,
        debug: bool = False,
    ) -> dict[str, Any]:
        if not (1 <= months <= 12):
            raise ValueError("months must be between 1 and 12")

        coin_list = self._parse_coins(coins)
        history_weeks = self._history_weeks_for_months(months)
        cot_data = fetch_latest_cot(
            report_type="futures_only" if report_type == "futures_only" else "futures_and_options",
            include_micro=include_micro,
            debug=debug,
            history_weeks=history_weeks,
        )
        selected = {coin: cot_data[coin] for coin in coin_list if coin in cot_data}
        historical = self._history_analyzer.generate_historical_variation(
            months=months,
            cot_data=selected,
        )
        markdown = self._reporter.render_historical_markdown(
            months=months,
            as_of=str(historical.get("as_of_date", "N/A")),
            per_asset=historical.get("assets", {}),
            observations=historical.get("observations", []),
        )
        return {
            **historical,
            "markdown": markdown,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_weekly_plan(
        self,
        *,
        coins: str | list[str] = "BTC ETH",
        include_micro: bool = False,
        debug: bool = False,
        capital_usd: float = 2000.0,
        leverage: float = 10.0,
        wallet: str = "hermes",
        testnet: bool = True,
    ) -> dict[str, Any]:
        coin_list = self._parse_coins(coins)

        futures_only = fetch_latest_cot(
            report_type="futures_only",
            include_micro=include_micro,
            debug=debug,
        )
        combined = fetch_latest_cot(
            report_type="futures_and_options",
            include_micro=include_micro,
            debug=debug,
        )

        cot_sections = build_cot_sections_from_datasets(
            futures_only_data=futures_only,
            combined_data=combined,
        )
        cot_sections = {coin: cot_sections[coin] for coin in coin_list if coin in cot_sections}

        biases = self._analyzer.analyze(combined)
        market_client = HyperliquidClient(wallet_name=wallet, testnet=testnet)

        market_data_4h: dict[str, dict[str, Any]] = {}
        for coin in coin_list:
            bias = biases.get(coin)
            if not bias:
                continue
            as_of_date = str(bias.metadata.get("as_of_date") or datetime.now().date().isoformat())
            try:
                market_data_4h[coin] = self._market_structure_4h(market_client, coin, as_of_date)
            except Exception:
                market_data_4h[coin] = {
                    "trend": "unknown",
                    "price": 0.0,
                    "swing_high": 0.0,
                    "swing_low": 0.0,
                    "atr": 1.0,
                }

        weekly_plan = self._position_generator.generate_weekly_plan(
            cot_data=cot_sections,
            market_data_4h=market_data_4h,
            capital_usd=capital_usd,
            leverage=leverage,
        )
        weekly_plan["report_markdown"] = self._reporter.render_weekly_plan_markdown(weekly_plan)
        return weekly_plan
