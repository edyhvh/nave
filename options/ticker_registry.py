"""Per-ticker playbook registry: price behavior, setup stats, X, Congress."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from options.replay import bulk_price_history, infer_directional_bias_from_series
from options.ticker_strategy import apply_merge_gate, learn_ticker_strategy
from options.universe import SP500_TOP_40_TICKERS
from trading.stocks.x_interest import XMarketView, load_x_interest_index, load_x_market_index

REGISTRY_VERSION = "ticker_playbook_v2"
DEFAULT_REGISTRY_DIR = Path(__file__).resolve().parents[1] / "var" / "registry" / "sp500_top40"


@dataclass(frozen=True)
class RegistryPaths:
    root: Path

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def ticker_path(self, symbol: str) -> Path:
        return self.root / f"{symbol.upper()}.json"


def _safe_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        v = float(value)
        return v if abs(v) < 1e15 else None
    return None


def analyze_price_behavior(
    series: Any,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """How the ticker usually moves (returns, vol, trend labels)."""
    as_of = as_of or datetime.now(timezone.utc).date()
    if series is None:
        return {"status": "insufficient_history"}

    clean = series.dropna()
    if len(clean) < 30:
        return {"status": "insufficient_history"}

    def _ret(days: int) -> float | None:
        if len(clean) <= days:
            return None
        close = float(clean.iloc[-1])
        past = float(clean.iloc[-1 - days])
        if past > 0:
            return float((close / past - 1.0) * 100.0)
        return None

    returns = clean.pct_change().dropna()
    vol_20 = float(returns.tail(20).std() * (252**0.5) * 100.0) if len(returns) >= 20 else None
    vol_60 = float(returns.tail(60).std() * (252**0.5) * 100.0) if len(returns) >= 60 else None

    r20 = _ret(20)
    r60 = _ret(60)
    bias_20 = infer_directional_bias_from_series(series, as_of, lookback_days=20)
    bias_60 = infer_directional_bias_from_series(series, as_of, lookback_days=60)

    move_style = "range_bound"
    if r60 is not None and abs(r60) >= 15:
        move_style = "trending"
    elif vol_20 is not None and vol_20 >= 35:
        move_style = "high_volatility"

    return {
        "status": "ok",
        "as_of": as_of.isoformat(),
        "return_20d_pct": r20,
        "return_60d_pct": r60,
        "realized_vol_20d_ann_pct": vol_20,
        "realized_vol_60d_ann_pct": vol_60,
        "bias_20d": bias_20,
        "bias_60d": bias_60,
        "move_style": move_style,
        "typical_behavior": _describe_move_style(move_style, bias_20, vol_20),
    }


def _describe_move_style(style: str, bias: str, vol: float | None) -> str:
    vol_note = f" ~{vol:.0f}% ann. vol" if vol is not None else ""
    if style == "trending":
        return f"Tends to trend ({bias} 20d){vol_note}."
    if style == "high_volatility":
        return f"Large swings; short premium needs wider strikes{vol_note}."
    return f"Often range-bound / grind ({bias} 20d){vol_note}."


def summarize_setup_performance(
    replay_rows: list[Mapping[str, Any]],
    ticker: str,
) -> dict[str, Any]:
    """Aggregate yearly replay outcomes by strategy for one ticker."""
    sym = ticker.upper()
    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in replay_rows:
        if str(row.get("ticker") or "").upper() != sym:
            continue
        if row.get("status") not in {"trade_candidate", "directional_override"}:
            continue
        if not row.get("mark"):
            continue
        strat = str(row.get("strategy_name") or "unknown")
        by_strategy[strat].append(row)

    strategies: list[dict[str, Any]] = []
    for strat, rows in sorted(by_strategy.items(), key=lambda kv: -len(kv[1])):
        n = len(rows)
        wins = sum(1 for r in rows if r.get("profitable"))
        pnls = [float((r.get("mark") or {}).get("pnl_dollars") or 0.0) for r in rows]
        pops = [_safe_float((r.get("entry_metrics") or {}).get("pop")) for r in rows]
        touches = [_safe_float((r.get("entry_metrics") or {}).get("probability_of_touch")) for r in rows]
        wr = wins / n if n else 0.0
        avg_pnl = sum(pnls) / n if n else 0.0
        from options.ticker_strategy import edge_score as _edge_score

        strategies.append(
            {
                "strategy": strat,
                "trades": n,
                "win_rate": wr,
                "avg_pnl_dollars": avg_pnl,
                "avg_pop": _avg(pops),
                "avg_touch": _avg(touches),
                "edge_score": round(
                    _edge_score(
                        trades=n,
                        win_rate=wr,
                        avg_pnl_dollars=avg_pnl,
                        avg_pop=_avg(pops),
                    ),
                    1,
                ),
            }
        )

    strategies.sort(
        key=lambda s: (s.get("edge_score", 0), s["win_rate"], s["trades"]),
        reverse=True,
    )
    best = next((s for s in strategies if s["trades"] >= 2), strategies[0] if strategies else None)
    return {
        "total_replay_trades": sum(s["trades"] for s in strategies),
        "strategies": strategies,
        "best_strategy": best["strategy"] if best else None,
        "best_win_rate": best["win_rate"] if best else None,
        "best_edge_score": best.get("edge_score") if best else None,
        "recommendation": _setup_recommendation(strategies, sym),
    }


def _avg(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def _setup_recommendation(strategies: list[dict[str, Any]], ticker: str) -> str:
    if not strategies:
        return "No historical replay trades; run yearly backtest to populate."
    best = strategies[0]
    if best["trades"] < 2:
        return f"Thin sample ({best['trades']} trades); prefer {best['strategy']} cautiously."
    wr = best["win_rate"]
    if wr >= 0.5 and best["avg_pnl_dollars"] > 0:
        return f"Favor {best['strategy']} (replay {wr:.0%} win, ${best['avg_pnl_dollars']:.0f} avg)."
    if wr >= 0.35:
        return f"Mixed edge on {best['strategy']}; size small or wait for bias alignment."
    return f"Avoid aggressive short premium on {ticker}; replay win rate {wr:.0%}."


def load_congress_holdings_proxy(
    ticker: str,
    *,
    reports_dir: Path | None = None,
    fetch_live: bool = False,
) -> dict[str, Any]:
    """Congressional holdings proxy — disclosed purchases/sales for a symbol."""
    sym = ticker.upper()
    trades: list[dict[str, Any]] = []

    root = reports_dir or (Path(__file__).resolve().parents[1] / "var" / "reports" / "politicians")
    if root.is_dir():
        for path in sorted(root.glob("*.json"), reverse=True)[:5]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for raw in payload.get("new_trades") or payload.get("trades") or []:
                if str(raw.get("symbol") or "").upper() != sym:
                    continue
                trades.append(
                    {
                        "politician": raw.get("politician"),
                        "chamber": raw.get("chamber"),
                        "transaction_type": raw.get("transaction_type"),
                        "amount_range": raw.get("amount_range"),
                        "transaction_date": raw.get("transaction_date"),
                        "disclosure_date": raw.get("disclosure_date"),
                    }
                )

    if fetch_live and len(trades) < 3:
        try:
            from trading.stocks.politicians.provider import FMPPoliticianTradesProvider

            provider = FMPPoliticianTradesProvider()
            for trade in provider.fetch_all():
                if (trade.symbol or "").upper() == sym:
                    trades.append(
                        {
                            "politician": trade.politician,
                            "chamber": trade.chamber,
                            "transaction_type": trade.transaction_type,
                            "amount_range": trade.amount_range,
                            "transaction_date": trade.transaction_date,
                            "disclosure_date": trade.disclosure_date,
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "partial",
                "mentions": len(trades),
                "recent_trades": trades[:10],
                "note": f"live_fetch_failed: {exc}",
            }

    purchases = sum(1 for t in trades if "purchase" in str(t.get("transaction_type") or "").lower())
    sales = sum(1 for t in trades if "sale" in str(t.get("transaction_type") or "").lower())
    lean = "neutral"
    if purchases > sales * 1.5 and purchases > 0:
        lean = "accumulation"
    elif sales > purchases * 1.5 and sales > 0:
        lean = "distribution"

    holders: dict[str, dict[str, int]] = {}
    for t in trades:
        name = str(t.get("politician") or "unknown")
        bucket = holders.setdefault(name, {"purchases": 0, "sales": 0})
        tx = str(t.get("transaction_type") or "").lower()
        if "purchase" in tx:
            bucket["purchases"] += 1
        elif "sale" in tx:
            bucket["sales"] += 1

    holder_rows = [
        {"politician": name, **counts}
        for name, counts in sorted(holders.items(), key=lambda item: -sum(item[1].values()))
    ]

    return {
        "status": "ok" if trades else "none",
        "role": "institutional_sentiment_proxy",
        "mentions": len(trades),
        "purchase_count": purchases,
        "sale_count": sales,
        "flow_lean": lean,
        "proxy_signal": lean,
        "holders": holder_rows[:10],
        "recent_trades": trades[:8],
        "interpretation": _congress_interpretation(lean, purchases, sales),
    }


def _congress_interpretation(lean: str, purchases: int, sales: int) -> str:
    if lean == "accumulation":
        return f"Lawmakers leaning net buyers ({purchases} purchases vs {sales} sales) — mild bullish proxy."
    if lean == "distribution":
        return f"Lawmakers leaning net sellers ({sales} sales vs {purchases} purchases) — caution proxy."
    return "No clear congressional flow signal in cached disclosures."


# Alias for older callers
load_congress_activity = load_congress_holdings_proxy


def x_opinion_block(view: XMarketView | None) -> dict[str, Any]:
    """X layer focused on entry/target prices and crowd opinion."""
    if view is None or view.post_count <= 0:
        return {
            "status": "skipped",
            "hint": "X layer disabled — playbook uses price replay + Congress only.",
        }
    parts = [view.opinion]
    if view.entry_zone:
        parts.append(f"Entry zone discussed: {view.entry_zone}")
    if view.target_zone:
        parts.append(f"Targets discussed: {view.target_zone}")
    return {
        "status": "ok",
        **view.as_dict(),
        "summary": " | ".join(parts),
    }


def _load_fmp_social(ticker: str) -> dict[str, Any]:
    try:
        from trading.stocks.fmp_social import fetch_social_sentiment

        return fetch_social_sentiment(ticker)
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "error": str(exc)}


def live_options_snapshot(
    ticker: str,
    *,
    analyzer: Any | None = None,
    days_to_exp: int = 30,
) -> dict[str, Any]:
    """Current options engine view (trade decision + executable setup)."""
    from options.analyzer import OptionsAnalyzer

    sym = ticker.upper()
    try:
        engine = analyzer or OptionsAnalyzer()
        payload = engine.run(ticker=sym, days_to_exp=days_to_exp)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}

    overlay = payload.get("analysis_overlay") or {}
    decision = overlay.get("trade_decision") or {}
    executable = (overlay.get("final_recommendations") or {}).get(
        "best_overall_executable_setup"
    ) or {}
    metrics = executable.get("metrics") or {}
    underlying = payload.get("underlying_analysis") or {}

    return {
        "status": "ok",
        "trade_decision": decision.get("status"),
        "open_recommended": decision.get("open_recommended"),
        "strategy": executable.get("strategy_name"),
        "bias": executable.get("bias"),
        "pop": metrics.get("pop"),
        "touch": metrics.get("probability_of_touch"),
        "expected_value": metrics.get("expected_value"),
        "composite_score": metrics.get("composite_score"),
        "price": underlying.get("price"),
        "iv_rank": (underlying.get("implied_volatility") or {}).get("iv_rank"),
    }


def build_ticker_profile(
    ticker: str,
    *,
    price_series: Any | None = None,
    replay_rows: list[Mapping[str, Any]] | None = None,
    extra_replay_rows: list[Mapping[str, Any]] | None = None,
    walkforward: Mapping[str, Any] | None = None,
    x_index: Mapping[str, XMarketView] | None = None,
    congress_reports_dir: Path | None = None,
    include_live_options: bool = False,
    analyzer: Any | None = None,
) -> dict[str, Any]:
    """Full playbook card for one ticker."""
    sym = ticker.strip().upper()
    x_index = x_index if x_index is not None else load_x_market_index()

    price_block = (
        analyze_price_behavior(price_series)
        if price_series is not None
        else {"status": "no_series"}
    )
    all_rows = list(replay_rows or []) + list(extra_replay_rows or [])
    setup_block = summarize_setup_performance(all_rows, sym)
    from options.ticker_strategy import INCOME_STRATEGIES

    learned_block = learn_ticker_strategy(
        all_rows,
        sym,
        bias_20d=str(price_block.get("bias_20d") or "neutral"),
        bias_60d=str(price_block.get("bias_60d") or "neutral"),
        move_style=str(price_block.get("move_style") or "range_bound"),
    )
    income_learned = learn_ticker_strategy(
        all_rows,
        sym,
        bias_20d=str(price_block.get("bias_20d") or "neutral"),
        bias_60d=str(price_block.get("bias_60d") or "neutral"),
        move_style=str(price_block.get("move_style") or "range_bound"),
        strategies=INCOME_STRATEGIES,
    )
    learned_block["income_playbook"] = income_learned
    if walkforward:
        learned_block["walkforward"] = dict(walkforward)
        if walkforward.get("narrative"):
            learned_block["narrative"] = (
                f"{learned_block.get('narrative', '')} {walkforward['narrative']}"
            ).strip()
    learned_block = apply_merge_gate(income_learned, learned_block.get("walkforward"))
    learned_block["merge_scope"] = "income_playbook"
    congress_block = load_congress_holdings_proxy(sym, reports_dir=congress_reports_dir)
    x_block = x_opinion_block(x_index.get(sym))

    fmp_social_block = _load_fmp_social(sym)

    profile: dict[str, Any] = {
        "ticker": sym,
        "registry_version": REGISTRY_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "price_behavior": price_block,
        "setup_performance": setup_block,
        "learned_strategy": learned_block,
        "x_opinion": x_block,
        "fmp_social_sentiment": fmp_social_block,
        "congress_holdings": congress_block,
        "congress": congress_block,
        "playbook": _synthesize_playbook(
            sym,
            price=price_block,
            setups=setup_block,
            learned=learned_block,
            x=x_block,
            congress=congress_block,
        ),
    }
    if include_live_options:
        profile["live_options"] = live_options_snapshot(sym, analyzer=analyzer)
    return profile


def _synthesize_playbook(
    ticker: str,
    *,
    price: Mapping[str, Any],
    setups: Mapping[str, Any],
    learned: Mapping[str, Any],
    x: Mapping[str, Any],
    congress: Mapping[str, Any],
) -> dict[str, Any]:
    """Actionable summary tying behavior + per-ticker learned setup + Congress."""
    bias = price.get("bias_20d") or "neutral"
    merge = learned.get("merge") or {}
    primary = learned.get("primary") or {}
    best_strat = (
        learned.get("validated_setup")
        or merge.get("validated_setup")
        or primary.get("strategy")
        or setups.get("best_strategy")
    )
    merge_status = merge.get("merge_status", "reject")
    rules: list[str] = []

    if learned.get("narrative"):
        rules.append(str(learned["narrative"]))
    elif best_strat:
        rules.append(f"Learned setup for {ticker}: {best_strat}.")
    else:
        rules.append("Collect replay data before sizing income trades.")

    for item in learned.get("avoid") or []:
        rules.append(f"Avoid on {ticker}: {item.get('strategy')} — {item.get('reason')}")

    exec_block = learned.get("execution") or {}
    if exec_block.get("size"):
        rules.append(f"Size guidance: {exec_block['size']}.")

    if price.get("move_style") == "high_volatility":
        rules.append("Use wider spreads; avoid tight short strikes.")
    if price.get("move_style") == "trending":
        rules.append("Align direction with 20d/60d trend before selling premium.")

    if x.get("entry_zone"):
        rules.append(f"X entry zone: {x['entry_zone']} — align short strikes / spreads accordingly.")
    if x.get("target_zone"):
        rules.append(f"X price targets: {x['target_zone']} — use for profit-taking context.")
    x_sent = x.get("sentiment")
    if x.get("opinion"):
        rules.append(str(x["opinion"]))
    elif x_sent and x_sent != "neutral":
        rules.append(f"X crowd currently {x_sent}; confirm before fading the tape.")

    flow = congress.get("proxy_signal") or congress.get("flow_lean")
    if flow and flow != "neutral":
        rules.append(congress.get("interpretation") or f"Congress proxy: {flow}.")

    rules.append(f"Merge status: {merge_status} — only size approved setups at full weight.")
    if merge_status == "approved":
        rules.append(
            "Approved horizon is walk-forward replay (multi-month), not this week — "
            "confirm live options bias matches primary or by_bias before full size."
        )
    if merge_status != "approved":
        rules.append("Use half size or paper-trade until OOS confirms this ticker.")

    return {
        "bias_20d": bias,
        "preferred_setup": best_strat,
        "merge_status": merge_status,
        "validated_setup": learned.get("validated_setup"),
        "learned_confidence": learned.get("confidence"),
        "learned_edge_score": primary.get("edge_score"),
        "setup_by_bias": learned.get("by_bias"),
        "setup_note": setups.get("recommendation"),
        "behavior_note": price.get("typical_behavior"),
        "rules": rules,
    }


def load_yearly_replay_rows(path: Path | None = None) -> list[dict[str, Any]]:
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8")).get("rows") or []
    raw = Path(__file__).resolve().parents[1] / "docs" / "analysis" / "raw"
    candidates = sorted(raw.glob("options_yearly_*.json"))
    if not candidates:
        return []
    return json.loads(candidates[-1].read_text(encoding="utf-8")).get("rows") or []


def build_registry(
    tickers: list[str] | None = None,
    *,
    paths: RegistryPaths | None = None,
    replay_json: Path | None = None,
    include_live_options: bool = False,
    workers: int = 1,
    extra_rows: list[Mapping[str, Any]] | None = None,
    walkforward_by_ticker: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build or refresh the full top-40 registry on disk."""
    symbols = [t.strip().upper() for t in (tickers or SP500_TOP_40_TICKERS) if t.strip()]
    paths = paths or RegistryPaths(DEFAULT_REGISTRY_DIR)
    paths.root.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).date()
    hist_start = today - timedelta(days=400)
    price_history = bulk_price_history(symbols, start=hist_start, end=today)
    replay_rows = load_yearly_replay_rows(replay_json)
    x_index = load_x_market_index()
    wf_map = walkforward_by_ticker or {}

    profiles: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        sym_extra = [
            r for r in (extra_rows or []) if str(r.get("ticker") or "").upper() == sym
        ]
        profiles[sym] = build_ticker_profile(
            sym,
            price_series=price_history.get(sym),
            replay_rows=replay_rows,
            extra_replay_rows=sym_extra,
            walkforward=wf_map.get(sym),
            x_index=x_index,
            include_live_options=include_live_options,
        )
        paths.ticker_path(sym).write_text(
            json.dumps(profiles[sym], indent=2, default=str),
            encoding="utf-8",
        )

    index = {
        "registry_version": REGISTRY_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tickers": symbols,
        "replay_source": str(replay_json) if replay_json else "latest options_yearly_*.json",
        "profiles": {
            sym: {
                "file": paths.ticker_path(sym).name,
                "bias_20d": profiles[sym]["playbook"].get("bias_20d"),
                "preferred_setup": profiles[sym]["playbook"].get("preferred_setup"),
                "merge_status": profiles[sym]["playbook"].get("merge_status"),
                "learned_confidence": profiles[sym]["playbook"].get("learned_confidence"),
                "learned_edge_score": profiles[sym]["playbook"].get("learned_edge_score"),
                "oos_win_rate": (
                    (profiles[sym].get("learned_strategy") or {})
                    .get("walkforward", {})
                    .get("oos_win_rate")
                ),
                "best_win_rate": (profiles[sym]["setup_performance"] or {}).get("best_win_rate"),
                "x_status": (profiles[sym]["x_opinion"] or {}).get("status"),
                "congress_mentions": (profiles[sym]["congress"] or {}).get("mentions", 0),
            }
            for sym in symbols
        },
    }
    paths.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return {"index": index, "profiles": profiles, "paths": {"root": str(paths.root)}}


def load_registry(paths: RegistryPaths | None = None) -> dict[str, Any]:
    paths = paths or RegistryPaths(DEFAULT_REGISTRY_DIR)
    if not paths.index_path.is_file():
        return {"status": "missing", "hint": "Run: nave options registry build"}
    index = json.loads(paths.index_path.read_text(encoding="utf-8"))
    return {"status": "ok", "index": index, "root": str(paths.root)}


def load_ticker_profile(ticker: str, paths: RegistryPaths | None = None) -> dict[str, Any] | None:
    paths = paths or RegistryPaths(DEFAULT_REGISTRY_DIR)
    path = paths.ticker_path(ticker)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))