"""Presentation formatters for politician STOCK Act scan payloads.

This module keeps scanner payloads machine-stable while offering an optional,
Telegram-ready MarkdownV2 digest that is easier for humans to scan.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_MD_V2_SPECIALS_RE = re.compile(r"([_*\[\]()~`>#+\-=|{}.!])")


def escape_markdown_v2(value: Any) -> str:
    """Escape user/content text for Telegram MarkdownV2."""
    if value is None:
        return ""
    return _MD_V2_SPECIALS_RE.sub(r"\\\1", str(value))


def _escape_markdown_v2_url(url: str) -> str:
    # Telegram MarkdownV2 inline links are sensitive to parentheses/backslashes.
    return str(url).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_politicians_scan_markdown_v2(
    payload: dict[str, Any],
    *,
    max_message_chars: int = 3800,
    include_empty: bool = False,
) -> list[str]:
    """Render scan payload as one or more Telegram MarkdownV2 messages."""
    if max_message_chars < 500:
        raise ValueError("max_message_chars must be at least 500")

    new_trades = payload.get("new_trades") if isinstance(payload, dict) else None
    if not isinstance(new_trades, list) or not new_trades:
        if not include_empty:
            return []
        return [
            "*NAVE STOCK Act*\n"
            "No hay disclosures nuevas en este escaneo\\."
        ]

    summary = payload.get("summary") if isinstance(payload, dict) else {}
    if not isinstance(summary, dict):
        summary = {}

    blocks: list[str] = []
    blocks.append(_build_header_block(payload, summary, new_trades))

    top_symbols_block = _build_top_symbols_block(summary)
    if top_symbols_block:
        blocks.append(top_symbols_block)

    for group in _group_and_sort_trades(new_trades):
        blocks.append(_build_group_block(group))

    blocks.append(
        escape_markdown_v2(
            "Recordatorio: disclosures STOCK Act pueden publicarse con hasta 45 dias "
            "de demora; no es una senal de trading inmediata."
        )
    )

    fragments: list[str] = []
    for block in blocks:
        fragments.extend(_split_block_lines(block, max_chars=max_message_chars))

    messages = _pack_fragments(fragments, max_chars=max_message_chars)
    if len(messages) <= 1:
        return messages

    # Reserve headroom for the part label so each final message still fits.
    part_headroom = 24
    effective_limit = max(500, max_message_chars - part_headroom)
    messages = _pack_fragments(fragments, max_chars=effective_limit)

    total = len(messages)
    with_parts: list[str] = []
    for idx, message in enumerate(messages, start=1):
        with_parts.append(f"*Parte {idx}/{total}*\n{message}")
    return with_parts


def _build_header_block(
    payload: dict[str, Any],
    summary: dict[str, Any],
    trades: list[dict[str, Any]],
) -> str:
    generated_at = str(payload.get("generated_at") or "")
    generated_display = generated_at.replace("T", " ").replace("+00:00", " UTC") if generated_at else "N/A"

    raw_by_type = summary.get("by_type")
    by_type: dict[str, Any] = raw_by_type if isinstance(raw_by_type, dict) else {}
    raw_by_chamber = summary.get("by_chamber")
    by_chamber: dict[str, Any] = (
        raw_by_chamber if isinstance(raw_by_chamber, dict) else {}
    )

    buys = 0
    sells = 0
    for key, raw_value in by_type.items():
        key_lower = str(key).lower()
        value = _safe_int(raw_value)
        if "purchase" in key_lower:
            buys += value
        elif "sale" in key_lower:
            sells += value

    unique_politicians = _safe_int(summary.get("unique_politicians"))
    if unique_politicians <= 0:
        unique_politicians = len({str(t.get("politician") or "") for t in trades if t.get("politician")})

    house_count = _safe_int(by_chamber.get("house"))
    senate_count = _safe_int(by_chamber.get("senate"))
    new_total = _safe_int(payload.get("new_total"))

    return "\n".join(
        [
            "*NAVE STOCK Act*",
            f"Escaneo: {escape_markdown_v2(generated_display)}",
            (
                f"Nuevas disclosures: *{new_total}* \\| "
                f"Compras: *{buys}* \\| Ventas: *{sells}*"
            ),
            (
                f"Politicos unicos: *{unique_politicians}* \\| "
                f"Camara: *{house_count}* \\| Senado: *{senate_count}*"
            ),
        ]
    )


def _build_top_symbols_block(summary: dict[str, Any]) -> str:
    top_symbols = summary.get("top_symbols")
    if not isinstance(top_symbols, list) or not top_symbols:
        return ""

    lines = ["*Top symbols*:"]
    for item in top_symbols[:10]:
        if not isinstance(item, dict):
            continue
        symbol = escape_markdown_v2(item.get("symbol") or "?")
        count = _safe_int(item.get("count"))
        lines.append(f"\\- *{symbol}*: {count}")
    return "\n".join(lines)


def _group_and_sort_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for trade in trades:
        chamber = str(trade.get("chamber") or "").lower()
        politician = str(trade.get("politician") or "Unknown")
        state = str(trade.get("state") or "")
        link = str(trade.get("link") or "")
        key = (chamber, politician, state, link)
        groups.setdefault(key, []).append(trade)

    ranked: list[dict[str, Any]] = []
    for (chamber, politician, state, link), items in groups.items():
        max_amount = max(_amount_upper_bound(item.get("amount_range")) for item in items)
        max_disclosure = max(_date_rank(item.get("disclosure_date")) for item in items)
        ranked.append(
            {
                "chamber": chamber,
                "politician": politician,
                "state": state,
                "link": link,
                "items": items,
                "max_amount": max_amount,
                "max_disclosure": max_disclosure,
            }
        )

    ranked.sort(
        key=lambda group: (
            -int(group["max_amount"]),
            -int(group["max_disclosure"]),
            str(group["politician"]).lower(),
        )
    )
    return ranked


def _build_group_block(group: dict[str, Any]) -> str:
    chamber = str(group.get("chamber") or "")
    chamber_label = "Senado" if chamber == "senate" else "Camara"
    politician = escape_markdown_v2(group.get("politician") or "Unknown")
    state = str(group.get("state") or "")
    state_label = escape_markdown_v2(state) if state else "N/A"

    lines = [f"*{politician}*", f"{escape_markdown_v2(chamber_label)}, {state_label}"]

    link = str(group.get("link") or "")
    if link:
        lines.append(f"[Fuente]({_escape_markdown_v2_url(link)})")

    symbol_rows = _aggregate_symbol_rows(group.get("items") or [])
    for row in symbol_rows:
        symbol = escape_markdown_v2(row["symbol"])
        description = escape_markdown_v2(row["asset_description"]) if row["asset_description"] else ""
        amount = escape_markdown_v2(_compact_join(row["amounts"]))
        tx_dates = escape_markdown_v2(_compact_join(row["transaction_dates"], limit=3))
        disclosure_dates = escape_markdown_v2(_compact_join(row["disclosure_dates"], limit=2))

        entry = f"\\- *{symbol}*"
        if description:
            entry += f" {description}"
        if amount:
            entry += f" \\| monto: {amount}"
        if tx_dates:
            entry += f" \\| tx: {tx_dates}"
        if disclosure_dates:
            entry += f" \\| disclosure: {disclosure_dates}"
        if row["count"] > 1:
            entry += f" \\| x{row['count']}"
        lines.append(entry)

    return "\n".join(lines)


def _aggregate_symbol_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in items:
        symbol = str(item.get("symbol") or "?")
        row = rows.setdefault(
            symbol,
            {
                "symbol": symbol,
                "asset_description": str(item.get("asset_description") or ""),
                "amounts": set(),
                "transaction_dates": set(),
                "disclosure_dates": set(),
                "count": 0,
                "max_amount": 0,
                "max_disclosure": 0,
            },
        )
        amount = str(item.get("amount_range") or "").strip()
        if amount:
            row["amounts"].add(amount)
            row["max_amount"] = max(int(row["max_amount"]), _amount_upper_bound(amount))

        tx_date = str(item.get("transaction_date") or "").strip()
        if tx_date:
            row["transaction_dates"].add(tx_date)

        disclosure_date = str(item.get("disclosure_date") or "").strip()
        if disclosure_date:
            row["disclosure_dates"].add(disclosure_date)
            row["max_disclosure"] = max(int(row["max_disclosure"]), _date_rank(disclosure_date))

        if not row["asset_description"] and item.get("asset_description"):
            row["asset_description"] = str(item.get("asset_description") or "")

        row["count"] = int(row["count"]) + 1

    output = list(rows.values())
    for row in output:
        row["amounts"] = sorted(row["amounts"], key=_amount_upper_bound, reverse=True)
        row["transaction_dates"] = sorted(row["transaction_dates"], reverse=True)
        row["disclosure_dates"] = sorted(row["disclosure_dates"], reverse=True)

    output.sort(
        key=lambda row: (
            -int(row["max_amount"]),
            -int(row["max_disclosure"]),
            str(row["symbol"]).lower(),
        )
    )
    return output


def _split_block_lines(block: str, *, max_chars: int) -> list[str]:
    if len(block) <= max_chars:
        return [block]

    out: list[str] = []
    current = ""
    for line in block.splitlines():
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            out.append(current)
        if len(line) <= max_chars:
            current = line
            continue
        start = 0
        while start < len(line):
            out.append(line[start:start + max_chars])
            start += max_chars
        current = ""

    if current:
        out.append(current)
    return out


def _pack_fragments(fragments: list[str], *, max_chars: int) -> list[str]:
    out: list[str] = []
    current = ""
    for fragment in fragments:
        candidate = fragment if not current else f"{current}\n\n{fragment}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            out.append(current)
        current = fragment
    if current:
        out.append(current)
    return out


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _amount_upper_bound(amount_range: Any) -> int:
    if not amount_range:
        return 0
    numbers = re.findall(r"([0-9][0-9,]*)", str(amount_range))
    if not numbers:
        return 0
    return max(int(number.replace(",", "")) for number in numbers)


def _date_rank(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return parsed.year * 10000 + parsed.month * 100 + parsed.day


def _compact_join(values: list[str], *, limit: int = 2) -> str:
    if not values:
        return ""
    if len(values) <= limit:
        return " / ".join(values)
    remaining = len(values) - limit
    head = " / ".join(values[:limit])
    return f"{head} (+{remaining} mas)"


__all__ = ["escape_markdown_v2", "render_politicians_scan_markdown_v2"]
