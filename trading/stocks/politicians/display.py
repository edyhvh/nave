"""Terminal display for Congressional disclosure scans."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _format_scan_time(iso: str | None) -> str:
    if not iso:
        return "never"
    return iso[:19].replace("T", " ") + " UTC"


def render_congress_scan(payload: dict[str, Any], *, console: Console | None = None) -> None:
    """Human-first view: new STOCK Act disclosures since the last run."""
    out = console or Console()
    previous = payload.get("previous_scan_at")
    new_total = int(payload.get("new_total") or 0)
    fetched = int(payload.get("fetched_total") or 0)
    generated = _format_scan_time(payload.get("generated_at"))

    headline = Text()
    if new_total:
        label = (
            f"{new_total} new disclosure"
            if new_total == 1
            else f"{new_total} new disclosures"
        )
        headline.append(label, style="bold green")
        headline.append(f" since {_format_scan_time(previous)}", style="")
    else:
        headline.append("No new disclosures", style="bold dim")
        headline.append(f" since {_format_scan_time(previous)}", style="dim")

    out.print(
        Panel(
            headline,
            title="[bold]Congressional trades[/bold]",
            subtitle=f"scanned {generated} · feed {fetched} rows · cache {payload.get('seen_total_after', 0)} seen",
        )
    )

    new_trades = payload.get("new_trades") or []
    if not new_trades:
        if previous is None:
            out.print(
                "[dim]First run recorded the current feed. Run again later to see only new filings.[/dim]"
            )
        return

    table = Table(show_header=True, header_style="bold", show_lines=False)
    table.add_column("Chamber")
    table.add_column("Politician")
    table.add_column("Symbol")
    table.add_column("Type")
    table.add_column("Amount")
    table.add_column("Tx date")
    table.add_column("Disclosed")
    for trade in new_trades:
        table.add_row(
            (trade.get("chamber") or "").title(),
            trade.get("politician") or "—",
            trade.get("symbol") or "—",
            trade.get("transaction_type") or "—",
            trade.get("amount_range") or "—",
            trade.get("transaction_date") or "—",
            trade.get("disclosure_date") or "—",
        )
    out.print(table)

    summary = payload.get("summary") or {}
    top = summary.get("top_symbols") or []
    if top:
        symbols = ", ".join(f"{item['symbol']} ({item['count']})" for item in top[:6])
        out.print(f"\n[dim]Top symbols this batch:[/dim] {symbols}")

    if payload.get("saved_to"):
        out.print(f"\n[dim]Report saved: {payload['saved_to']}[/dim]")

    out.print(
        "\n[dim]Dedup cache: var/politicians_cache/seen.json · requires FMP_API_KEY[/dim]"
    )