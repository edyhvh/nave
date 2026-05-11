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
from options.analytics.probability import expected_move_one_std
from options.analysis_overlay import build_narrative_overlay
from options.cache import OptionsCacheStore
from options.config import OptionsConfig, load_options_config
from options.exceptions import OptionsComputationError, OptionsDataError, OptionsStrategyError
from options.fetchers import YFinanceOptionsFetcher
from options.scoring import rank_recommendations
from options.strategies import build_strategy_candidates_with_audit
from options.visualization import (
    build_greeks_chart,
    build_payoff_chart,
    build_pnl_distribution_chart,
    build_strategy_ranking_chart,
)

logger = configure_logger(__name__)


class OptionsAnalyzer:
    """Analyze option chains and rank strategy opportunities."""

    def __init__(self, config: OptionsConfig | None = None):
        self.config = config or load_options_config()
        self.cache = OptionsCacheStore(self.config)
        self.fetcher = YFinanceOptionsFetcher(self.config)

    def _load_or_fetch(self, ticker: str) -> tuple[pd.DataFrame, float, list[str], dict[str, Any]]:
        cached = self.cache.latest_snapshot(ticker)
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
            source="yfinance",
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
        hist = yf.Ticker(ticker).history(
            period=self.config.default_history_period, interval="1d")
        if hist.empty or "Close" not in hist:
            raise OptionsComputationError(
                f"No daily close history available for {ticker}")
        return hist["Close"].dropna()

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

    def run(self, ticker: str = "MSFT", days_to_exp: int = 30) -> dict[str, Any]:
        """Run complete options analysis and return a JSON-ready payload."""
        symbol = ticker.upper().strip()
        if not symbol:
            raise OptionsComputationError("ticker must be a non-empty value")

        frame, underlying_price, expirations, cache_info = self._load_or_fetch(
            symbol)
        if frame.empty:
            raise OptionsStrategyError(
                f"No option data available for {symbol}")

        closes = self._underlying_history(symbol)
        hv_short = compute_historical_volatility(
            closes, window=self.config.hv_window_short)
        hv_long = compute_historical_volatility(
            closes, window=self.config.hv_window_long)

        iv_series = pd.to_numeric(
            frame["implied_volatility"], errors="coerce").dropna()
        iv_history = self.cache.iv_history(
            symbol, lookback_days=self.config.iv_history_lookback_days)
        if not iv_series.empty:
            iv_history = pd.concat([iv_history, pd.Series(
                [float(iv_series.mean())], dtype=float)], ignore_index=True)
        iv_rank, iv_percentile = compute_iv_rank_percentile(
            iv_history if not iv_history.empty else iv_series,
            lookback=self.config.iv_history_lookback_days,
        )

        frame = enrich_greeks(
            frame, underlying_price=underlying_price, config=self.config)
        skew = compute_put_call_skew(frame, underlying_price=underlying_price)

        candidates, generation_audit = build_strategy_candidates_with_audit(
            frame,
            underlying_price=underlying_price,
            target_dte=days_to_exp,
            config=self.config,
        )
        if not candidates:
            raise OptionsStrategyError(
                f"No strategy candidates found for {symbol}")

        iv_atm = float(iv_series.mean()) if not iv_series.empty else 0.25
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
                "iv_mean": float(iv_series.mean()) if not iv_series.empty else float("nan"),
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
        )

        payload = {
            "ticker": symbol,
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
