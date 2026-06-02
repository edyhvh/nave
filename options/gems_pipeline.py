"""Run equity scan + hidden-gem ranking (+ optional X fetch for shortlist)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from options.gem_finder import GemFilterConfig, rank_hidden_gems
from trading.stocks.x_interest import load_x_interest_index


def load_congress_tickers() -> frozenset[str]:
    root = Path(__file__).resolve().parents[1] / "var" / "reports" / "politicians"
    if not root.is_dir():
        return frozenset()
    reports = sorted(root.glob("*.json"), reverse=True)
    if not reports:
        return frozenset()
    try:
        import json

        payload = json.loads(reports[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    out: set[str] = set()
    for trade in payload.get("new_trades") or payload.get("trades") or []:
        sym = str(trade.get("symbol") or trade.get("ticker") or "").strip().upper()
        if sym:
            out.add(sym)
    return frozenset(out)


def fetch_x_for_tickers(tickers: list[str], *, days: int = 7, limit: int = 25) -> dict[str, Any] | None:
    """Fetch X posts for gem shortlist; returns None if twscrape unavailable."""
    if not tickers:
        return None
    try:
        from trading.stocks.social_analyzer import analyze_tickers
    except ImportError:
        return None
    try:
        return analyze_tickers(tickers[:12], days=days, limit_per_ticker=limit, persist=True)
    except Exception:
        return None


def run_hidden_gems_scan(
    scan_payload: dict[str, Any],
    *,
    congress_tickers: frozenset[str] | None = None,
    cfg: GemFilterConfig | None = None,
    filter_profile: str = "daily",
    top: int = 15,
    fetch_x_for_top: int = 0,
) -> dict[str, Any]:
    """Rank gems from an existing universe scan; optionally refresh X for top N."""
    congress = congress_tickers if congress_tickers is not None else load_congress_tickers()
    gem_payload = rank_hidden_gems(
        scan_payload,
        congress_tickers=congress,
        limit=top,
        cfg=cfg,
        filter_profile=filter_profile,
    )

    x_fetch: dict[str, Any] | None = None
    if fetch_x_for_top > 0:
        shortlist = [str(g["ticker"]) for g in gem_payload.get("gems") or []][:fetch_x_for_top]
        x_fetch = fetch_x_for_tickers(shortlist)
        if x_fetch is not None:
            x_index = load_x_interest_index()
            gem_payload = rank_hidden_gems(
                scan_payload,
                x_index=x_index,
                congress_tickers=congress,
                limit=top,
                cfg=cfg,
                filter_profile=filter_profile,
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hidden_gems": gem_payload,
        "congress_tickers": sorted(congress),
        "x_fetch": x_fetch,
    }


def format_gem_digest(gem_payload: dict[str, Any], *, max_lines: int = 8) -> str:
    """One-line-per-gem summary for daily reports."""
    gems = gem_payload.get("gems") or []
    watch = gem_payload.get("watchlist") or []
    scan_picks = gem_payload.get("scan_picks") or []
    if not gems:
        lines = ["Hidden gems: none passed gem filters today."]
        if watch:
            lines.append(f"Watchlist ({len(watch)}) — relaxed gates:")
            for item in watch[:max_lines]:
                metrics = item.get("metrics") or {}
                lines.append(
                    f"  ~ {item['ticker']} score={item.get('gem_score')} "
                    f"PoP={metrics.get('pop')}%"
                )
        if scan_picks:
            lines.append(f"Scan picks ({len(scan_picks)}) — top executable trades from universe:")
            for item in scan_picks[:max_lines]:
                lines.append(
                    f"  • {item['ticker']} {str(item.get('strategy') or '').replace('_', ' ')} "
                    f"score={item.get('composite_score')} PoP={item.get('pop')}%"
                )
        if not watch and not scan_picks:
            lines.append(
                "No trade_candidate rows in scan — try --limit 100 or "
                "nave options analyze --sp500-scan."
            )
        filt = gem_payload.get("filter") or {}
        profile = gem_payload.get("filter_profile") or "daily"
        lines.append(
            f"(profile={profile}, pop≥{filt.get('min_pop')}, touch<{filt.get('max_touch')})"
        )
        return "\n".join(lines)
    lines = [f"Hidden gems ({len(gems)} open, {len(watch)} watch):"]
    for item in gems[:max_lines]:
        metrics = item.get("metrics") or {}
        lines.append(
            f"• {item['ticker']} [{item.get('tier')}] score={item.get('gem_score')} "
            f"{str(item.get('strategy', '')).replace('_', ' ')} "
            f"PoP={metrics.get('pop')}% — {'; '.join((item.get('reasons') or [])[:2])}"
        )
    for item in watch[:3]:
        metrics = item.get("metrics") or {}
        lines.append(
            f"  ~ {item['ticker']} [watch] score={item.get('gem_score')} "
            f"PoP={metrics.get('pop')}%"
        )
    filt = gem_payload.get("filter") or {}
    lines.append(
        f"(filters: bullish bull-put, no bear-calls, pop≥{filt.get('min_pop')}, touch<{filt.get('max_touch')})"
    )
    return "\n".join(lines)