"""Hidden-gem ranking: simple executable setups + under-the-radar + X crowd interest."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from trading.stocks.x_interest import XInterestProfile, interest_score, load_x_interest_index

MEGA_CAP_TICKERS = frozenset(
    {
        "AAPL",
        "MSFT",
        "NVDA",
        "TSLA",
        "META",
        "AMZN",
        "GOOGL",
        "GOOG",
        "BRK.B",
        "BRK-B",
    }
)

# Yearly replay: chronic losers on short premium in rally regimes.
HIGH_VOL_LOSERS = frozenset({"TSLA", "PLTR", "COIN", "MSTR", "RIVN", "LCID"})

# Yearly replay: banks tended to win more often on bull puts.
QUALITY_INCOME_TICKERS = frozenset(
    {"JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC", "BK", "SCHW", "AXP"}
)

SIMPLE_STRATEGIES = frozenset(
    {
        "bull_put_credit_spread",
        "bear_call_credit_spread",
        "cash_secured_put",
    }
)

DEFAULT_FILTER = None  # set after GemFilterConfig definition


@dataclass(frozen=True)
class GemFilterConfig:
    """Tunable gates — defaults tuned from yearly replay experiment."""

    min_pop: float = 60.0
    max_touch: float = 72.0
    min_structure: float = 50.0
    require_open_recommended: bool = True
    require_bias_aligned: bool = True
    allow_neutral_banks: bool = True
    allow_bear_calls: bool = False
    block_high_vol: bool = True
    bear_call_min_hidden: float = 72.0
    mega_cap_penalty_unless_structure: float = 72.0
    quality_sector_bonus: float = 10.0
    min_gem_score: float = 50.0


# Production default: bullish bull puts (+ bank neutral), no bear calls, no TSLA/PLTR.
DEFAULT_FILTER = GemFilterConfig(
    require_bias_aligned=True,
    allow_neutral_banks=True,
    allow_bear_calls=False,
    block_high_vol=True,
    min_structure=52.0,
    min_pop=63.0,
    max_touch=70.0,
    min_gem_score=50.0,
)


def _f(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def bias_aligned(
    strategy: str,
    bias: str | None,
    *,
    ticker: str = "",
    allow_neutral_banks: bool = True,
) -> bool:
    b = (bias or "").lower()
    sym = ticker.upper()
    if "bull_put" in strategy or "cash_secured_put" in strategy:
        if b == "bullish":
            return True
        if allow_neutral_banks and b == "neutral" and sym in QUALITY_INCOME_TICKERS:
            return True
        return False
    if "bear_call" in strategy:
        return b == "bearish"
    return True


def structure_score(metrics: Mapping[str, Any]) -> float:
    pop = _f(metrics.get("pop"))
    touch = _f(metrics.get("probability_of_touch"))
    ev = _f(metrics.get("expected_value"))
    composite = _f(metrics.get("composite_score"))

    pop_pts = min(35.0, max(0.0, (pop - 50.0) * 0.7))
    touch_pts = min(25.0, max(0.0, (72.0 - touch) * 0.5))
    ev_pts = min(20.0, max(0.0, ev / 25.0)) if ev > 0 else max(-10.0, ev / 40.0)
    comp_pts = min(20.0, composite * 0.35)
    return max(0.0, min(100.0, pop_pts + touch_pts + ev_pts + comp_pts))


def hidden_factor(ticker: str, strategy: str | None) -> float:
    sym = ticker.strip().upper()
    score = 50.0
    if sym in MEGA_CAP_TICKERS:
        score -= 35.0
    elif sym in QUALITY_INCOME_TICKERS:
        score += 22.0
    elif len(sym) <= 4:
        score += 12.0
    if strategy in SIMPLE_STRATEGIES:
        score += 20.0
    elif strategy:
        score -= 15.0
    return max(0.0, min(100.0, score))


def passes_gem_filters(
    *,
    ticker: str,
    strategy: str,
    bias: str | None,
    metrics: Mapping[str, Any],
    cfg: GemFilterConfig,
) -> tuple[bool, str]:
    sym = ticker.upper()
    pop = _f(metrics.get("pop"))
    touch = _f(metrics.get("probability_of_touch"))
    struct = structure_score(metrics)
    hidden = hidden_factor(sym, strategy)

    if pop < cfg.min_pop or touch >= cfg.max_touch:
        return False, "odds_gate"
    if struct < cfg.min_structure:
        return False, "structure_weak"
    if cfg.block_high_vol and sym in HIGH_VOL_LOSERS:
        return False, "high_vol_blocklist"
    if not cfg.allow_bear_calls and "bear_call" in strategy:
        return False, "bear_calls_disabled"
    if cfg.require_bias_aligned and not bias_aligned(
        strategy,
        bias,
        ticker=sym,
        allow_neutral_banks=cfg.allow_neutral_banks,
    ):
        return False, "bias_misaligned"
    if "bear_call" in strategy and hidden < cfg.bear_call_min_hidden:
        return False, "bear_call_not_hidden_enough"
    if sym in MEGA_CAP_TICKERS and struct < cfg.mega_cap_penalty_unless_structure:
        return False, "mega_cap_needs_exceptional_structure"
    return True, "ok"


def alignment_bonus(
    *,
    options_bias: str | None,
    strategy: str | None,
    x_profile: XInterestProfile | None,
) -> float:
    if x_profile is None:
        return 0.0
    bias = (options_bias or "").lower()
    strat = strategy or ""
    x_sent = x_profile.sentiment
    if "bull_put" in strat or "cash_secured_put" in strat:
        if bias == "bullish" and x_sent == "bullish":
            return 12.0
        if bias == "bullish" and x_sent == "bearish":
            return -10.0
    if "bear_call" in strat:
        if bias == "bearish" and x_sent == "bearish":
            return 12.0
        if bias == "bearish" and x_sent == "bullish":
            return -10.0
    return 0.0


def congress_bonus(ticker: str, congress_tickers: frozenset[str] | set[str]) -> float:
    return 15.0 if ticker.upper() in congress_tickers else 0.0


def score_gem_row(
    row: Mapping[str, Any],
    *,
    x_index: Mapping[str, XInterestProfile] | None = None,
    median_x_engagement: float = 0.0,
    congress_tickers: frozenset[str] | set[str] | None = None,
    cfg: GemFilterConfig | None = None,
) -> dict[str, Any] | None:
    cfg = cfg or DEFAULT_FILTER
    status = str(row.get("status") or "")
    if status not in {"trade_candidate", "directional_override"}:
        return None

    decision = row.get("trade_decision") or {}
    if cfg.require_open_recommended and not decision.get("open_recommended"):
        return None

    metrics = row.get("executable_metrics") or {}
    strategy = str(row.get("executable_strategy") or "")
    if strategy and strategy not in SIMPLE_STRATEGIES:
        return None

    ticker = str(row.get("ticker") or "").upper()
    if not ticker:
        return None

    bias = (row.get("executable_setup") or {}).get("bias")
    ok, _block_reason = passes_gem_filters(
        ticker=ticker,
        strategy=strategy,
        bias=bias,
        metrics=metrics,
        cfg=cfg,
    )
    if not ok:
        return None

    struct = structure_score(metrics)
    hidden = hidden_factor(ticker, strategy)
    x_profile = (x_index or {}).get(ticker)
    x_pts = interest_score(x_profile, median_engagement=median_x_engagement)
    align = alignment_bonus(options_bias=bias, strategy=strategy, x_profile=x_profile)
    congress_pts = congress_bonus(ticker, congress_tickers or frozenset())
    quality_pts = cfg.quality_sector_bonus if ticker in QUALITY_INCOME_TICKERS else 0.0
    try:
        from options.ticker_strategy import registry_setup_bonus

        registry_pts, registry_reasons = registry_setup_bonus(
            ticker,
            strategy,
            options_bias=bias,
        )
    except Exception:
        registry_pts, registry_reasons = 0.0, []

    gem_score = (
        struct * 0.42
        + hidden * 0.28
        + x_pts * 0.18
        + align
        + congress_pts
        + quality_pts
        + registry_pts
    )
    gem_score = max(0.0, min(100.0, gem_score))
    if gem_score < cfg.min_gem_score:
        return None

    reasons: list[str] = []
    if struct >= 55:
        reasons.append(
            f"structure PoP {_f(metrics.get('pop')):.0f}% touch {_f(metrics.get('probability_of_touch')):.0f}%"
        )
    if ticker in QUALITY_INCOME_TICKERS:
        reasons.append("quality income sector (banks)")
    elif hidden >= 55:
        reasons.append("under-the-radar vs mega-cap")
    if cfg.require_bias_aligned:
        reasons.append(f"bias-aligned {strategy.replace('_', ' ')}")
    if x_pts >= 20 and x_profile is not None:
        reasons.append(f"X: {x_profile.post_count} posts, {x_profile.sentiment}")
    if congress_pts > 0:
        reasons.append("congressional disclosure")
    if align >= 10:
        reasons.append("X aligns with bias")
    if registry_pts != 0.0 and registry_reasons:
        reasons.extend(registry_reasons)

    tier = "gem" if gem_score >= 62 else "prospect" if gem_score >= cfg.min_gem_score else "watch"

    return {
        "ticker": ticker,
        "gem_score": round(gem_score, 1),
        "tier": tier,
        "structure_score": round(struct, 1),
        "hidden_score": round(hidden, 1),
        "x_interest_score": round(x_pts, 1),
        "alignment_bonus": round(align, 1),
        "congress_bonus": round(congress_pts, 1),
        "quality_bonus": round(quality_pts, 1),
        "registry_bonus": round(registry_pts, 1),
        "status": status,
        "strategy": strategy,
        "bias": bias,
        "metrics": dict(metrics),
        "x_profile": x_profile.as_dict() if x_profile else None,
        "reasons": reasons or ["passes refined gem filters"],
        "executable_setup": row.get("executable_setup"),
        "trade_decision": decision,
        "filter_config": "v2_refined",
    }


def score_replay_row(
    row: Mapping[str, Any],
    *,
    cfg: GemFilterConfig | None = None,
) -> dict[str, Any] | None:
    """Score a yearly-replay row using the same filters as live gems."""
    cfg = cfg or DEFAULT_FILTER
    if row.get("status") not in {"trade_candidate", "directional_override"}:
        return None
    if not row.get("mark"):
        return None
    strategy = str(row.get("strategy_name") or "")
    if strategy not in SIMPLE_STRATEGIES:
        return None
    metrics = row.get("entry_metrics") or {}
    pop = _f(metrics.get("pop"))
    touch = _f(metrics.get("probability_of_touch"))
    if cfg.require_open_recommended and (pop < cfg.min_pop or touch >= cfg.max_touch):
        return None
    ticker = str(row.get("ticker") or "").upper()
    bias = row.get("directional_bias")
    ok, _ = passes_gem_filters(
        ticker=ticker,
        strategy=strategy,
        bias=bias,
        metrics=metrics,
        cfg=cfg,
    )
    if not ok:
        return None
    struct = structure_score(metrics)
    hidden = hidden_factor(ticker, strategy)
    gem_score = struct * 0.55 + hidden * 0.45
    if gem_score < cfg.min_gem_score:
        return None
    return {
        "ticker": ticker,
        "gem_score": round(gem_score, 1),
        "tier": "gem" if gem_score >= 62 else "prospect",
        "strategy": strategy,
        "profitable": bool(row.get("profitable")),
        "pnl_dollars": (row.get("mark") or {}).get("pnl_dollars"),
    }


def summarize_filter_experiment(
    rows: list[Mapping[str, Any]],
    cfg: GemFilterConfig,
) -> dict[str, Any]:
    picks: list[dict[str, Any]] = []
    for row in rows:
        scored = score_replay_row(row, cfg=cfg)
        if scored is None:
            continue
        picks.append({**scored, "row": row})

    n = len(picks)
    if n == 0:
        return {"trades": 0, "wins": 0, "win_rate": 0.0, "avg_pnl": 0.0, "gem_tier_count": 0}

    wins = sum(1 for p in picks if p.get("profitable"))
    avg_pnl = sum(float((p.get("pnl_dollars") or 0)) for p in picks) / n
    gem_tier = sum(1 for p in picks if p.get("tier") == "gem")
    return {
        "trades": n,
        "wins": wins,
        "win_rate": wins / n,
        "avg_pnl": avg_pnl,
        "gem_tier_count": gem_tier,
    }


def rank_hidden_gems(
    scan_payload: Mapping[str, Any],
    *,
    x_index: Mapping[str, XInterestProfile] | None = None,
    congress_tickers: frozenset[str] | set[str] | None = None,
    limit: int = 25,
    cfg: GemFilterConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or DEFAULT_FILTER
    x_index = x_index if x_index is not None else load_x_interest_index()
    engagements = [p.engagement for p in x_index.values() if p.engagement > 0]
    median_eng = float(sorted(engagements)[len(engagements) // 2]) if engagements else 0.0

    gems: list[dict[str, Any]] = []
    blocked = 0
    for row in (scan_payload.get("results") or {}).values():
        scored = score_gem_row(
            row,
            x_index=x_index,
            median_x_engagement=median_eng,
            congress_tickers=congress_tickers,
            cfg=cfg,
        )
        if scored is not None:
            gems.append(scored)
        elif row.get("status") in {"trade_candidate", "directional_override"}:
            blocked += 1

    gems.sort(
        key=lambda item: (
            item.get("gem_score") or 0.0,
            item.get("structure_score") or 0.0,
        ),
        reverse=True,
    )

    # Secondary watchlist: passed core bias/vol gates but below strict pop/structure bar.
    watch_cfg = GemFilterConfig(
        min_pop=58.0,
        max_touch=72.0,
        min_structure=45.0,
        min_gem_score=42.0,
        require_bias_aligned=True,
        allow_neutral_banks=True,
        allow_bear_calls=False,
        block_high_vol=True,
    )
    watchlist: list[dict[str, Any]] = []
    gem_tickers = {g["ticker"] for g in gems}
    for row in (scan_payload.get("results") or {}).values():
        sym = str(row.get("ticker") or "").upper()
        if sym in gem_tickers:
            continue
        scored = score_gem_row(
            row,
            x_index=x_index,
            median_x_engagement=median_eng,
            congress_tickers=congress_tickers,
            cfg=watch_cfg,
        )
        if scored is not None:
            scored["tier"] = "watch"
            watchlist.append(scored)
    watchlist.sort(key=lambda item: item.get("gem_score") or 0.0, reverse=True)

    return {
        "strategy": "options_hidden_gems_v2",
        "filter": {
            "min_pop": cfg.min_pop,
            "max_touch": cfg.max_touch,
            "min_structure": cfg.min_structure,
            "require_bias_aligned": cfg.require_bias_aligned,
            "block_high_vol": cfg.block_high_vol,
            "min_gem_score": cfg.min_gem_score,
        },
        "x_snapshots_loaded": len(x_index),
        "median_x_engagement": median_eng,
        "actionable_before_filter": blocked + len(gems),
        "actionable_gems": len(gems),
        "gems": gems[:limit],
        "watchlist": watchlist[: max(5, limit // 2)],
        "all_gems": gems,
    }