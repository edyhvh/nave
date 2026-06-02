"""High-level options analysis orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
try:
    import yfinance as yf
except Exception:  # noqa: BLE001
    yf = None

from core.logger import configure_logger
from options.analytics import (
    compute_historical_volatility,
    compute_iv_rank_percentile,
    compute_put_call_skew,
    enrich_greeks,
)
from options.analytics.probability import expected_move_one_std, evaluate_strategy_distribution
from options.analysis_overlay import build_narrative_overlay
from options.cache import OptionsCacheStore
from options.config import OptionsConfig, load_options_config
from options.exceptions import OptionsComputationError, OptionsDataError, OptionsError, OptionsStrategyError
from options.fetchers.deribit_fetcher import DeribitOptionsFetcher
from options.fetchers.yfinance_fetcher import YFinanceOptionsFetcher
from options.models import StrategyCandidate, StrategyLeg
from options.scoring import rank_recommendations
from options.strategies import build_strategy_candidates_with_audit
from options.visualization import (
    build_greeks_chart,
    build_payoff_chart,
    build_pnl_distribution_chart,
    build_strategy_ranking_chart,
)

logger = configure_logger(__name__)

_CRYPTO_SPOT_PROXY_TICKERS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
}

_CRYPTO_DERIBIT_TICKERS = {
    "BTC": "BTC",
    "ETH": "ETH",
}


def _days_to_expiration(expiration: str) -> int:
    exp_date = datetime.fromisoformat(expiration).date()
    now_date = datetime.now(timezone.utc).date()
    return max(1, (exp_date - now_date).days)


class OptionsAnalyzer:
    """Analyze option chains and rank strategy opportunities."""

    def __init__(self, config: OptionsConfig | None = None, fetcher_source: str = "yfinance"):
        self.config = config or load_options_config()
        self.cache = OptionsCacheStore(self.config)
        self.fetcher_source = self._normalize_source(fetcher_source)
        self.fetcher = self._build_fetcher(self.fetcher_source)

    def _normalize_source(self, source: str) -> str:
        normalized = str(source or "yfinance").strip().lower()
        if normalized not in {"yfinance", "deribit"}:
            raise OptionsComputationError(
                "source must be one of: yfinance, deribit"
            )
        return normalized

    def _build_fetcher(self, source: str) -> YFinanceOptionsFetcher | DeribitOptionsFetcher:
        if source == "deribit":
            return DeribitOptionsFetcher(self.config)
        return YFinanceOptionsFetcher(self.config)

    def _coin_mapping(self) -> dict[str, str]:
        if self.fetcher_source == "deribit":
            return _CRYPTO_DERIBIT_TICKERS
        return _CRYPTO_SPOT_PROXY_TICKERS

    def _load_or_fetch(self, ticker: str) -> tuple[pd.DataFrame, float, list[str], dict[str, Any]]:
        cached = self.cache.latest_snapshot(ticker, source=self.fetcher_source)
        if cached is not None:
            frame = self.cache.load_snapshot_frame(cached)
            if not frame.empty:
                return (
                    frame,
                    cached.underlying_price,
                    cached.expirations,
                    {
                        "used_cache": True,
                        "metadata": cached.to_dict(),
                    },
                )

        fetched = self.fetcher.fetch_chain(ticker)
        metadata = self.cache.persist_snapshot(
            ticker=ticker,
            frame=fetched.frame,
            underlying_price=fetched.underlying_price,
            expirations=fetched.expirations,
            source=self.fetcher_source,
        )
        return (
            fetched.frame,
            fetched.underlying_price,
            fetched.expirations,
            {
                "used_cache": False,
                "metadata": metadata.to_dict(),
            },
        )

    def _underlying_history(self, ticker: str) -> pd.Series:
        if yf is None:
            raise OptionsDataError(
                "yfinance is not installed. Install dependency 'yfinance' to fetch underlying history."
            )
        history_symbol = ticker
        if self.fetcher_source == "deribit" and ticker.upper() in _CRYPTO_DERIBIT_TICKERS.values():
            history_symbol = _CRYPTO_SPOT_PROXY_TICKERS.get(
                ticker.upper(), ticker)

        hist = yf.Ticker(history_symbol).history(
            period=self.config.default_history_period, interval="1d")
        if hist.empty or "Close" not in hist:
            raise OptionsComputationError(
                f"No daily close history available for {history_symbol}")
        return hist["Close"].dropna()

    def _directional_bias_from_history(self, closes: pd.Series, lookback_days: int = 20) -> str:
        if closes is None or closes.empty:
            return "neutral"
        window = closes.dropna().tail(max(5, lookback_days + 1))
        if len(window) < 5:
            return "neutral"
        spot = float(window.iloc[-1])
        base = float(window.iloc[0])
        if base <= 0:
            return "neutral"
        ret = (spot / base) - 1.0
        if ret >= 0.03:
            return "bullish"
        if ret <= -0.03:
            return "bearish"
        return "neutral"

    def _has_earnings_within_dte(self, ticker: str, dte: int) -> tuple[bool, int | None]:
        """Check if earnings is within DTE. Returns (has_earnings, days_to_earnings)."""
        if yf is None:
            return False, None
        try:
            cal = yf.Ticker(ticker).calendar
            if cal is None or getattr(cal, "empty", True):
                return False, None
            # yfinance calendar index is the event date
            next_earnings = pd.to_datetime(cal.index[0]).date()
            days_to_earnings = (next_earnings - datetime.now(timezone.utc).date()).days
            return 0 <= days_to_earnings <= dte, days_to_earnings
        except Exception:  # noqa: BLE001
            return False, None

    def _options_market_snapshot(self, frame: pd.DataFrame) -> dict[str, float]:
        if frame.empty:
            return {
                "contracts": 0.0,
                "calls": 0.0,
                "puts": 0.0,
                "call_volume": 0.0,
                "put_volume": 0.0,
                "call_open_interest": 0.0,
                "put_open_interest": 0.0,
                "put_call_volume_ratio": float("nan"),
                "put_call_oi_ratio": float("nan"),
                "avg_spread_pct": float("nan"),
            }

        calls = frame[frame["option_type"] == "call"]
        puts = frame[frame["option_type"] == "put"]
        calls_volume_col = calls["volume"] if "volume" in calls.columns else pd.Series(
            dtype=float)
        puts_volume_col = puts["volume"] if "volume" in puts.columns else pd.Series(
            dtype=float)
        calls_oi_col = calls["open_interest"] if "open_interest" in calls.columns else pd.Series(
            dtype=float)
        puts_oi_col = puts["open_interest"] if "open_interest" in puts.columns else pd.Series(
            dtype=float)
        spread_col = frame["spread_pct"] if "spread_pct" in frame.columns else pd.Series(
            dtype=float)

        call_volume = float(pd.to_numeric(
            calls_volume_col, errors="coerce").fillna(0.0).sum())
        put_volume = float(pd.to_numeric(
            puts_volume_col, errors="coerce").fillna(0.0).sum())
        call_oi = float(pd.to_numeric(
            calls_oi_col, errors="coerce").fillna(0.0).sum())
        put_oi = float(pd.to_numeric(
            puts_oi_col, errors="coerce").fillna(0.0).sum())

        put_call_volume_ratio = float(
            put_volume / call_volume) if call_volume > 0 else float("nan")
        put_call_oi_ratio = float(
            put_oi / call_oi) if call_oi > 0 else float("nan")
        avg_spread_pct = float(pd.to_numeric(
            spread_col, errors="coerce").dropna().mean())

        return {
            "contracts": float(len(frame)),
            "calls": float(len(calls)),
            "puts": float(len(puts)),
            "call_volume": call_volume,
            "put_volume": put_volume,
            "call_open_interest": call_oi,
            "put_open_interest": put_oi,
            "put_call_volume_ratio": put_call_volume_ratio,
            "put_call_oi_ratio": put_call_oi_ratio,
            "avg_spread_pct": avg_spread_pct,
        }

    def _manual_bull_put_credit_spread(
        self,
        frame: pd.DataFrame,
        *,
        expiration: str,
        short_put: float,
        long_put: float,
        short_premium: float | None,
        long_premium: float | None,
    ) -> tuple[StrategyCandidate, dict[str, Any]]:
        if short_put <= long_put:
            raise OptionsComputationError(
                "bull-put manual strategy requires --short-put above --long-put"
            )

        expiry = str(expiration).strip()
        if not expiry:
            raise OptionsComputationError(
                "manual strategy requires --expiration YYYY-MM-DD"
            )
        try:
            dte = _days_to_expiration(expiry)
        except ValueError as exc:
            raise OptionsComputationError(
                "expiration must use YYYY-MM-DD format"
            ) from exc

        expiry_frame = frame[frame["expiration"] == expiry]

        def _row_for_strike(strike: float) -> pd.Series | None:
            rows = expiry_frame[
                (expiry_frame["option_type"] == "put")
                & (pd.to_numeric(expiry_frame["strike"], errors="coerce") == float(strike))
            ]
            if rows.empty:
                return None
            return rows.iloc[0]

        short_row = _row_for_strike(short_put)
        long_row = _row_for_strike(long_put)

        if short_premium is None:
            if short_row is None:
                raise OptionsComputationError(
                    f"missing short put strike {short_put:g} for {expiry}; pass --short-premium"
                )
            short_premium = float(short_row["mid_price"])
        if long_premium is None:
            if long_row is None:
                raise OptionsComputationError(
                    f"missing long put strike {long_put:g} for {expiry}; pass --long-premium"
                )
            long_premium = float(long_row["mid_price"])

        credit = float(short_premium) - float(long_premium)
        width = float(short_put) - float(long_put)
        if credit <= 0.0:
            raise OptionsComputationError(
                "bull-put manual strategy requires a positive net credit"
            )
        if credit >= width:
            raise OptionsComputationError(
                "net credit must be lower than spread width"
            )

        candidate = StrategyCandidate(
            name="bull_put_credit_spread",
            expiration=expiry,
            days_to_expiration=dte,
            legs=[
                StrategyLeg(
                    instrument_type="option",
                    side="sell",
                    quantity=1,
                    premium=float(short_premium),
                    strike=float(short_put),
                    option_type="put",
                ),
                StrategyLeg(
                    instrument_type="option",
                    side="buy",
                    quantity=1,
                    premium=float(long_premium),
                    strike=float(long_put),
                    option_type="put",
                ),
            ],
            net_premium=credit * 100.0,
            max_profit=credit * 100.0,
            max_loss=max(0.0, (width - credit) * 100.0),
            breakeven_points=[float(short_put) - credit],
            notes=[
                "Manual bull put credit spread.",
                f"Sell {short_put:g} put @ {float(short_premium):.2f}.",
                f"Buy {long_put:g} put @ {float(long_premium):.2f}.",
            ],
        )
        audit = {
            "status": "manual",
            "strategy_generation": [
                {
                    "strategy_family": "bull_put_credit_spread",
                    "status": "built",
                    "selection": "manual_strikes",
                    "expiration": expiry,
                    "short_strike": float(short_put),
                    "long_strike": float(long_put),
                    "short_premium": float(short_premium),
                    "long_premium": float(long_premium),
                    "net_credit": credit * 100.0,
                    "max_loss": max(0.0, (width - credit) * 100.0),
                }
            ],
        }
        return candidate, audit

    def _momentum_context(self, symbol_entry: dict[str, Any]) -> dict[str, Any]:
        plans = list(symbol_entry.get("plans") or [])
        tradeable = list(symbol_entry.get("tradeable") or [])
        selected = tradeable[0] if tradeable else (plans[0] if plans else {})

        return {
            "has_plan": bool(selected),
            "tradeable": bool(tradeable),
            "tradeable_count": len(tradeable),
            "setup_status": selected.get("setup_status"),
            "side": selected.get("side"),
            "confidence_score": selected.get("confidence_score"),
            "entry_zone": selected.get("entry_zone"),
            "invalidation": selected.get("invalidation"),
            "rr_estimated": selected.get("rr_estimated"),
        }

    def _directional_bias_from_momentum(self, context: dict[str, Any]) -> str:
        side = str(context.get("side") or "").lower().strip()
        if side == "long":
            return "bullish"
        if side == "short":
            return "bearish"
        return "neutral"

    def scan_crypto_opportunities(
        self,
        *,
        coins: list[str] | None = None,
        days_to_exp: int = 30,
        tf: str = "4h,1h",
        account_equity: float = 10000.0,
        risk_pct: float = 0.005,
        score_threshold: int = 75,
        require_tradeable: bool = True,
        directional_bias_override: str | None = None,
    ) -> dict[str, Any]:
        """Scan BTC/ETH opportunities by applying momentum gating before options analysis."""
        requested = [str(coin).strip().upper()
                     for coin in (coins or ["BTC", "ETH"]) if str(coin).strip()]
        if not requested:
            raise OptionsComputationError(
                "coins must include at least one symbol")
        if not 1 <= days_to_exp <= 365:
            raise OptionsComputationError(
                "days_to_exp must be between 1 and 365")

        mapping = self._coin_mapping()
        supported = [coin for coin in requested if coin in mapping]

        momentum_payload: dict[str, Any] = {
            "summary": {},
            "timeframes": {},
            "results": {},
        }
        if supported:
            from trading.crypto.momentum.service import MomentumMarketService

            service = MomentumMarketService()
            try:
                timeframes = service.parse_timeframes(tf)
                momentum_payload = service.scan_live(
                    symbols=[f"{coin}USDT" for coin in supported],
                    timeframes=timeframes,
                    account_equity=account_equity,
                    risk_pct=risk_pct,
                    score_threshold=score_threshold,
                )
            except ValueError as exc:
                raise OptionsComputationError(str(exc)) from exc

        opportunities: dict[str, Any] = {}
        ranked: list[dict[str, Any]] = []
        momentum_allowed = 0
        options_ready = 0

        for coin in requested:
            mapped_ticker = mapping.get(coin)
            if mapped_ticker is None:
                opportunities[coin] = {
                    "coin": coin,
                    "status": "unsupported_coin",
                    "reason": "Only BTC and ETH are supported in this scan.",
                }
                continue

            momentum_entry = (momentum_payload.get("results")
                              or {}).get(f"{coin}USDT") or {}
            context = self._momentum_context(momentum_entry)
            allowed = bool(context.get("has_plan"))
            if require_tradeable:
                allowed = allowed and bool(context.get("tradeable"))

            if not allowed:
                override = str(directional_bias_override or "").strip().lower()
                if override not in {"bullish", "bearish", "neutral"}:
                    opportunities[coin] = {
                        "coin": coin,
                        "ticker": mapped_ticker,
                        "status": "filtered_by_momentum",
                        "momentum": context,
                        "reason": "No momentum-qualified setup met the current gate.",
                    }
                    continue
                directional_bias = override
                momentum_allowed += 1
            else:
                momentum_allowed += 1
                directional_bias = self._directional_bias_from_momentum(context)

            try:
                options_payload = self.run(
                    ticker=mapped_ticker,
                    days_to_exp=days_to_exp,
                    directional_bias=directional_bias,
                )
            except OptionsError as exc:
                opportunities[coin] = {
                    "coin": coin,
                    "ticker": mapped_ticker,
                    "status": "options_unavailable",
                    "momentum": context,
                    "error": str(exc),
                }
                continue

            options_ready += 1
            top = (options_payload.get("recommendations") or [{}])[0]
            overlay = options_payload.get("analysis_overlay") or {}
            trade_decision = overlay.get("trade_decision") or {}
            final_recs = overlay.get("final_recommendations") or {}
            executable = final_recs.get("best_overall_executable_setup") or {}
            metrics = top.get("metrics") or {}
            strategy = (top.get("strategy") or {}).get("name")
            executable_metrics = executable.get("metrics") or {}
            executable_strategy = executable.get("strategy_name")
            has_trade_decision = bool(trade_decision)
            is_trade_candidate = trade_decision.get("status") == "trade_candidate"

            opportunities[coin] = {
                "coin": coin,
                "ticker": mapped_ticker,
                "status": "ready",
                "momentum": context,
                "directional_bias": directional_bias,
                "options": options_payload,
                "top_strategy": strategy,
                "trade_decision": trade_decision,
                "executable_strategy": executable_strategy,
                "top_metrics": {
                    "composite_score": metrics.get("composite_score"),
                    "pop": metrics.get("pop"),
                    "expected_value": metrics.get("expected_value"),
                    "probability_of_touch": metrics.get("probability_of_touch"),
                },
                "executable_metrics": {
                    "composite_score": executable_metrics.get("composite_score"),
                    "pop": executable_metrics.get("pop"),
                    "expected_value": executable_metrics.get("expected_value"),
                    "probability_of_touch": executable_metrics.get("probability_of_touch"),
                },
            }
            ranked.append(
                {
                    "coin": coin,
                    "ticker": mapped_ticker,
                    "strategy_name": (
                        executable_strategy
                        if executable_strategy or has_trade_decision
                        else strategy
                    ),
                    "trade_decision": trade_decision.get("status"),
                    "momentum_confidence": context.get("confidence_score"),
                    "strategy_score": (
                        executable_metrics.get("composite_score")
                        if executable_strategy
                        else (
                            0.0
                            if has_trade_decision and not is_trade_candidate
                            else metrics.get("composite_score")
                        )
                    ),
                    "expected_value": (
                        executable_metrics.get("expected_value")
                        if executable_strategy
                        else (
                            None
                            if has_trade_decision and not is_trade_candidate
                            else metrics.get("expected_value")
                        )
                    ),
                    "modeled_top_strategy": strategy,
                    "status": "ready",
                }
            )

        ranked = sorted(
            ranked,
            key=lambda item: (
                1 if item.get("trade_decision") == "trade_candidate" else 0,
                float(item.get("momentum_confidence") or 0.0),
                float(item.get("strategy_score") or 0.0),
                float(item.get("expected_value") or -1e9),
            ),
            reverse=True,
        )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strategy": "options_momentum_bridge_v1",
            "data_source": self.fetcher_source,
            "coins": requested,
            "score_threshold": score_threshold,
            "require_tradeable": require_tradeable,
            "days_to_exp": days_to_exp,
            "momentum": {
                "timeframes": momentum_payload.get("timeframes") or {},
                "summary": momentum_payload.get("summary") or {},
            },
            "summary": {
                "coins_requested": len(requested),
                "coins_supported": len(supported),
                "momentum_allowed": momentum_allowed,
                "options_ready": options_ready,
            },
            "opportunities": opportunities,
            "ranked": ranked,
        }

    def run(
        self,
        ticker: str = "MSFT",
        days_to_exp: int = 30,
        *,
        directional_bias: str = "neutral",
        prefer_directional_override: bool = True,
        allow_mega_cap_income_pass: bool = True,
        strategy: str | None = None,
        expiration: str | None = None,
        short_put: float | None = None,
        long_put: float | None = None,
        short_premium: float | None = None,
        long_premium: float | None = None,
    ) -> dict[str, Any]:
        """Run complete options analysis and return a JSON-ready payload."""
        symbol = ticker.upper().strip()
        if not symbol:
            raise OptionsComputationError("ticker must be a non-empty value")
        normalized_directional_bias = str(
            directional_bias or "neutral").strip().lower()
        if normalized_directional_bias not in {"bullish", "bearish", "neutral"}:
            raise OptionsComputationError(
                "directional_bias must be one of: bullish, bearish, neutral"
            )
        manual_strategy = str(strategy or "").strip().lower().replace("-", "_")

        frame, underlying_price, expirations, cache_info = self._load_or_fetch(
            symbol)
        if frame.empty:
            raise OptionsStrategyError(
                f"No option data available for {symbol}")

        closes = self._underlying_history(symbol)
        if normalized_directional_bias == "neutral":
            normalized_directional_bias = self._directional_bias_from_history(closes)
        hv_short = compute_historical_volatility(
            closes, window=self.config.hv_window_short)
        hv_long = compute_historical_volatility(
            closes, window=self.config.hv_window_long)

        iv_history = self.cache.iv_history(
            symbol,
            lookback_days=self.config.iv_history_lookback_days,
            source=self.fetcher_source,
        )
        # iv_atm will be computed after we know the selected expiration
        iv_rank, iv_percentile = compute_iv_rank_percentile(
            iv_history if not iv_history.empty else pd.Series([0.25], dtype=float),
            lookback=self.config.iv_history_lookback_days,
        )

        frame = enrich_greeks(
            frame, underlying_price=underlying_price, config=self.config)
        skew = compute_put_call_skew(frame, underlying_price=underlying_price)

        manual_candidate: StrategyCandidate | None = None
        if manual_strategy:
            if manual_strategy not in {"bull_put", "bull_put_credit_spread"}:
                raise OptionsComputationError(
                    "manual --strategy currently supports bull_put only"
                )
            if expiration is None or short_put is None or long_put is None:
                raise OptionsComputationError(
                    "bull_put manual strategy requires --expiration, --short-put, and --long-put"
                )
            manual_candidate, generation_audit = self._manual_bull_put_credit_spread(
                frame,
                expiration=expiration,
                short_put=float(short_put),
                long_put=float(long_put),
                short_premium=short_premium,
                long_premium=long_premium,
            )
            candidates = [manual_candidate]
        else:
            candidates, generation_audit = build_strategy_candidates_with_audit(
                frame,
                underlying_price=underlying_price,
                target_dte=days_to_exp,
                config=self.config,
            )
        if not candidates:
            raise OptionsStrategyError(
                f"No strategy candidates found for {symbol}")

        # FIX P0: Compute IV from selected expiration only, filter outliers, use median
        selected_expiration = candidates[0].expiration
        chain_slice = frame[frame["expiration"] == selected_expiration]
        clean_iv = pd.to_numeric(
            chain_slice["implied_volatility"], errors="coerce"
        ).dropna()
        # Remove obvious data errors (deep OTM illiquid options with absurd IVs)
        clean_iv = clean_iv[(clean_iv >= 0.05) & (clean_iv <= 2.0)]
        iv_atm = float(clean_iv.median()) if not clean_iv.empty else 0.25

        # Update IV history with the cleaned IV for rank/percentile
        if not iv_history.empty:
            iv_history = pd.concat(
                [iv_history, pd.Series([iv_atm], dtype=float)],
                ignore_index=True,
            )
        iv_rank, iv_percentile = compute_iv_rank_percentile(
            iv_history if not iv_history.empty else pd.Series([iv_atm], dtype=float),
            lookback=self.config.iv_history_lookback_days,
        )

        one_std_move = expected_move_one_std(
            underlying_price, iv_atm, days_to_exp)
        all_ranked = rank_recommendations(
            candidates=candidates,
            option_frame=frame,
            underlying_price=underlying_price,
            iv_atm=iv_atm,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            top_n=max(3, len(candidates)),
            risk_free_rate=self.config.risk_free_rate,
            equity_risk_premium=self.config.equity_risk_premium,
            directional_bias=normalized_directional_bias,
        )
        if not all_ranked:
            raise OptionsStrategyError(
                f"Unable to rank strategies for {symbol}")
        ranked = all_ranked[:3]

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        top = all_ranked[0]

        payoff_path = build_payoff_chart(
            recommendation=top,
            underlying_price=underlying_price,
            output_path=self.config.charts_dir / f"{symbol}_{ts}_payoff.html",
        )
        greeks_path = build_greeks_chart(
            option_frame=frame,
            output_path=self.config.charts_dir / f"{symbol}_{ts}_greeks.html",
        )
        mc_path = build_pnl_distribution_chart(
            recommendation=top,
            underlying_price=underlying_price,
            hv_annualized=hv_short if pd.notna(hv_short) else 0.3,
            days_to_expiration=top.strategy.days_to_expiration,
            n_paths=self.config.monte_carlo_paths,
            seed=self.config.monte_carlo_seed,
            output_path=self.config.charts_dir /
            f"{symbol}_{ts}_monte_carlo.html",
        )
        options_snapshot = self._options_market_snapshot(frame)
        ranking_path = build_strategy_ranking_chart(
            recommendations=all_ranked,
            ticker=symbol,
            underlying_price=underlying_price,
            options_snapshot=options_snapshot,
            output_path=self.config.charts_dir / f"{symbol}_{ts}_ranking.html",
        )

        underlying_analysis = {
            "price": underlying_price,
            "historical_volatility": {
                f"hv_{self.config.hv_window_short}": hv_short,
                f"hv_{self.config.hv_window_long}": hv_long,
            },
            "implied_volatility": {
                "iv_mean": iv_atm,
                "iv_rank": iv_rank,
                "iv_percentile": iv_percentile,
            },
            "expected_move": {
                "horizon_days": days_to_exp,
                "one_std_move": one_std_move,
                "one_std_move_pct": float(one_std_move / underlying_price) if underlying_price > 0 else float("nan"),
            },
            "hv_vs_iv": {
                "hv_short_minus_iv": float(hv_short - iv_atm) if pd.notna(hv_short) else float("nan"),
                "hv_long_minus_iv": float(hv_long - iv_atm) if pd.notna(hv_long) else float("nan"),
                "iv_rich_vs_hv_short": bool(pd.notna(hv_short) and iv_atm > hv_short),
            },
            "put_call_skew": skew,
            "options_market_snapshot": options_snapshot,
            "expirations_available": expirations,
            "contracts_analyzed": int(len(frame)),
            "directional_bias": normalized_directional_bias,
        }

        # FIX P1: Add earnings warning if applicable
        has_earnings, days_to_earnings = self._has_earnings_within_dte(
            symbol, days_to_exp)
        if has_earnings:
            underlying_analysis["event_warning"] = {
                "type": "earnings",
                "days_to_event": days_to_earnings,
                "recommendation": "avoid_income_strategies_through_earnings",
            }
        if manual_candidate is not None:
            underlying_analysis["manual_strategy"] = {
                "strategy": manual_strategy,
                "expiration": manual_candidate.expiration,
                "days_to_expiration": manual_candidate.days_to_expiration,
                "net_credit": manual_candidate.net_premium,
                "max_loss": manual_candidate.max_loss,
                "breakeven": manual_candidate.breakeven_points[0],
            }
        all_ranked_dicts = [rec.to_dict() for rec in all_ranked]
        ranked_dicts = all_ranked_dicts[:3]
        narrative_overlay = build_narrative_overlay(
            ticker=symbol,
            underlying_analysis=underlying_analysis,
            all_ranked=all_ranked_dicts,
            generation_audit=generation_audit,
            conservative_touch_max_pct=self.config.conservative_touch_max_pct,
            modeled_touch_warning_pct=self.config.modeled_touch_warning_pct,
            prefer_directional_override=prefer_directional_override,
            allow_mega_cap_income_pass=allow_mega_cap_income_pass,
        )

        payload = {
            "ticker": symbol,
            "data_source": self.fetcher_source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "underlying_analysis": underlying_analysis,
            "recommendations": ranked_dicts,
            "all_recommendations_ranked": all_ranked_dicts,
            "generation_audit": generation_audit,
            "analysis_overlay": narrative_overlay,
            "charts": {
                "payoff": payoff_path,
                "greeks": greeks_path,
                "monte_carlo": mc_path,
                "strategy_ranking": ranking_path,
            },
            "cache": cache_info,
        }

        return payload


def _save_report(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2,
                    default=str), encoding="utf-8")


if __name__ == "__main__":
    analyzer = OptionsAnalyzer()
    report = analyzer.run(ticker="MSFT", days_to_exp=30)
    out = analyzer.config.reports_dir / \
        f"MSFT_options_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    _save_report(report, out)
    logger.info("Saved options analysis report to %s", out)
