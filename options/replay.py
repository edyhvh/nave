"""Historical replay and mark-to-market for options scan validation."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except Exception:  # noqa: BLE001
    yf = None

from options.analysis_overlay import build_narrative_overlay
from options.analytics import compute_historical_volatility, compute_iv_rank_percentile, compute_put_call_skew, enrich_greeks
from options.analytics.probability import expected_move_one_std
from options.analyzer import OptionsAnalyzer
from options.config import OptionsConfig
from options.models import StrategyCandidate, StrategyLeg
from options.scoring import rank_recommendations
from options.strategies import build_strategy_candidates_with_audit


def _norm_cdf(x: float) -> float:
    return float(0.5 * (1.0 + math.erf(x / math.sqrt(2.0))))


def bs_option_price(
    *,
    spot: float,
    strike: float,
    days_to_expiration: int,
    implied_volatility: float,
    option_type: str,
    risk_free_rate: float = 0.04,
) -> float:
    """Black-Scholes price per share (European approximation)."""
    t = max(1, days_to_expiration) / 365.0
    sigma = max(0.05, implied_volatility)
    if spot <= 0 or strike <= 0:
        return 0.0
    vol_sqrt_t = sigma * math.sqrt(t)
    if vol_sqrt_t <= 0:
        return max(0.0, spot - strike) if option_type == "call" else max(0.0, strike - spot)
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * sigma * sigma) * t) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    if option_type == "call":
        return float(spot * _norm_cdf(d1) - strike * math.exp(-risk_free_rate * t) * _norm_cdf(d2))
    return float(strike * math.exp(-risk_free_rate * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1))


def bulk_price_history(
    tickers: list[str],
    *,
    start: date,
    end: date,
) -> dict[str, pd.Series]:
    """Download adjusted closes for many tickers (fewer API calls than per-ticker)."""
    if yf is None or not tickers:
        return {}
    out: dict[str, pd.Series] = {}
    chunk_size = 40
    normalized = [str(item).upper() for item in tickers if str(item).strip()]
    for idx in range(0, len(normalized), chunk_size):
        chunk = normalized[idx: idx + chunk_size]
        try:
            frame = yf.download(
                chunk,
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                auto_adjust=True,
                progress=False,
                threads=False,
            )
        except Exception:  # noqa: BLE001
            continue
        if frame is None or frame.empty:
            continue
        if isinstance(frame.columns, pd.MultiIndex):
            if "Close" in frame.columns.get_level_values(0):
                closes = frame["Close"]
                for symbol in closes.columns:
                    series = closes[symbol].dropna()
                    if not series.empty:
                        out[str(symbol).upper()] = series
        elif "Close" in frame.columns and len(chunk) == 1:
            out[chunk[0]] = frame["Close"].dropna()
    return out


def close_on_or_before(series: pd.Series | None, as_of: date) -> float | None:
    if series is None or series.empty:
        return None
    ordered = series.sort_index()
    eligible = ordered[ordered.index.date <= as_of]
    if eligible.empty:
        return float(ordered.iloc[0])
    return float(eligible.iloc[-1])


def historical_close_on_or_before(ticker: str, as_of: date) -> float | None:
    if yf is None:
        return None
    start = as_of - timedelta(days=14)
    end = as_of + timedelta(days=2)
    try:
        hist = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True)
    except Exception:  # noqa: BLE001
        return None
    if hist is None or hist.empty:
        return None
    return close_on_or_before(hist["Close"], as_of)


def infer_directional_bias_from_series(series: pd.Series | None, as_of: date, lookback_days: int = 20) -> str:
    if series is None or series.empty:
        return "neutral"
    window = series.sort_index()
    window = window[window.index.date <= as_of].tail(max(5, lookback_days + 1))
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


def infer_directional_bias(ticker: str, as_of: date, lookback_days: int = 20) -> str:
    if yf is None:
        return "neutral"
    start = as_of - timedelta(days=lookback_days + 10)
    end = as_of + timedelta(days=2)
    try:
        hist = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True)
    except Exception:  # noqa: BLE001
        return "neutral"
    if hist is None or hist.empty:
        return "neutral"
    return infer_directional_bias_from_series(hist["Close"], as_of, lookback_days=lookback_days)


def _pick_target_expiration(expirations: list[str], entry_date: date, target_dte: int) -> str | None:
    target = entry_date + timedelta(days=target_dte)
    best: tuple[int, str] | None = None
    for raw in expirations:
        try:
            exp_date = datetime.fromisoformat(str(raw)).date()
        except ValueError:
            continue
        delta = abs((exp_date - target).days)
        if best is None or delta < best[0]:
            best = (delta, str(raw))
    return best[1] if best else None


def _leg_mid(frame: pd.DataFrame, candidate: StrategyCandidate, leg: StrategyLeg) -> float | None:
    if leg.instrument_type != "option" or leg.strike is None or leg.option_type is None:
        return float(leg.premium)
    rows = frame[
        (frame["expiration"] == candidate.expiration)
        & (frame["strike"] == float(leg.strike))
        & (frame["option_type"] == leg.option_type)
    ]
    if rows.empty:
        return None
    row = rows.iloc[0]
    mid = row.get("mid_price")
    if mid is not None and np.isfinite(mid) and float(mid) > 0:
        return float(mid)
    bid = float(row.get("bid") or 0.0)
    ask = float(row.get("ask") or 0.0)
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    last = float(row.get("last_price") or 0.0)
    return last if last > 0 else None


def reprice_legs_bs(
    candidate: StrategyCandidate,
    *,
    spot: float,
    iv: float,
    days_to_expiration: int,
    risk_free_rate: float,
) -> list[StrategyLeg]:
    repriced: list[StrategyLeg] = []
    for leg in candidate.legs:
        if leg.instrument_type != "option" or leg.strike is None or leg.option_type is None:
            repriced.append(leg)
            continue
        px = bs_option_price(
            spot=spot,
            strike=float(leg.strike),
            days_to_expiration=days_to_expiration,
            implied_volatility=iv,
            option_type=str(leg.option_type),
            risk_free_rate=risk_free_rate,
        )
        repriced.append(
            StrategyLeg(
                instrument_type=leg.instrument_type,
                side=leg.side,
                quantity=leg.quantity,
                premium=float(px),
                strike=leg.strike,
                option_type=leg.option_type,
            )
        )
    return repriced


def _candidate_from_recommendation(
    rec: dict[str, Any],
    candidates: list[StrategyCandidate],
) -> StrategyCandidate | None:
    strategy = rec.get("strategy") or {}
    name = str(strategy.get("name") or "")
    expiration = str(strategy.get("expiration") or "")
    for candidate in candidates:
        if candidate.name == name and candidate.expiration == expiration:
            return candidate
    return candidates[0] if candidates else None


def mark_candidate_pnl(
    candidate: StrategyCandidate,
    *,
    frame: pd.DataFrame,
    entry_legs: list[StrategyLeg],
    multiplier: float = 100.0,
) -> dict[str, float | None]:
    """Mark open position P/L using entry premiums and current chain mids."""
    entry_flow = 0.0
    exit_flow = 0.0
    missing_exit = 0

    for entry_leg, leg in zip(entry_legs, candidate.legs, strict=True):
        qty = float(leg.quantity)
        sign = 1.0 if entry_leg.side == "sell" else -1.0
        entry_flow += sign * float(entry_leg.premium) * qty * multiplier

        exit_mid = _leg_mid(frame, candidate, leg)
        if exit_mid is None:
            missing_exit += 1
            exit_mid = float(entry_leg.premium)
        exit_sign = -1.0 if leg.side == "sell" else 1.0
        exit_flow += exit_sign * float(exit_mid) * qty * multiplier

    pnl = entry_flow + exit_flow
    max_loss = float(candidate.max_loss or 0.0)
    max_profit = float(candidate.max_profit or 0.0) if candidate.max_profit is not None else 0.0
    return {
        "pnl_dollars": float(pnl),
        "pnl_pct_of_max_loss": float(pnl / max_loss * 100.0) if max_loss > 0 else None,
        "pnl_pct_of_max_profit": float(pnl / max_profit * 100.0) if max_profit > 0 else None,
        "missing_exit_legs": float(missing_exit),
    }


def _safe_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        v = float(value)
        return v if math.isfinite(v) else None
    return None


def _return_pct(row: dict[str, Any]) -> float | None:
    mark = row.get("mark") or {}
    pnl = _safe_float(mark.get("pnl_dollars"))
    if pnl is None:
        return None
    if pnl >= 0:
        return _safe_float(mark.get("pnl_pct_of_max_profit"))
    return _safe_float(mark.get("pnl_pct_of_max_loss"))


def analyze_ticker_at_date(
    analyzer: OptionsAnalyzer,
    ticker: str,
    *,
    entry_date: date,
    days_to_exp: int = 30,
    exit_date: date | None = None,
    price_history: dict[str, pd.Series] | None = None,
) -> dict[str, Any]:
    """Replay model selection at ``entry_date`` and mark P/L at ``exit_date``."""
    symbol = ticker.strip().upper()
    exit_date = exit_date or datetime.now(timezone.utc).date()
    history = price_history or {}
    series = history.get(symbol)
    entry_spot = close_on_or_before(series, entry_date) if series is not None else historical_close_on_or_before(symbol, entry_date)
    exit_spot = close_on_or_before(series, exit_date) if series is not None else historical_close_on_or_before(symbol, exit_date)
    if entry_spot is None or exit_spot is None:
        return {
            "ticker": symbol,
            "status": "error",
            "error": "missing_price_history",
            "entry_date": entry_date.isoformat(),
            "exit_date": exit_date.isoformat(),
        }

    try:
        frame, _spot_now, expirations, _cache = analyzer._load_or_fetch(symbol)
    except Exception as exc:  # noqa: BLE001
        return {
            "ticker": symbol,
            "status": "error",
            "error": str(exc),
            "entry_date": entry_date.isoformat(),
        }

    if frame.empty:
        return {
            "ticker": symbol,
            "status": "error",
            "error": "empty_option_chain",
            "entry_date": entry_date.isoformat(),
        }

    target_exp = _pick_target_expiration(list(expirations), entry_date, days_to_exp)
    if target_exp is None:
        return {
            "ticker": symbol,
            "status": "error",
            "error": "no_suitable_expiration",
            "entry_date": entry_date.isoformat(),
        }

    exp_date = datetime.fromisoformat(target_exp).date()
    entry_dte = max(1, (exp_date - entry_date).days)
    exit_dte = max(1, (exp_date - exit_date).days)

    directional_bias = (
        infer_directional_bias_from_series(series, entry_date)
        if series is not None
        else infer_directional_bias(symbol, entry_date)
    )
    closes = analyzer._underlying_history(symbol)
    hv_short = compute_historical_volatility(closes, window=analyzer.config.hv_window_short)
    hv_long = compute_historical_volatility(closes, window=analyzer.config.hv_window_long)
    iv_history = analyzer.cache.iv_history(
        symbol,
        lookback_days=analyzer.config.iv_history_lookback_days,
        source=analyzer.fetcher_source,
    )

    frame = enrich_greeks(frame, underlying_price=entry_spot, config=analyzer.config)
    skew = compute_put_call_skew(frame, underlying_price=entry_spot)

    candidates, generation_audit = build_strategy_candidates_with_audit(
        frame[frame["expiration"] == target_exp] if target_exp in set(frame["expiration"]) else frame,
        underlying_price=entry_spot,
        target_dte=entry_dte,
        config=analyzer.config,
    )
    if not candidates:
        candidates, generation_audit = build_strategy_candidates_with_audit(
            frame,
            underlying_price=entry_spot,
            target_dte=entry_dte,
            config=analyzer.config,
        )
    if not candidates:
        return {
            "ticker": symbol,
            "status": "no_candidates",
            "entry_date": entry_date.isoformat(),
            "entry_spot": entry_spot,
            "exit_spot": exit_spot,
        }

    chain_slice = frame[frame["expiration"] == candidates[0].expiration]
    clean_iv = pd.to_numeric(chain_slice["implied_volatility"], errors="coerce").dropna()
    clean_iv = clean_iv[(clean_iv >= 0.05) & (clean_iv <= 2.0)]
    iv_atm = float(clean_iv.median()) if not clean_iv.empty else float(hv_short or 0.25)
    if not np.isfinite(iv_atm) or iv_atm <= 0:
        iv_atm = 0.25

    iv_rank, iv_percentile = compute_iv_rank_percentile(
        iv_history if not iv_history.empty else pd.Series([iv_atm], dtype=float),
        lookback=analyzer.config.iv_history_lookback_days,
    )

    all_ranked = rank_recommendations(
        candidates=candidates,
        option_frame=frame,
        underlying_price=entry_spot,
        iv_atm=iv_atm,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        top_n=max(5, len(candidates)),
        risk_free_rate=analyzer.config.risk_free_rate,
        equity_risk_premium=analyzer.config.equity_risk_premium,
        directional_bias=directional_bias,
    )
    one_std_move = expected_move_one_std(entry_spot, iv_atm, entry_dte)
    hv_vs_iv = {
        "hv_short_minus_iv": float(hv_short - iv_atm) if pd.notna(hv_short) else float("nan"),
        "iv_rich_vs_hv_short": bool(pd.notna(hv_short) and iv_atm > hv_short),
    }
    underlying_analysis = {
        "price": entry_spot,
        "historical_volatility": {
            f"hv_{analyzer.config.hv_window_short}": hv_short,
            f"hv_{analyzer.config.hv_window_long}": hv_long,
        },
        "implied_volatility": {
            "iv_mean": iv_atm,
            "iv_rank": iv_rank,
            "iv_percentile": iv_percentile,
        },
        "expected_move": {
            "horizon_days": entry_dte,
            "one_std_move": one_std_move,
            "one_std_move_pct": float(one_std_move / entry_spot) if entry_spot > 0 else float("nan"),
        },
        "hv_vs_iv": hv_vs_iv,
        "put_call_skew": skew,
        "directional_bias": directional_bias,
    }
    ranked_dicts = [rec.to_dict() for rec in all_ranked]

    overlay = build_narrative_overlay(
        ticker=symbol,
        underlying_analysis=underlying_analysis,
        all_ranked=ranked_dicts,
        generation_audit=generation_audit,
        conservative_touch_max_pct=analyzer.config.conservative_touch_max_pct,
        modeled_touch_warning_pct=analyzer.config.modeled_touch_warning_pct,
        prefer_directional_override=True,
        allow_mega_cap_income_pass=True,
    )

    decision = overlay.get("trade_decision") or {}
    primary = (overlay.get("final_recommendations") or {}).get("best_overall_executable_setup")
    decision_status = str(decision.get("status") or "no_trade")
    status = (
        decision_status
        if decision_status in {"trade_candidate", "directional_override"} and primary
        else "no_trade"
    )

    result: dict[str, Any] = {
        "ticker": symbol,
        "status": status,
        "entry_date": entry_date.isoformat(),
        "exit_date": exit_date.isoformat(),
        "entry_spot": entry_spot,
        "exit_spot": exit_spot,
        "spot_return_pct": float((exit_spot / entry_spot - 1.0) * 100.0),
        "directional_bias": directional_bias,
        "expiration": target_exp,
        "entry_dte": entry_dte,
        "exit_dte": exit_dte,
        "trade_decision": decision,
        "executable_setup": primary,
    }

    if status not in {"trade_candidate", "directional_override"} or not primary:
        return result

    chosen_name = str(primary.get("strategy_name") or "")
    chosen_rec = next(
        (item for item in ranked_dicts if str((item.get("strategy") or {}).get("name")) == chosen_name),
        ranked_dicts[0] if ranked_dicts else None,
    )
    if chosen_rec is None:
        return result

    candidate = _candidate_from_recommendation(chosen_rec, candidates)
    if candidate is None:
        return result

    entry_iv = float(hv_short if pd.notna(hv_short) and hv_short > 0 else iv_atm)
    entry_legs = reprice_legs_bs(
        candidate,
        spot=entry_spot,
        iv=entry_iv,
        days_to_expiration=entry_dte,
        risk_free_rate=analyzer.config.risk_free_rate,
    )
    marks = mark_candidate_pnl(
        candidate,
        frame=frame,
        entry_legs=entry_legs,
    )
    entry_metrics = primary.get("metrics") or {}
    odds = {
        "pop": _safe_float(entry_metrics.get("pop")),
        "touch": _safe_float(entry_metrics.get("probability_of_touch")),
        "expected_value": _safe_float(entry_metrics.get("expected_value")),
    }
    entry_quality = "standard"
    if (
        odds["pop"] is not None
        and odds["touch"] is not None
        and odds["pop"] >= 60.0
        and odds["touch"] < 72.0
    ):
        entry_quality = "high_odds"

    result.update(
        {
            "strategy_name": chosen_name,
            "setup_summary": primary.get("setup_summary"),
            "entry_metrics": entry_metrics,
            "entry_quality": entry_quality,
            "mark": marks,
            "profitable": bool((marks.get("pnl_dollars") or 0.0) > 0.0),
            "return_pct": _return_pct(
                {
                    "mark": marks,
                }
            ),
        }
    )
    return result


def iter_monthly_entry_dates(
    *,
    months: int = 12,
    end: date | None = None,
    hold_days: int = 30,
) -> list[tuple[date, date]]:
    """Return (entry_date, exit_date) pairs: month-start entry, hold then mark."""
    end = end or datetime.now(timezone.utc).date()
    year, month = end.year, end.month
    month -= 1
    if month == 0:
        month, year = 12, year - 1

    pairs: list[tuple[date, date]] = []
    for _ in range(max(1, months)):
        entry = date(year, month, 1)
        exit_d = min(entry + timedelta(days=hold_days), end)
        if exit_d > entry:
            pairs.append((entry, exit_d))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return sorted(pairs, key=lambda item: item[0])


def _entry_odds(row: dict[str, Any]) -> dict[str, float | None]:
    metrics = row.get("entry_metrics") or {}
    return {
        "pop": _safe_float(metrics.get("pop")),
        "touch": _safe_float(metrics.get("probability_of_touch")),
        "expected_value": _safe_float(metrics.get("expected_value")),
        "composite_score": _safe_float(metrics.get("composite_score")),
    }


def summarize_yearly_backtest(
    rows: list[dict[str, Any]],
    *,
    min_pop: float = 60.0,
    max_touch: float = 72.0,
    min_return_pct: float = 40.0,
) -> dict[str, Any]:
    """Aggregate a year of replay rows; highlight high-odds and high-return subsets."""
    base = summarize_replay_rows(rows)
    trades = [
        row for row in rows
        if row.get("status") in {"trade_candidate", "directional_override"}
    ]

    high_odds = []
    for row in trades:
        odds = _entry_odds(row)
        pop = odds.get("pop")
        touch = odds.get("touch")
        if pop is None or touch is None:
            continue
        if pop >= min_pop and touch < max_touch:
            high_odds.append(row)

    high_odds_wins = [r for r in high_odds if r.get("profitable")]
    high_return = []
    for row in high_odds:
        ret = _return_pct(row)
        if ret is not None and ret >= min_return_pct:
            high_return.append(row)

    by_ticker: dict[str, dict[str, float | int]] = {}
    for row in high_odds:
        sym = str(row.get("ticker") or "")
        bucket = by_ticker.setdefault(
            sym,
            {"trades": 0, "wins": 0, "total_pnl": 0.0, "pop_sum": 0.0},
        )
        bucket["trades"] += 1
        if row.get("profitable"):
            bucket["wins"] += 1
        bucket["total_pnl"] += float((row.get("mark") or {}).get("pnl_dollars") or 0.0)
        odds = _entry_odds(row)
        if odds.get("pop") is not None:
            bucket["pop_sum"] += float(odds["pop"])

    ticker_leaderboard = []
    for sym, stats in by_ticker.items():
        n = int(stats["trades"])
        if n < 2:
            continue
        ticker_leaderboard.append(
            {
                "ticker": sym,
                "trades": n,
                "win_rate": float(stats["wins"]) / n,
                "avg_pop": float(stats["pop_sum"]) / n,
                "total_pnl": float(stats["total_pnl"]),
            }
        )
    ticker_leaderboard.sort(
        key=lambda item: (item["win_rate"], item["total_pnl"]),
        reverse=True,
    )

    by_month: dict[str, dict[str, int | float]] = {}
    for row in high_odds:
        key = str(row.get("entry_date") or "")[:7]
        bucket = by_month.setdefault(key, {"trades": 0, "wins": 0, "pnl": 0.0})
        bucket["trades"] = int(bucket["trades"]) + 1
        if row.get("profitable"):
            bucket["wins"] = int(bucket["wins"]) + 1
        bucket["pnl"] = float(bucket["pnl"]) + float(
            (row.get("mark") or {}).get("pnl_dollars") or 0.0
        )

    return {
        **base,
        "filters": {
            "min_pop": min_pop,
            "max_touch": max_touch,
            "min_return_pct": min_return_pct,
        },
        "high_odds": {
            "trades": len(high_odds),
            "wins": len(high_odds_wins),
            "losses": len(high_odds) - len(high_odds_wins),
            "win_rate": float(len(high_odds_wins) / len(high_odds)) if high_odds else 0.0,
            "avg_pnl_dollars": float(
                np.mean([float((r.get("mark") or {}).get("pnl_dollars") or 0.0) for r in high_odds])
            )
            if high_odds
            else 0.0,
        },
        "high_odds_high_return": {
            "count": len(high_return),
            "examples": [
                {
                    "ticker": r.get("ticker"),
                    "entry_date": r.get("entry_date"),
                    "strategy": r.get("strategy_name"),
                    "pop": _entry_odds(r).get("pop"),
                    "return_pct": _return_pct(r),
                    "pnl_dollars": (r.get("mark") or {}).get("pnl_dollars"),
                }
                for r in sorted(
                    high_return,
                    key=lambda item: _return_pct(item) or 0.0,
                    reverse=True,
                )[:25]
            ],
        },
        "by_month": by_month,
        "ticker_leaderboard": ticker_leaderboard[:30],
    }


def summarize_replay_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [
        row for row in rows
        if row.get("status") in {"trade_candidate", "directional_override"}
    ]
    profitable = [row for row in trades if row.get("profitable")]
    losses = [row for row in trades if not row.get("profitable")]
    no_trade = [row for row in rows if row.get("status") == "no_trade"]
    errors = [row for row in rows if row.get("status") == "error"]

    by_status: dict[str, int] = {}
    for row in trades:
        st = str(row.get("status") or "unknown")
        by_status[st] = by_status.get(st, 0) + 1

    by_strategy: dict[str, dict[str, int]] = {}
    for row in trades:
        name = str(row.get("strategy_name") or "unknown")
        bucket = by_strategy.setdefault(name, {"count": 0, "wins": 0, "losses": 0})
        bucket["count"] += 1
        if row.get("profitable"):
            bucket["wins"] += 1
        else:
            bucket["losses"] += 1

    pnl_values = [float(row.get("mark", {}).get("pnl_dollars") or 0.0) for row in trades]
    return {
        "total": len(rows),
        "trade_candidates": len(trades),
        "no_trade": len(no_trade),
        "errors": len(errors),
        "wins": len(profitable),
        "losses": len(losses),
        "win_rate": float(len(profitable) / len(trades)) if trades else 0.0,
        "avg_pnl_dollars": float(np.mean(pnl_values)) if pnl_values else 0.0,
        "total_pnl_dollars": float(np.sum(pnl_values)) if pnl_values else 0.0,
        "by_strategy": by_strategy,
        "by_status": by_status,
    }