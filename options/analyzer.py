"""High-level options analysis orchestrator."""

from __future__ import annotations

import json
import math
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
from options.cache import OptionsCacheStore
from options.config import OptionsConfig, load_options_config
from options.exceptions import OptionsComputationError, OptionsDataError, OptionsStrategyError
from options.fetchers import YFinanceOptionsFetcher
from options.scoring import rank_recommendations
from options.strategies import build_strategy_candidates
from options.visualization import (
    build_greeks_chart,
    build_payoff_chart,
    build_pnl_distribution_chart,
    build_strategy_ranking_chart,
)

logger = configure_logger(__name__)


def _safe_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _format_pct(value: float | None, *, scale: float = 100.0) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value * scale:.1f}%"


def _format_number(value: float | None, *, decimals: int = 1, prefix: str = "") -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{prefix}{value:.{decimals}f}"


def _strategy_name(rec: dict[str, Any]) -> str:
    return str(((rec.get("strategy") or {}).get("name")) or "unknown")


def _strategy_bias(strategy_name: str) -> str:
    if strategy_name in {
        "bull_put_credit_spread",
        "bull_call_debit_spread",
        "cash_secured_put",
        "covered_call",
    }:
        return "bullish"
    if strategy_name in {"iron_condor", "call_butterfly"}:
        return "neutral"
    if strategy_name in {"long_strangle", "long_straddle"}:
        return "long_volatility"
    return "other"


def _strategy_metrics(rec: dict[str, Any]) -> dict[str, Any]:
    return dict(rec.get("metrics") or {})


def _breakeven_width(rec: dict[str, Any]) -> float | None:
    points = list(((rec.get("strategy") or {}).get("breakeven_points") or []))
    numeric = [point for point in (_safe_float(item)
                                   for item in points) if point is not None]
    if len(numeric) < 2:
        return None
    return abs(numeric[-1] - numeric[0])


def _summarize_legs(rec: dict[str, Any]) -> str:
    legs = list(((rec.get("strategy") or {}).get("legs") or []))
    if not legs:
        return "No leg details available."

    parts: list[str] = []
    for leg in legs:
        side = str(leg.get("side") or "?")
        quantity = int(leg.get("quantity") or 0)
        instrument = str(leg.get("instrument_type") or "instrument")
        strike = _safe_float(leg.get("strike"))
        option_type = str(leg.get("option_type") or "")
        if instrument == "option" and strike is not None:
            parts.append(f"{side} {quantity} {option_type} {strike:.0f}")
        else:
            premium = _safe_float(leg.get("premium"))
            if premium is not None:
                parts.append(f"{side} {quantity} stock @ {premium:.2f}")
            else:
                parts.append(f"{side} {quantity} {instrument}")
    return "; ".join(parts)


def _strategy_flags(
    rec: dict[str, Any],
    *,
    one_std_move: float,
    skew: dict[str, Any],
) -> dict[str, bool]:
    metrics = _strategy_metrics(rec)
    strategy_name = _strategy_name(rec)
    expected_value = _safe_float(metrics.get("expected_value")) or 0.0
    pop = _safe_float(metrics.get("pop")) or 0.0
    touch = _safe_float(metrics.get("probability_of_touch")) or 0.0
    theta_per_day = _safe_float(metrics.get("theta_per_day")) or 0.0
    breakeven_width = _breakeven_width(rec)
    skew_diff = _safe_float(skew.get("skew_diff")) or 0.0
    two_sided_expected_move = max(0.0, one_std_move * 2.0)

    return {
        "range_too_tight_vs_expected_move": bool(
            strategy_name == "iron_condor"
            and breakeven_width is not None
            and two_sided_expected_move > 0
            and breakeven_width < (two_sided_expected_move * 0.6)
        ),
        "negative_ev_despite_high_pop": expected_value < 0.0 and pop >= 55.0,
        "high_path_risk": touch >= 70.0 or (touch - pop) >= 12.0,
        "puts_rich_supportive": skew_diff > 0.0 and strategy_name in {
            "bull_put_credit_spread",
            "cash_secured_put",
            "iron_condor",
        },
        "defined_risk_income_candidate": strategy_name in {
            "bull_put_credit_spread",
            "iron_condor",
        } and theta_per_day >= 0.0,
    }


def _comparison_commentary(
    rec: dict[str, Any],
    *,
    one_std_move: float,
    flags: dict[str, bool],
) -> str:
    metrics = _strategy_metrics(rec)
    strategy_name = _strategy_name(rec)
    expected_value = _safe_float(metrics.get("expected_value")) or 0.0
    pop = _safe_float(metrics.get("pop")) or 0.0
    touch = _safe_float(metrics.get("probability_of_touch")) or 0.0
    theta_per_day = _safe_float(metrics.get("theta_per_day")) or 0.0
    breakeven_width = _breakeven_width(rec)

    if strategy_name == "iron_condor":
        if flags.get("range_too_tight_vs_expected_move"):
            return (
                f"The condor's profitable width ({_format_number(breakeven_width, decimals=1, prefix='$')}) "
                f"is too narrow relative to the roughly +/- {_format_number(one_std_move, decimals=1, prefix='$')} expected move. "
                "Headline PoP looks acceptable, but the structure is fragile once path risk and tail risk are considered."
            )
        return "Neutral premium-selling structure, but it should only be favored when the profitable band is comfortably wider than day-to-day noise."

    if strategy_name == "bull_put_credit_spread":
        return (
            "Defined-risk short put premium setup that only needs the underlying to hold above support. "
            "It is a more realistic conservative expression than a tight condor when puts are rich and the tape is bullish-to-neutral."
        )

    if strategy_name == "long_straddle":
        return (
            f"Pure long-volatility bet with heavy theta burn ({_format_number(theta_per_day, decimals=2, prefix='$')}/day). "
            "It needs a large move or volatility expansion quickly, which makes it expensive to hold in a merely choppy tape."
        )

    if strategy_name == "long_strangle":
        return (
            f"Cheaper breakout expression than the straddle, with less theta drag and similar convexity if the move expands. "
            f"It is the cleaner aggressive choice when expected value ({_format_number(expected_value, decimals=2, prefix='$')}) and path risk are comparable."
        )

    if flags.get("negative_ev_despite_high_pop"):
        return (
            f"The setup wins often on paper (PoP {_format_number(pop)}%), but negative expected value "
            f"({_format_number(expected_value, decimals=2, prefix='$')}) means the payout profile still works against disciplined sizing."
        )

    if flags.get("high_path_risk"):
        return (
            f"Probability of touch ({_format_number(touch)}%) is high enough that this trade is likely to become uncomfortable well before expiration, "
            "even if the terminal PoP looks acceptable."
        )

    return str(rec.get("tradeoff_comment") or "")


def _conservative_pick_score(rec: dict[str, Any], *, flags: dict[str, bool]) -> float:
    metrics = _strategy_metrics(rec)
    score = _safe_float(metrics.get("composite_score")) or 0.0
    strategy_name = _strategy_name(rec)
    expected_value = _safe_float(metrics.get("expected_value")) or 0.0

    if strategy_name == "bull_put_credit_spread":
        score += 10.0
    if flags.get("puts_rich_supportive"):
        score += 5.0
    if flags.get("defined_risk_income_candidate"):
        score += 4.0
    if flags.get("range_too_tight_vs_expected_move"):
        score -= 18.0
    if flags.get("negative_ev_despite_high_pop"):
        score -= 10.0
    if flags.get("high_path_risk"):
        score -= 10.0
    if expected_value < 0.0:
        score -= 6.0
    return score


def _aggressive_pick_score(
    rec: dict[str, Any],
    *,
    iv_rank: float,
    iv_percentile: float,
) -> float:
    metrics = _strategy_metrics(rec)
    score = _safe_float(metrics.get("composite_score")) or 0.0
    strategy_name = _strategy_name(rec)
    theta_per_day = _safe_float(metrics.get("theta_per_day")) or 0.0

    if strategy_name == "long_strangle":
        score += 8.0
    if strategy_name == "long_straddle" and (iv_rank >= 40.0 or iv_percentile >= 80.0):
        score -= 6.0
    if theta_per_day < 0.0:
        score += max(-8.0, theta_per_day * 10.0)
    return score


def _pick_recommendation(
    recs: list[dict[str, Any]],
    *,
    names: set[str],
    scorer,
) -> dict[str, Any] | None:
    candidates = [rec for rec in recs if _strategy_name(rec) in names]
    if not candidates:
        return None
    return max(candidates, key=scorer)


def _recommendation_snapshot(rec: dict[str, Any], *, thesis: str, rationale: str) -> dict[str, Any]:
    metrics = _strategy_metrics(rec)
    return {
        "strategy_name": _strategy_name(rec),
        "bias": _strategy_bias(_strategy_name(rec)),
        "thesis": thesis,
        "rationale": rationale,
        "setup_summary": _summarize_legs(rec),
        "metrics": {
            "composite_score": metrics.get("composite_score"),
            "pop": metrics.get("pop"),
            "expected_value": metrics.get("expected_value"),
            "probability_of_touch": metrics.get("probability_of_touch"),
            "theta_per_day": metrics.get("theta_per_day"),
            "vega_exposure": metrics.get("vega_exposure"),
            "risk_reward": metrics.get("risk_reward"),
            "max_loss": metrics.get("max_loss"),
        },
    }


def _build_narrative_overlay(
    *,
    ticker: str,
    underlying_analysis: dict[str, Any],
    all_ranked: list[dict[str, Any]],
) -> dict[str, Any]:
    implied = dict(underlying_analysis.get("implied_volatility") or {})
    hv = dict(underlying_analysis.get("historical_volatility") or {})
    expected_move = dict(underlying_analysis.get("expected_move") or {})
    hv_vs_iv = dict(underlying_analysis.get("hv_vs_iv") or {})
    skew = dict(underlying_analysis.get("put_call_skew") or {})
    snapshot = dict(underlying_analysis.get("options_market_snapshot") or {})

    price = _safe_float(underlying_analysis.get("price"))
    hv_short = _safe_float(hv.get("hv_30"))
    iv_mean = _safe_float(implied.get("iv_mean"))
    iv_rank = _safe_float(implied.get("iv_rank")) or 0.0
    iv_percentile = _safe_float(implied.get("iv_percentile")) or 0.0
    one_std_move = _safe_float(expected_move.get("one_std_move")) or 0.0
    one_std_move_pct = _safe_float(expected_move.get("one_std_move_pct"))
    put_call_oi_ratio = _safe_float(snapshot.get("put_call_oi_ratio"))
    put_call_volume_ratio = _safe_float(snapshot.get("put_call_volume_ratio"))
    skew_diff = _safe_float(skew.get("skew_diff"))
    iv_rich = bool(hv_vs_iv.get("iv_rich_vs_hv_short"))

    flags_by_name = {
        _strategy_name(rec): _strategy_flags(rec, one_std_move=one_std_move, skew=skew)
        for rec in all_ranked
    }
    ranked_by_name = {_strategy_name(rec): rec for rec in all_ranked}
    comparison_names = [
        "iron_condor",
        "long_straddle",
        "long_strangle",
        "bull_put_credit_spread",
    ]
    comparison = []
    for name in comparison_names:
        rec = ranked_by_name.get(name)
        if rec is None:
            continue
        metrics = _strategy_metrics(rec)
        comparison.append(
            {
                "strategy_name": name,
                "setup_summary": _summarize_legs(rec),
                "flags": flags_by_name[name],
                "commentary": _comparison_commentary(
                    rec,
                    one_std_move=one_std_move,
                    flags=flags_by_name[name],
                ),
                "metrics": {
                    "composite_score": metrics.get("composite_score"),
                    "pop": metrics.get("pop"),
                    "expected_value": metrics.get("expected_value"),
                    "theta_per_day": metrics.get("theta_per_day"),
                    "vega_exposure": metrics.get("vega_exposure"),
                    "risk_reward": metrics.get("risk_reward"),
                    "probability_of_touch": metrics.get("probability_of_touch"),
                    "max_loss": metrics.get("max_loss"),
                    "breakeven_points": ((rec.get("strategy") or {}).get("breakeven_points") or []),
                },
            }
        )

    bias_rankings: dict[str, list[dict[str, Any]]] = {
        "bullish": [],
        "neutral": [],
        "long_volatility": [],
        "other": [],
    }
    for rec in all_ranked:
        name = _strategy_name(rec)
        bias = _strategy_bias(name)
        metrics = _strategy_metrics(rec)
        bias_rankings[bias].append(
            {
                "strategy_name": name,
                "composite_score": metrics.get("composite_score"),
                "expected_value": metrics.get("expected_value"),
                "pop": metrics.get("pop"),
                "probability_of_touch": metrics.get("probability_of_touch"),
                "tradeoff_comment": rec.get("tradeoff_comment") or "",
            }
        )

    best_modeled = all_ranked[0] if all_ranked else None
    best_conservative = _pick_recommendation(
        all_ranked,
        names={"bull_put_credit_spread", "iron_condor",
               "cash_secured_put", "covered_call"},
        scorer=lambda rec: _conservative_pick_score(
            rec, flags=flags_by_name[_strategy_name(rec)]),
    )
    best_aggressive = _pick_recommendation(
        all_ranked,
        names={"long_strangle", "long_straddle",
               "bull_call_debit_spread", "call_butterfly"},
        scorer=lambda rec: _aggressive_pick_score(
            rec, iv_rank=iv_rank, iv_percentile=iv_percentile),
    )

    conservative_rationale = (
        "Defined-risk short put premium is preferred over a tight condor when put skew is supportive, the tape is bullish-to-neutral, "
        "and the condor's range is too small relative to the expected move."
        if best_conservative is not None and _strategy_name(best_conservative) == "bull_put_credit_spread"
        else "Use the highest-quality income setup only if path risk remains manageable relative to the expected move."
    )
    aggressive_rationale = (
        "The strangle is favored over the straddle when implied volatility is already elevated, because it keeps breakout convexity while reducing theta burn."
        if best_aggressive is not None and _strategy_name(best_aggressive) == "long_strangle"
        else "Aggressive setups must be treated as timing-dependent volatility trades, not passive holds."
    )

    return {
        "executive_summary": [
            (
                f"{ticker} is in a {'neutral-high' if iv_rich else 'balanced'} volatility regime: IV mean {_format_pct(iv_mean)} "
                f"versus HV30 {_format_pct(hv_short)}, with IV Rank {_format_number(iv_rank)} and IV Percentile {_format_number(iv_percentile)}."
            ),
            (
                f"Options positioning is bullish-to-neutral rather than truly range-compressed: put/call OI ratio {_format_number(put_call_oi_ratio)} "
                f"and put/call volume ratio {_format_number(put_call_volume_ratio)} should be read alongside put skew diff {_format_pct(skew_diff)}."
            ),
            (
                f"The 30-day expected move is about +/- {_format_number(one_std_move, prefix='$')} "
                f"({_format_pct(one_std_move_pct)} of spot), so premium-selling trades need enough room to survive ordinary displacement."
            ),
            "Prioritize expected value and path risk over headline PoP. High-probability setups with negative EV or high touch risk should not be treated as conservative income trades.",
        ],
        "volatility_market_context": {
            "regime_summary": (
                "Implied volatility is slightly richer than realized volatility, which supports selective short premium, "
                "but the percentile backdrop argues against selling too-tight ranges or assuming realized movement stays muted."
                if iv_rich
                else "Implied volatility is not clearly rich to realized volatility, so short-premium trades need cleaner structural edge than headline PoP alone."
            ),
            "skew_interpretation": (
                "ATM puts are priced richer than ATM calls, which supports downside premium sellers such as short put spreads more than symmetric range-selling structures."
                if (skew_diff or 0.0) > 0.0
                else "Skew is not strongly supportive of downside premium sales, so short-put structures should rely more on directional conviction than on skew edge."
            ),
            "expected_move_assessment": (
                f"Use +/- {_format_number(one_std_move, prefix='$')} as the baseline displacement budget. Any structure with a materially narrower profitable band should be treated as fragile."
            ),
            "path_risk_note": "Probability of touch matters because traders manage through the life of the trade, not only at expiration."
        },
        "bias_rankings": bias_rankings,
        "strategy_comparison": comparison,
        "final_recommendations": {
            "best_modeled_setup": (
                _recommendation_snapshot(
                    best_modeled,
                    thesis="Highest quantitative ranking from the current model output.",
                    rationale=str(best_modeled.get("tradeoff_comment") or ""),
                )
                if best_modeled is not None
                else None
            ),
            "best_conservative_executable_setup": (
                _recommendation_snapshot(
                    best_conservative,
                    thesis="Preferred conservative expression based on executable structure and path-risk realism.",
                    rationale=conservative_rationale,
                )
                if best_conservative is not None
                else None
            ),
            "best_aggressive_setup": (
                _recommendation_snapshot(
                    best_aggressive,
                    thesis="Preferred aggressive expression for traders expecting a meaningful breakout or volatility expansion.",
                    rationale=aggressive_rationale,
                )
                if best_aggressive is not None
                else None
            ),
        },
        "risk_management_framework": {
            "conservative_setup": {
                "profit_taking": "Take profits into 40-60% of max credit rather than forcing full expiry decay.",
                "price_invalidation": "Reduce or exit if the short strike loses technical support with momentum.",
                "sizing": "Risk about 1-2% of account equity on defined-risk short-premium structures."
            },
            "aggressive_setup": {
                "profit_taking": "Pay for convexity only when the move starts; monetize quickly on volatility expansion or directional acceleration.",
                "time_invalidation": "Exit if the underlying remains trapped and theta burn dominates after the initial thesis window.",
                "sizing": "Keep long-volatility bets smaller, roughly 0.5-1% of account equity."
            },
            "gap_and_volatility_risk": "Gap risk and volatility spikes matter most for short premium. Defined risk helps, but large one-day displacement can still force early exits."
        },
        "what_to_monitor_next": [
            "Whether price stays comfortably outside the short strike for conservative premium-selling setups.",
            "Any further expansion or collapse in implied volatility after entry.",
            "Breakouts that exceed the normal weekly displacement budget and make long-volatility trades more attractive.",
        ],
    }


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

        candidates = build_strategy_candidates(
            frame,
            underlying_price=underlying_price,
            target_dte=days_to_exp,
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
        narrative_overlay = _build_narrative_overlay(
            ticker=symbol,
            underlying_analysis=underlying_analysis,
            all_ranked=all_ranked_dicts,
        )

        payload = {
            "ticker": symbol,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "underlying_analysis": underlying_analysis,
            "recommendations": ranked_dicts,
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
