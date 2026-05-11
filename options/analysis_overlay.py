"""Structured narrative overlay helpers for options analysis payloads."""

from __future__ import annotations

import math
from typing import Any


INCOME_STRATEGIES = {
    "bull_put_credit_spread",
    "cash_secured_put",
    "covered_call",
    "iron_condor",
}

AGGRESSIVE_STRATEGIES = {
    "long_strangle",
    "long_straddle",
    "bull_call_debit_spread",
    "call_butterfly",
}


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


def strategy_bias(strategy_name: str) -> str:
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
            strategy_name in {"iron_condor", "bull_put_credit_spread"}
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


def _forgivingness_score(
    rec: dict[str, Any],
    *,
    flags: dict[str, bool],
    iv_rich: bool,
    conservative_touch_max_pct: float,
) -> float:
    metrics = _strategy_metrics(rec)
    strategy_name = _strategy_name(rec)
    pop = _safe_float(metrics.get("pop")) or 0.0
    touch = _safe_float(metrics.get("probability_of_touch")) or 0.0
    expected_value = _safe_float(metrics.get("expected_value")) or 0.0
    theta_per_day = _safe_float(metrics.get("theta_per_day")) or 0.0

    score = 50.0
    score += (pop - 50.0) * 0.40
    score += max(-20.0, (conservative_touch_max_pct - touch) * 0.35)
    score += 8.0 if expected_value >= 0.0 else -10.0
    score += 7.0 if theta_per_day >= 0.0 else -10.0

    if strategy_name in INCOME_STRATEGIES:
        score += 8.0
    if strategy_name in {"long_straddle", "long_strangle"}:
        score -= 10.0
    if iv_rich and strategy_name in INCOME_STRATEGIES:
        score += 4.0

    if flags.get("range_too_tight_vs_expected_move"):
        score -= 15.0
    if flags.get("high_path_risk"):
        score -= 10.0

    return float(max(0.0, min(100.0, score)))


def _income_reason_codes(
    rec: dict[str, Any],
    *,
    flags: dict[str, bool],
    conservative_touch_max_pct: float,
) -> list[str]:
    metrics = _strategy_metrics(rec)
    strategy_name = _strategy_name(rec)
    expected_value = _safe_float(metrics.get("expected_value")) or 0.0
    touch = _safe_float(metrics.get("probability_of_touch")) or 0.0
    theta_per_day = _safe_float(metrics.get("theta_per_day")) or 0.0

    reasons: list[str] = []
    if strategy_name not in INCOME_STRATEGIES:
        reasons.append("not_income_first_structure")
    if expected_value < 0.0:
        reasons.append("negative_expected_value")
    if touch > conservative_touch_max_pct:
        reasons.append("touch_above_income_comfort")
    if theta_per_day < 0.0:
        reasons.append("negative_theta_drag")
    if flags.get("range_too_tight_vs_expected_move"):
        reasons.append("too_narrow_vs_expected_move")
    if not reasons:
        reasons.append("income_profile_supported")
    return reasons


def _income_executable_score(
    rec: dict[str, Any],
    *,
    flags: dict[str, bool],
    forgivingness_score: float,
    conservative_touch_max_pct: float,
) -> float:
    metrics = _strategy_metrics(rec)
    strategy_name = _strategy_name(rec)
    expected_value = _safe_float(metrics.get("expected_value")) or 0.0
    touch = _safe_float(metrics.get("probability_of_touch")) or 0.0
    theta_per_day = _safe_float(metrics.get("theta_per_day")) or 0.0
    composite = _safe_float(metrics.get("composite_score")) or 0.0

    score = composite * 0.55 + forgivingness_score * 0.45

    if strategy_name in INCOME_STRATEGIES:
        score += 8.0
    if strategy_name in {"long_strangle", "long_straddle"}:
        score -= 8.0
    if expected_value < 0.0:
        score -= 8.0
    if touch > conservative_touch_max_pct:
        score -= min(18.0, (touch - conservative_touch_max_pct) * 0.7)
    if theta_per_day < 0.0:
        score -= 6.0
    if flags.get("range_too_tight_vs_expected_move"):
        score -= 12.0

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
        "bias": strategy_bias(_strategy_name(rec)),
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


def _comparison_commentary(
    rec: dict[str, Any],
    *,
    one_std_move: float,
    flags: dict[str, bool],
) -> str:
    metrics = _strategy_metrics(rec)
    strategy_name = _strategy_name(rec)
    expected_value = _safe_float(metrics.get("expected_value")) or 0.0
    touch = _safe_float(metrics.get("probability_of_touch")) or 0.0
    theta_per_day = _safe_float(metrics.get("theta_per_day")) or 0.0
    breakeven_width = _breakeven_width(rec)

    if strategy_name == "iron_condor" and flags.get("range_too_tight_vs_expected_move"):
        return (
            f"Tight condor: profitable width ({_format_number(breakeven_width, decimals=1, prefix='$')}) "
            f"is narrow versus the ~+/- {_format_number(one_std_move, decimals=1, prefix='$')} expected move."
        )

    if strategy_name == "bull_put_credit_spread":
        return (
            "Defined-risk short put premium setup that is often easier to execute than tight range structures "
            "when skew and directional bias are supportive."
        )

    if strategy_name == "long_straddle":
        return (
            f"Long-volatility expression with high theta burn ({_format_number(theta_per_day, decimals=2, prefix='$')}/day)."
        )

    if strategy_name == "long_strangle":
        return (
            f"Cheaper breakout expression than the straddle with comparable convexity if range expansion occurs."
        )

    if expected_value < 0.0:
        return "High win-rate optics can hide negative expectancy; size and exits must be conservative."

    if touch >= 70.0:
        return "Path-risk is elevated; this setup is likely to become uncomfortable before expiry."

    return str(rec.get("tradeoff_comment") or "")


def _modeled_warnings(
    best_modeled: dict[str, Any] | None,
    *,
    modeled_touch_warning_pct: float,
) -> list[str]:
    if best_modeled is None:
        return []

    metrics = _strategy_metrics(best_modeled)
    expected_value = _safe_float(metrics.get("expected_value"))
    touch = _safe_float(metrics.get("probability_of_touch"))
    strategy_name = _strategy_name(best_modeled)

    warnings: list[str] = []
    if expected_value is not None and expected_value < 0.0:
        warnings.append(
            f"Highest modeled setup {strategy_name} has negative expected value ({expected_value:.2f})."
        )
    if touch is not None and touch > modeled_touch_warning_pct:
        warnings.append(
            f"Highest modeled setup {strategy_name} has high Probability of Touch ({touch:.1f}%)."
        )
    return warnings


def build_narrative_overlay(
    *,
    ticker: str,
    underlying_analysis: dict[str, Any],
    all_ranked: list[dict[str, Any]],
    generation_audit: dict[str, Any] | None = None,
    conservative_touch_max_pct: float = 75.0,
    modeled_touch_warning_pct: float = 85.0,
) -> dict[str, Any]:
    implied = dict(underlying_analysis.get("implied_volatility") or {})
    hv = dict(underlying_analysis.get("historical_volatility") or {})
    expected_move = dict(underlying_analysis.get("expected_move") or {})
    hv_vs_iv = dict(underlying_analysis.get("hv_vs_iv") or {})
    skew = dict(underlying_analysis.get("put_call_skew") or {})
    snapshot = dict(underlying_analysis.get("options_market_snapshot") or {})

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
    comparison: list[dict[str, Any]] = []
    for name in comparison_names:
        rec = ranked_by_name.get(name)
        if rec is None:
            continue
        metrics = _strategy_metrics(rec)
        flags = flags_by_name[name]
        comparison.append(
            {
                "strategy_name": name,
                "setup_summary": _summarize_legs(rec),
                "flags": flags,
                "commentary": _comparison_commentary(rec, one_std_move=one_std_move, flags=flags),
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

    ranking_work: list[dict[str, Any]] = []
    for modeled_rank, rec in enumerate(all_ranked, start=1):
        name = _strategy_name(rec)
        metrics = _strategy_metrics(rec)
        flags = flags_by_name.get(name, {})
        forgivingness = _forgivingness_score(
            rec,
            flags=flags,
            iv_rich=iv_rich,
            conservative_touch_max_pct=conservative_touch_max_pct,
        )
        executable_score = _income_executable_score(
            rec,
            flags=flags,
            forgivingness_score=forgivingness,
            conservative_touch_max_pct=conservative_touch_max_pct,
        )
        reason_codes = _income_reason_codes(
            rec,
            flags=flags,
            conservative_touch_max_pct=conservative_touch_max_pct,
        )

        ranking_work.append(
            {
                "strategy_name": name,
                "modeled_rank": modeled_rank,
                "forgivingness_score": forgivingness,
                "executable_score": executable_score,
                "reason_codes": reason_codes,
            }
        )

        bias = strategy_bias(name)
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

    executable_sorted = sorted(
        ranking_work,
        key=lambda item: item["executable_score"],
        reverse=True,
    )
    executable_rank_map = {
        item["strategy_name"]: idx for idx, item in enumerate(executable_sorted, start=1)
    }

    ranking_audit: list[dict[str, Any]] = []
    for item in ranking_work:
        name = item["strategy_name"]
        executable_rank = executable_rank_map.get(name)
        ranking_audit.append(
            {
                "strategy_name": name,
                "modeled_rank": item["modeled_rank"],
                "executable_rank": executable_rank,
                "rank_delta": (
                    None
                    if executable_rank is None
                    else (item["modeled_rank"] - executable_rank)
                ),
                "forgivingness_score": item["forgivingness_score"],
                "executable_score": item["executable_score"],
                "reason_codes": item["reason_codes"],
            }
        )

    best_modeled = all_ranked[0] if all_ranked else None
    best_conservative = _pick_recommendation(
        all_ranked,
        names=INCOME_STRATEGIES,
        scorer=lambda rec: _income_executable_score(
            rec,
            flags=flags_by_name[_strategy_name(rec)],
            forgivingness_score=_forgivingness_score(
                rec,
                flags=flags_by_name[_strategy_name(rec)],
                iv_rich=iv_rich,
                conservative_touch_max_pct=conservative_touch_max_pct,
            ),
            conservative_touch_max_pct=conservative_touch_max_pct,
        ),
    )
    best_aggressive = _pick_recommendation(
        all_ranked,
        names=AGGRESSIVE_STRATEGIES,
        scorer=lambda rec: _aggressive_pick_score(
            rec, iv_rank=iv_rank, iv_percentile=iv_percentile),
    )

    conservative_rationale = (
        "Defined-risk short put premium is preferred over a tight condor when put skew is supportive, the tape is bullish-to-neutral, and the condor range is too narrow versus expected move."
        if best_conservative is not None and _strategy_name(best_conservative) == "bull_put_credit_spread"
        else "Use the highest-quality income setup only if path risk remains manageable relative to the expected move."
    )

    aggressive_rationale = (
        "The strangle is favored over the straddle when implied volatility is already elevated, because it keeps breakout convexity while reducing theta burn."
        if best_aggressive is not None and _strategy_name(best_aggressive) == "long_strangle"
        else "Aggressive setups must be treated as timing-dependent volatility trades, not passive holds."
    )

    strategy_comparison_table: list[dict[str, Any]] = []
    for rec in all_ranked:
        name = _strategy_name(rec)
        metrics = _strategy_metrics(rec)
        flags = flags_by_name[name]
        forgivingness = _forgivingness_score(
            rec,
            flags=flags,
            iv_rich=iv_rich,
            conservative_touch_max_pct=conservative_touch_max_pct,
        )
        strategy_comparison_table.append(
            {
                "strategy": name,
                "pop": metrics.get("pop"),
                "expected_value": metrics.get("expected_value"),
                "max_loss": metrics.get("max_loss"),
                "probability_of_touch": metrics.get("probability_of_touch"),
                "forgivingness_score": forgivingness,
                "theta_per_day": metrics.get("theta_per_day"),
                "key_commentary": _comparison_commentary(
                    rec,
                    one_std_move=one_std_move,
                    flags=flags,
                ),
            }
        )

    warnings = _modeled_warnings(
        best_modeled,
        modeled_touch_warning_pct=modeled_touch_warning_pct,
    )

    practical_lens_summary = {
        "core_principle": (
            "Most periods are non-extreme; selectively selling rich premium on high-quality underlyings has edge when tail risk and psychology are managed."
        ),
        "entry_filters": {
            "iv_rank_preference": "Prefer IV Rank > 70 and IV > HV for short premium",
            "underlying_quality": "Prefer highly liquid mega-cap names with lower gap-risk",
            "event_filter": "Avoid earnings within ~10 DTE and major binary macro windows",
        },
        "management_rules": {
            "profit_target": "Close at 40-60% of max credit",
            "stop_framework": "1.5x-2x credit or technical breakdown of short strike",
            "position_sizing": "Risk 1-2% of account equity per income trade",
            "touch_preference": f"Prefer short-leg touch probability <= {conservative_touch_max_pct:.0f}%",
        },
        "execution_note": (
            "Wider 3-6% OTM bull put spreads are generally more forgiving in real execution than ultra-tight structures when IV is rich and bias is bullish."
        ),
        "modeled_vs_executable": {
            "highest_modeled": _strategy_name(best_modeled) if best_modeled else None,
            "best_conservative_executable": _strategy_name(best_conservative) if best_conservative else None,
            "best_aggressive": _strategy_name(best_aggressive) if best_aggressive else None,
        },
    }

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
        "strategy_comparison_table": strategy_comparison_table,
        "practical_trader_lens": practical_lens_summary,
        "warnings": warnings,
        "volatility_market_context": {
            "regime_summary": (
                "Implied volatility is slightly richer than realized volatility, which supports selective short premium, but the percentile backdrop argues against selling too-tight ranges."
                if iv_rich
                else "Implied volatility is not clearly rich to realized volatility, so short-premium trades need cleaner structural edge than headline PoP alone."
            ),
            "skew_interpretation": (
                "ATM puts are priced richer than ATM calls, which supports downside premium sellers more than symmetric range-selling structures."
                if (skew_diff or 0.0) > 0.0
                else "Skew is not strongly supportive of downside premium sales, so short-put structures should rely more on directional conviction than skew edge."
            ),
            "expected_move_assessment": f"Use +/- {_format_number(one_std_move, prefix='$')} as the baseline displacement budget.",
            "path_risk_note": "Probability of touch matters because traders manage through the life of the trade, not only at expiration.",
        },
        "bias_rankings": bias_rankings,
        "strategy_comparison": comparison,
        "ranking_audit": ranking_audit,
        "generation_audit": generation_audit or {},
        "final_recommendations": {
            "best_modeled_setup": (
                _recommendation_snapshot(
                    best_modeled,
                    thesis="Highest quantitative ranking from the model output.",
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
                    thesis="Preferred aggressive expression for traders expecting breakout/volatility expansion.",
                    rationale=aggressive_rationale,
                )
                if best_aggressive is not None
                else None
            ),
            "warnings": warnings,
        },
        "risk_management_framework": {
            "conservative_setup": {
                "profit_taking": "Take profits into 40-60% of max credit rather than forcing full expiry decay.",
                "price_invalidation": "Reduce or exit if the short strike loses technical support with momentum.",
                "sizing": "Risk about 1-2% of account equity on defined-risk short-premium structures.",
            },
            "aggressive_setup": {
                "profit_taking": "Pay for convexity only when the move starts; monetize quickly on volatility expansion or directional acceleration.",
                "time_invalidation": "Exit if the underlying remains trapped and theta burn dominates after the initial thesis window.",
                "sizing": "Keep long-volatility bets smaller, roughly 0.5-1% of account equity.",
            },
            "gap_and_volatility_risk": "Gap risk and volatility spikes matter most for short premium. Defined risk helps, but large one-day displacement can still force early exits.",
        },
        "what_to_monitor_next": [
            "Whether price stays comfortably outside the short strike for conservative premium-selling setups.",
            "Any further expansion or collapse in implied volatility after entry.",
            "Breakouts that exceed the normal weekly displacement budget and make long-volatility trades more attractive.",
        ],
    }
