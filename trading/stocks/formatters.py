"""Telegram-ready MarkdownV2 formatters for stock workflows."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from trading.stocks.politicians.formatters import escape_markdown_v2


def render_ism_report_markdown_v2(
    payload: Mapping[str, Any],
    *,
    max_message_chars: int = 3500,
) -> list[str]:
    """Render an ISM report payload as Telegram-ready MarkdownV2 chunks."""
    kind = str(payload.get("kind") or "ism").upper()
    report_month = str(payload.get("report_month") or "?")
    criteria = payload.get("criteria") or {}
    candidates = payload.get("candidates") or {}
    lines = [f"*NAVE ISM {escape_markdown_v2(kind)}*"]
    lines.append(f"Month: {escape_markdown_v2(report_month)}")
    pmi = payload.get("pmi")
    if pmi is not None:
        lines.append(f"PMI: *{escape_markdown_v2(str(pmi))}*")
    if isinstance(criteria, Mapping):
        lines.append(
            "Criteria: "
            f"top n {escape_markdown_v2(str(criteria.get('top_n', '?')))}, "
            f"min conf {escape_markdown_v2(str(criteria.get('min_confidence', '?')))}"
        )
    freshness_status = payload.get("freshness_status")
    expected_covers_month = payload.get("expected_covers_month")
    if freshness_status is not None:
        freshness = f"Freshness: *{escape_markdown_v2(str(freshness_status))}*"
        if expected_covers_month:
            freshness += (
                " expected "
                f"{escape_markdown_v2(str(expected_covers_month))}"
            )
        lines.append(freshness)

    blocks: list[str] = ["\n".join(lines)]
    blocks.append(
        _candidate_block(
            title="Top longs",
            rows=_candidate_rows(candidates, "longs", "expanding"),
        )
    )
    blocks.append(
        _candidate_block(
            title="Top shorts",
            rows=_candidate_rows(candidates, "shorts", "contracting"),
        )
    )
    blocks.append(
        _candidate_block(
            title="Ondo-shortable shorts",
            rows=_candidate_rows(candidates, "ondo_shorts", "contracting"),
        )
    )
    return _chunk_blocks(blocks, max_message_chars=max_message_chars)


def render_x_summary_markdown_v2(
    payload: Mapping[str, Any],
    *,
    max_message_chars: int = 3500,
) -> list[str]:
    """Render a deterministic X summary digest suitable for Telegram delivery."""
    tickers = [str(t).upper() for t in payload.get("tickers") or []]
    summary_stats = payload.get("summary_stats") or {}
    fetch_errors = payload.get("fetch_errors") or {}
    blocks = [
        "\n".join(
            [
                "*NAVE X digest*",
                f"Tickers: {escape_markdown_v2(', '.join(tickers) or '?')}",
                (
                    "Window: "
                    f"{escape_markdown_v2(str(payload.get('days', '?')))}d"
                    ", Posts: "
                    f"{escape_markdown_v2(str(payload.get('total_posts', '?')))}"
                ),
                (
                    "Fallback: use this digest directly if the richer LLM analysis "
                    "path is rate\\-limited\\."
                ),
            ]
        )
    ]

    for ticker in tickers:
        stats = summary_stats.get(ticker) if isinstance(summary_stats, Mapping) else {}
        if not isinstance(stats, Mapping):
            stats = {}
        lines = [
            f"*{escape_markdown_v2(ticker)}*",
            (
                "posts: "
                f"{escape_markdown_v2(str(stats.get('post_count', 0)))} "
                "likes: "
                f"{escape_markdown_v2(str(stats.get('total_likes', 0)))} "
                "replies: "
                f"{escape_markdown_v2(str(stats.get('total_replies', 0)))} "
                "retweets: "
                f"{escape_markdown_v2(str(stats.get('total_retweets', 0)))}"
            ),
        ]
        top_post_url = stats.get("top_post_url")
        if top_post_url:
            lines.append(f"Top post: {escape_markdown_v2(str(top_post_url))}")
        error = fetch_errors.get(ticker) if isinstance(fetch_errors, Mapping) else None
        if error:
            lines.append(f"Fetch error: {escape_markdown_v2(str(error))}")
        blocks.append("\n".join(lines))

    return _chunk_blocks(blocks, max_message_chars=max_message_chars)


def _candidate_rows(
    candidates: Any,
    primary_key: str,
    fallback_key: str,
) -> list[Mapping[str, Any]]:
    if not isinstance(candidates, Mapping):
        return []
    rows = candidates.get(primary_key)
    if rows is None:
        rows = candidates.get(fallback_key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _candidate_block(title: str, rows: list[Mapping[str, Any]]) -> str:
    lines = [f"*{escape_markdown_v2(title)}*"]
    if not rows:
        lines.append("none")
        return "\n".join(lines)
    for row in rows[:5]:
        symbol = escape_markdown_v2(str(row.get("symbol") or "?"))
        sector = escape_markdown_v2(str(row.get("sector") or "?"))
        side = escape_markdown_v2(str(row.get("side") or "?"))
        score = escape_markdown_v2(str(row.get("score") or "?"))
        confidence = escape_markdown_v2(str(row.get("confidence") or "?"))
        driver = escape_markdown_v2(str(row.get("driver_industry") or "?"))
        lines.append(
            f"*{symbol}* {side}, sector: {sector}, score: {score}, conf: {confidence}, driver: {driver}"
        )
    return "\n".join(lines)


def _chunk_blocks(
    blocks: Iterable[str],
    *,
    max_message_chars: int,
) -> list[str]:
    chunks: list[str] = []
    current = ""
    for block in blocks:
        if not block:
            continue
        candidate = block if not current else f"{current}\n\n{block}"
        if current and len(candidate) > max_message_chars:
            chunks.append(current)
            current = block
            continue
        current = candidate
    if current:
        chunks.append(current)
    return chunks


__all__ = [
    "render_ism_report_markdown_v2",
    "render_x_summary_markdown_v2",
]
