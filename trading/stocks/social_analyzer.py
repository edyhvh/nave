"""
Social sentiment analyzer for ISM-screened stocks.

Decoupled from the screener on purpose — fetching X posts is slow and
requires logged-in accounts, so users invoke this explicitly via
``nave stocks x-analyze`` or via the Hermes ``stocks_x_analyze`` tool. The
analyzer ships with the LLM analysis prompt baked into the payload, so
the calling agent (Telegram-side LLM, manual paste into Claude/ChatGPT)
has everything needed to produce the final markdown report.

Two output paths:
- JSON payload (machine-readable, persisted to ``stocks_history/``)
- Rich-table sheet (terminal-readable; computed from the same payload)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from trading.stocks.x_client import (
    DEFAULT_LIMIT_PER_TICKER,
    DEFAULT_LOOKBACK_DAYS,
    XClient,
    XClientError,
    XPost,
)

logger = logging.getLogger(__name__)


X_POSTS_ANALYSIS_SYSTEM_PROMPT = """You are an expert financial analyst specialized in interpreting real-time crowd sentiment from X (Twitter) about stocks.

The user has already fetched recent posts about one or more stock tickers. Your job is to analyze them and produce a clear, actionable, and well-structured report.

### INPUT FORMAT YOU WILL RECEIVE:
- Ticker(s)
- Number of days analyzed
- List of raw posts. Each post includes: text, username, date, likes, replies, reposts, views, etc.

### WHAT YOU MUST DO:
1. Read all the provided posts carefully.
2. Identify patterns, consensus, and contradictions.
3. Extract meaningful investment signals (not just generic sentiment).
4. Produce a professional, easy-to-read report.

### OUTPUT RULES:
- Respond in clear, natural Markdown format (headings, bullet points, tables if useful).
- Be objective, bold, and honest. Call out hype, panic, or low-quality discussion when you see it.
- Use real quotes from the posts to support your points.
- Keep the tone professional but conversational (suitable for a monthly investment ranking).

### REQUIRED SECTIONS (use exactly these headings, one block per ticker):

## 1. Ticker: [TICKER] - Overview
(Short summary: total posts, time period, general vibe)

## 2. Overall Sentiment
- Bullish / Bearish / Mixed / Neutral
- Approximate split (% bullish vs bearish)
- Confidence level (High / Medium / Low)

## 3. Key Fundamentals & Topics People Are Talking About
- List the top 5-7 things mentioned (with how often and tone)
- Examples: earnings, AI growth, debt, valuation, competition, new products, etc.

## 4. Perceived Valuation
- Do people think the stock is undervalued, fair, or overvalued?
- Any specific price levels or multiples discussed?

## 5. Entry Points & Price Discussion
- Most mentioned buy zones or target prices
- Contexts (e.g. "buy the dip under $XXX", "target $YYY by end of year")

## 6. Risks & Concerns Mentioned
- Main worries or bearish arguments

## 7. Actionable Insight for Investor
- One clear paragraph: Should someone consider buying now, waiting for a dip, or avoiding? Why?

## 8. Notable Quotes
- 3-5 exact quotes that best represent the current conversation (include username if relevant)

## 9. Final Recommendation
- strong_buy | buy | buy_on_dip | hold | wait | avoid
- One-sentence justification
"""


X_POSTS_ANALYSIS_USER_TEMPLATE = """Now analyze the following data:

Ticker(s): {tickers}
Period: last {days} days
Total posts analyzed: {total_posts}

Raw posts:
{raw_posts}
"""


def analyze_tickers(
    tickers: Sequence[str],
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    limit_per_ticker: int = DEFAULT_LIMIT_PER_TICKER,
    client: XClient | None = None,
    persist: bool = True,
    snapshot_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Sync wrapper around :func:`analyze_tickers_async`.

    Use this from CLI entrypoints. Hermes tool handlers may call either
    flavor — the async version is preferable inside an event loop.
    """
    return asyncio.run(
        analyze_tickers_async(
            tickers,
            days=days,
            limit_per_ticker=limit_per_ticker,
            client=client,
            persist=persist,
            snapshot_dir=snapshot_dir,
        )
    )


async def analyze_tickers_async(
    tickers: Sequence[str],
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    limit_per_ticker: int = DEFAULT_LIMIT_PER_TICKER,
    client: XClient | None = None,
    persist: bool = True,
    snapshot_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Fetch posts for each ticker, package with the LLM analysis prompt.

    Returns a fully serializable payload an external LLM can consume
    directly (the analysis prompt is baked in under ``analysis_prompt``).
    """
    normalized = _normalize_tickers(tickers)
    if not normalized:
        raise ValueError("at least one ticker is required")

    x = client or XClient()
    posts_by_ticker: dict[str, list[XPost]] = {}
    fetch_errors: dict[str, str] = {}
    for ticker in normalized:
        try:
            posts_by_ticker[ticker] = await x.fetch_recent_posts(
                ticker, days=days, limit=limit_per_ticker
            )
        except XClientError as exc:
            logger.warning("X fetch failed for %s: %s", ticker, exc)
            posts_by_ticker[ticker] = []
            fetch_errors[ticker] = str(exc)

    total_posts = sum(len(p) for p in posts_by_ticker.values())
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tickers": normalized,
        "days": days,
        "limit_per_ticker": limit_per_ticker,
        "total_posts": total_posts,
        "summary_stats": _summary_stats(posts_by_ticker),
        "posts_by_ticker": {
            ticker: [p.as_dict() for p in posts]
            for ticker, posts in posts_by_ticker.items()
        },
        "fetch_errors": fetch_errors,
        "analysis_prompt": _build_analysis_prompt(
            normalized, days=days, total_posts=total_posts, posts_by_ticker=posts_by_ticker
        ),
    }

    if persist:
        path = _persist_snapshot(payload, snapshot_dir=snapshot_dir)
        payload["saved_to"] = str(path)
    return payload


def _build_analysis_prompt(
    tickers: list[str],
    *,
    days: int,
    total_posts: int,
    posts_by_ticker: Mapping[str, list[XPost]],
) -> dict[str, str]:
    """Render the system + user prompt the calling LLM should run."""
    return {
        "system": X_POSTS_ANALYSIS_SYSTEM_PROMPT,
        "user": X_POSTS_ANALYSIS_USER_TEMPLATE.format(
            tickers=", ".join(tickers),
            days=days,
            total_posts=total_posts,
            raw_posts=_render_posts_for_prompt(posts_by_ticker),
        ),
        "instructions_for_caller": (
            "Send `system` as the system prompt and `user` as the user "
            "message to your LLM of choice. The model will return the "
            "markdown report described in the system prompt."
        ),
    }


def _render_posts_for_prompt(posts_by_ticker: Mapping[str, list[XPost]]) -> str:
    """Compact, LLM-friendly serialization of the post corpus."""
    blocks: list[str] = []
    for ticker, posts in posts_by_ticker.items():
        blocks.append(f"### {ticker} ({len(posts)} posts)")
        if not posts:
            blocks.append("  (no posts fetched)")
            continue
        for post in posts:
            blocks.append(
                f"- @{post.username} | {post.created_at} | "
                f"likes={post.likes} replies={post.replies} "
                f"retweets={post.retweets} views={post.views}\n"
                f"  {post.text}"
            )
    return "\n".join(blocks)


def _summary_stats(posts_by_ticker: Mapping[str, list[XPost]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for ticker, posts in posts_by_ticker.items():
        if not posts:
            out[ticker] = {
                "post_count": 0,
                "total_likes": 0,
                "total_replies": 0,
                "total_retweets": 0,
                "top_post_url": None,
            }
            continue
        top = max(posts, key=lambda p: (p.likes, p.retweets, p.replies))
        out[ticker] = {
            "post_count": len(posts),
            "total_likes": sum(p.likes for p in posts),
            "total_replies": sum(p.replies for p in posts),
            "total_retweets": sum(p.retweets for p in posts),
            "top_post_url": top.url or None,
        }
    return out


def _persist_snapshot(
    payload: Mapping[str, Any],
    *,
    snapshot_dir: str | Path | None,
) -> Path:
    root = Path(snapshot_dir) if snapshot_dir is not None else _default_snapshot_dir()
    root.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tickers = list(payload.get("tickers") or [])
    suffix = _ticker_suffix(tickers)
    path = root / f"x_analysis_{today}_{suffix}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def _ticker_suffix(tickers: list[str]) -> str:
    """Stable, filesystem-safe suffix for a (potentially long) ticker set."""
    if not tickers:
        return "none"
    if len(tickers) <= 4:
        return "-".join(t.lower() for t in tickers)
    digest = hashlib.sha1("|".join(tickers).encode("utf-8")).hexdigest()[:8]
    return f"{tickers[0].lower()}-and-{len(tickers) - 1}-more-{digest}"


def _normalize_tickers(tickers: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in tickers:
        sym = str(raw).strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _default_snapshot_dir() -> Path:
    # Repo-committed alongside ISM monthly snapshots.
    return Path(__file__).resolve().parents[2] / "stocks_history"


def render_sheet(payload: Mapping[str, Any]) -> None:
    """Pretty-print the payload as Rich tables for terminal consumption."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(
        f"[bold]X social analysis[/bold] — {payload.get('generated_at', '?')}"
    )
    tickers = payload.get("tickers") or []
    console.print(
        f"Tickers: {', '.join(tickers)}  |  days={payload.get('days')}  "
        f"|  total_posts={payload.get('total_posts')}"
    )
    if payload.get("saved_to"):
        console.print(f"Saved: {payload['saved_to']}")
    fetch_errors = payload.get("fetch_errors") or {}
    if fetch_errors:
        console.print(
            f"[yellow]Fetch errors:[/yellow] {len(fetch_errors)} ticker(s) — "
            f"{', '.join(fetch_errors)}"
        )

    stats_table = Table(title="Per-ticker stats")
    stats_table.add_column("Ticker")
    stats_table.add_column("Posts", justify="right")
    stats_table.add_column("Likes", justify="right")
    stats_table.add_column("Replies", justify="right")
    stats_table.add_column("Retweets", justify="right")
    stats_table.add_column("Top post URL")
    summary = payload.get("summary_stats") or {}
    for ticker in tickers:
        row = summary.get(ticker, {})
        stats_table.add_row(
            ticker,
            str(row.get("post_count", 0)),
            str(row.get("total_likes", 0)),
            str(row.get("total_replies", 0)),
            str(row.get("total_retweets", 0)),
            str(row.get("top_post_url") or "—"),
        )
    console.print(stats_table)

    posts_by_ticker = payload.get("posts_by_ticker") or {}
    for ticker in tickers:
        posts = posts_by_ticker.get(ticker) or []
        if not posts:
            continue
        table = Table(title=f"{ticker} — top posts (by engagement)")
        table.add_column("When")
        table.add_column("@user")
        table.add_column("Likes", justify="right")
        table.add_column("RT", justify="right")
        table.add_column("Text")
        sorted_posts = sorted(
            posts,
            key=lambda p: (
                int(p.get("likes") or 0),
                int(p.get("retweets") or 0),
            ),
            reverse=True,
        )[:10]
        for post in sorted_posts:
            text = str(post.get("text") or "")
            if len(text) > 140:
                text = text[:137] + "…"
            table.add_row(
                str(post.get("created_at") or "?"),
                f"@{post.get('username', '')}",
                str(post.get("likes", 0)),
                str(post.get("retweets", 0)),
                text,
            )
        console.print(table)

    console.print(
        "\n[dim]Analysis prompt is included in the JSON payload under "
        "`analysis_prompt`. Pipe the JSON into your LLM (or paste the "
        "rendered system+user prompt) to generate the markdown report.[/dim]"
    )
