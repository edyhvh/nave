"""Per-ticker options setup learning from replay history (not one global template)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

SIMPLE_STRATEGIES = frozenset(
    {
        "bull_put_credit_spread",
        "bear_call_credit_spread",
        "cash_secured_put",
    }
)

INCOME_STRATEGIES = frozenset(
    {
        "bull_put_credit_spread",
        "cash_secured_put",
    }
)

MIN_TRADES_HIGH = 5
MIN_TRADES_MEDIUM = 2


def _safe_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        v = float(value)
        return v if abs(v) < 1e15 else None
    return None


def _avg(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def strategy_bias_fit(strategy: str, bias: str) -> bool:
    """Whether a structure is directionally appropriate for tape bias."""
    b = (bias or "neutral").lower()
    s = strategy.lower()
    if "bull_put" in s or "cash_secured_put" in s:
        return b in {"bullish", "neutral"}
    if "bear_call" in s:
        return b == "bearish"
    return True


def edge_score(
    *,
    trades: int,
    win_rate: float,
    avg_pnl_dollars: float,
    avg_pop: float | None = None,
) -> float:
    """0–100 edge estimate; rewards sample size, win rate, and positive PnL."""
    if trades <= 0:
        return 0.0
    sample = min(1.0, trades / MIN_TRADES_HIGH)
    wr_pts = win_rate * 55.0
    pnl_pts = max(-15.0, min(25.0, avg_pnl_dollars * 0.4))
    pop_pts = 0.0
    if avg_pop is not None:
        pop_pts = max(0.0, min(10.0, (avg_pop - 55.0) * 0.2))
    raw = (wr_pts + pnl_pts + pop_pts) * sample
    return max(0.0, min(100.0, raw))


def confidence_tier(trades: int, top_trades: int) -> str:
    if top_trades >= MIN_TRADES_HIGH:
        return "high"
    if top_trades >= MIN_TRADES_MEDIUM:
        return "medium"
    return "low"


def _aggregate_replay_rows(
    replay_rows: list[Mapping[str, Any]],
    ticker: str,
    *,
    allowed_strategies: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    sym = ticker.upper()
    allowed = allowed_strategies or SIMPLE_STRATEGIES
    by_strategy: dict[str, list[Mapping[str, Any]]] = defaultdict(list)

    for row in replay_rows:
        if str(row.get("ticker") or "").upper() != sym:
            continue
        if row.get("status") not in {"trade_candidate", "directional_override"}:
            continue
        if not row.get("mark"):
            continue
        strat = str(row.get("strategy_name") or "").strip()
        if not strat or strat not in allowed:
            continue
        by_strategy[strat].append(row)

    out: list[dict[str, Any]] = []
    for strat, rows in by_strategy.items():
        n = len(rows)
        wins = sum(1 for r in rows if r.get("profitable"))
        pnls = [float((r.get("mark") or {}).get("pnl_dollars") or 0.0) for r in rows]
        pops = [_safe_float((r.get("entry_metrics") or {}).get("pop")) for r in rows]
        touches = [_safe_float((r.get("entry_metrics") or {}).get("probability_of_touch")) for r in rows]
        avg_pnl = sum(pnls) / n if n else 0.0
        wr = wins / n if n else 0.0
        score = edge_score(
            trades=n,
            win_rate=wr,
            avg_pnl_dollars=avg_pnl,
            avg_pop=_avg(pops),
        )
        out.append(
            {
                "strategy": strat,
                "trades": n,
                "win_rate": wr,
                "avg_pnl_dollars": avg_pnl,
                "avg_pop": _avg(pops),
                "avg_touch": _avg(touches),
                "edge_score": round(score, 1),
            }
        )
    out.sort(key=lambda s: (s["edge_score"], s["win_rate"], s["trades"]), reverse=True)
    return out


def _pick_for_bias(
    ranked: list[dict[str, Any]],
    bias: str,
) -> dict[str, Any] | None:
    if not ranked:
        return None
    aligned = [s for s in ranked if strategy_bias_fit(s["strategy"], bias)]
    if bias in {"bullish", "neutral"}:
        non_bear = [s for s in aligned if "bear_call" not in s["strategy"]]
        if non_bear:
            aligned = non_bear
    if not aligned:
        aligned = list(ranked)
    viable = [s for s in aligned if s["trades"] >= MIN_TRADES_MEDIUM] or aligned
    return max(
        viable,
        key=lambda s: (s["edge_score"], s["win_rate"], s["trades"]),
    )


def _avoid_list(ranked: list[dict[str, Any]]) -> list[dict[str, str]]:
    avoid: list[dict[str, str]] = []
    for s in ranked:
        if s["trades"] < MIN_TRADES_MEDIUM:
            continue
        if s["win_rate"] < 0.35 and s["avg_pnl_dollars"] < 0:
            avoid.append(
                {
                    "strategy": s["strategy"],
                    "reason": (
                        f"Replay loser: {s['win_rate']:.0%} win, "
                        f"${s['avg_pnl_dollars']:.0f} avg over {s['trades']} trades."
                    ),
                }
            )
    return avoid


def _size_guidance(confidence: str, primary: dict[str, Any] | None) -> str:
    if primary is None:
        return "skip"
    if confidence == "high" and primary.get("win_rate", 0) >= 0.55:
        return "standard"
    if confidence == "medium":
        return "half"
    return "probe"


def _filter_strategy_rows(
    replay_rows: list[Mapping[str, Any]],
    ticker: str,
    strategies: frozenset[str],
) -> list[dict[str, Any]]:
    sym = ticker.upper()
    return [
        dict(row)
        for row in replay_rows
        if str(row.get("ticker") or "").upper() == sym
        and str(row.get("strategy_name") or "") in strategies
    ]


def learn_ticker_strategy(
    replay_rows: list[Mapping[str, Any]],
    ticker: str,
    *,
    bias_20d: str = "neutral",
    bias_60d: str = "neutral",
    move_style: str = "range_bound",
    strategies: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Learn which simple setup fits this ticker — not a global default."""
    sym = ticker.upper()
    allowed = strategies or SIMPLE_STRATEGIES
    scoped = _filter_strategy_rows(replay_rows, sym, allowed) if strategies else None
    source_rows = scoped if strategies is not None else replay_rows
    ranked = _aggregate_replay_rows(source_rows, sym, allowed_strategies=allowed)
    if not ranked:
        return {
            "status": "insufficient_data",
            "ticker": sym,
            "confidence": "low",
            "primary": None,
            "by_bias": {},
            "ranked": [],
            "avoid": [],
            "narrative": "No replay trades yet — run yearly backtest for this symbol.",
            "execution": {"size": "skip", "open_only_if": ["replay_populated"]},
        }

    top_trades = ranked[0]["trades"]
    conf = confidence_tier(
        sum(s["trades"] for s in ranked),
        top_trades,
    )
    primary_row = _pick_for_bias(ranked, bias_20d) or max(
        ranked,
        key=lambda s: (s["edge_score"], s["win_rate"], s["trades"]),
    )
    by_bias = {}
    for b in ("bullish", "bearish", "neutral"):
        pick = _pick_for_bias(ranked, b)
        if pick:
            by_bias[b] = {
                "strategy": pick["strategy"],
                "edge_score": pick["edge_score"],
                "win_rate": pick["win_rate"],
                "trades": pick["trades"],
            }

    avoid = _avoid_list(ranked)
    size = _size_guidance(conf, primary_row)

    narrative = _build_narrative(
        sym,
        ranked=ranked,
        primary=primary_row,
        bias_20d=bias_20d,
        bias_60d=bias_60d,
        move_style=move_style,
        confidence=conf,
    )

    open_only_if = [
        f"20d bias is {bias_20d} (or use by_bias map)",
        f"structure matches learned primary: {primary_row['strategy']}",
    ]
    if move_style == "high_volatility":
        open_only_if.append("wider strikes / reduced size — high realized vol")
    if move_style == "trending" and bias_20d != bias_60d:
        open_only_if.append("20d vs 60d bias diverge — confirm trend before entry")

    block: dict[str, Any] = {
        "status": "ok",
        "ticker": sym,
        "confidence": conf,
        "primary": {
            "strategy": primary_row["strategy"],
            "edge_score": primary_row["edge_score"],
            "win_rate": primary_row["win_rate"],
            "trades": primary_row["trades"],
            "avg_pnl_dollars": primary_row["avg_pnl_dollars"],
            "aligned_with_20d_bias": strategy_bias_fit(primary_row["strategy"], bias_20d),
        },
        "by_bias": by_bias,
        "ranked": ranked,
        "avoid": avoid,
        "narrative": narrative,
        "execution": {
            "size": size,
            "open_only_if": open_only_if,
            "preferred_dte_window": "25–35",
        },
    }
    return block


def apply_merge_gate(
    learned: dict[str, Any],
    walkforward: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach merge_status + validated_setup (call after walkforward block exists)."""
    from options.merge_readiness import assess_merge_status

    merge = assess_merge_status(learned, walkforward)
    learned = {**learned, "merge": merge}
    if merge.get("validated_setup"):
        learned["validated_setup"] = merge["validated_setup"]
    return learned


def _build_narrative(
    ticker: str,
    *,
    ranked: list[dict[str, Any]],
    primary: dict[str, Any],
    bias_20d: str,
    bias_60d: str,
    move_style: str,
    confidence: str,
) -> str:
    parts = [
        f"{ticker}: learned setup is {primary['strategy'].replace('_', ' ')} "
        f"({primary['win_rate']:.0%} win, ${primary['avg_pnl_dollars']:.0f} avg, "
        f"n={primary['trades']}, edge {primary['edge_score']:.0f}/100, {confidence} confidence)."
    ]
    if len(ranked) > 1:
        alt = ranked[1]
        parts.append(
            f" Runner-up: {alt['strategy'].replace('_', ' ')} "
            f"(edge {alt['edge_score']:.0f}, {alt['win_rate']:.0%} win)."
        )
    if bias_20d != bias_60d:
        parts.append(f" Tape mixed: 20d {bias_20d} vs 60d {bias_60d} — check by_bias before sizing.")
    if move_style == "high_volatility":
        parts.append(" High vol name: prefer wider spreads or sit out short premium.")
    elif move_style == "trending":
        parts.append(" Trending tape: only sell premium with the trend.")
    return " ".join(parts)


def load_strategy_index(
    registry_dir: "Path | None" = None,
) -> dict[str, dict[str, Any]]:
    """Ticker → learned primary strategy from on-disk registry."""
    from pathlib import Path

    from options.ticker_registry import (
        DEFAULT_REGISTRY_DIR,
        RegistryPaths,
        load_ticker_profile,
    )

    root = Path(registry_dir) if registry_dir is not None else DEFAULT_REGISTRY_DIR
    paths = RegistryPaths(root)
    index_path = paths.index_path
    if not index_path.is_file():
        return {}
    import json

    index = json.loads(index_path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for sym in index.get("tickers") or []:
        profile = load_ticker_profile(sym, paths=paths)
        if not profile:
            continue
        learned = profile.get("learned_strategy") or {}
        primary = learned.get("primary") or {}
        if primary.get("strategy"):
            merge = learned.get("merge") or {}
            out[sym.upper()] = {
                "strategy": primary["strategy"],
                "confidence": learned.get("confidence"),
                "edge_score": primary.get("edge_score"),
                "merge_status": merge.get("merge_status", "watch"),
                "by_bias": learned.get("by_bias") or {},
                "avoid": {a["strategy"] for a in learned.get("avoid") or []},
            }
    return out


def registry_setup_bonus(
    ticker: str,
    strategy: str,
    *,
    options_bias: str | None = None,
    strategy_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[float, list[str]]:
    """Score boost when live scan matches this ticker's learned setup."""
    idx = strategy_index
    if idx is None:
        try:
            idx = load_strategy_index()
        except Exception:
            return 0.0, []

    meta = idx.get(ticker.upper())
    if not meta:
        return 0.0, []

    if meta.get("merge_status") == "reject":
        return -8.0, ["ticker strategy not merge-approved"]

    strat = strategy or ""
    reasons: list[str] = []
    primary = meta.get("strategy")
    if strat == primary:
        if meta.get("merge_status") == "approved":
            bonus = 18.0 if meta.get("confidence") == "high" else 12.0 if meta.get("confidence") == "medium" else 6.0
        else:
            bonus = 5.0
        reasons.append(f"matches learned primary ({primary.replace('_', ' ')})")
        return bonus, reasons

    b = (options_bias or "neutral").lower()
    by_bias = meta.get("by_bias") or {}
    bias_pick = by_bias.get(b) or {}
    if strat == bias_pick.get("strategy"):
        reasons.append(f"matches learned setup for {b} bias")
        return 10.0, reasons

    if strat in (meta.get("avoid") or set()):
        reasons.append("learned avoid list for this ticker")
        return -15.0, reasons

    return 0.0, []