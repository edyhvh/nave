"""Memecoin CLI command group — Solana scanner + safety filter.

Subcommands:
    nave memecoin scan         Pull recent Pump.fun launches, gate, score, rank.
    nave memecoin check        Run the full safety + score pipeline on one mint.
"""

from __future__ import annotations

import json as _json
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cli.professional_typer import ProfessionalTyper
from core.logger import configure_logger
from trading.memecoin import MemecoinScanner

logger = configure_logger(__name__, level=logging.INFO)

memecoin_app = ProfessionalTyper(
    help="Solana memecoin scanner (Pump.fun + Helius + DexScreener + Jupiter)."
)


def _verdict_color(verdict: str) -> str:
    return {
        "PASS": "green",
        "WATCH": "yellow",
        "FAIL": "red",
    }.get(verdict, "white")


def _label_color(label: str) -> str:
    return {
        "GOOD": "green",
        "WATCH": "yellow",
        "SHILL": "red",
    }.get(label, "white")


@memecoin_app.command("scan")
def scan(
    limit: int = typer.Option(
        50, "--limit", help="How many recent Pump.fun launches to pull."
    ),
    top_n: int = typer.Option(
        10, "--top-n", help="Keep the top-N passing candidates by score."
    ),
    keep_skipped: bool = typer.Option(
        False,
        "--keep-skipped",
        help="Include liquidity-rejected tokens (observability).",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit raw JSON instead of the table."
    ),
) -> None:
    """Run the discover → gate → safety → score pipeline."""
    scanner = MemecoinScanner()
    candidates = scanner.scan(limit=limit, top_n=top_n, keep_skipped=keep_skipped)

    payload = {
        "tool": "memecoin_scan",
        "params": {"limit": limit, "top_n": top_n, "keep_skipped": keep_skipped},
        "count": len(candidates),
        "candidates": [c.to_dict() for c in candidates],
    }

    if json_out:
        typer.echo(_json.dumps(payload, default=str, indent=2))
        return

    console = Console()
    if not candidates:
        console.print(
            "[yellow]No candidates returned.[/yellow] Either the Pump.fun feed "
            "is empty right now or every recent launch failed the $25k "
            "liquidity gate or a safety check."
        )
        return

    table = Table(
        title=f"Memecoin scan — {len(candidates)} candidates "
        f"(limit={limit}, top_n={top_n})",
        show_lines=False,
    )
    table.add_column("Score", justify="right")
    table.add_column("Label")
    table.add_column("Verdict")
    table.add_column("Symbol")
    table.add_column("Mint", overflow="ellipsis")
    table.add_column("Liq $", justify="right")
    table.add_column("FDV $", justify="right")
    table.add_column("Vol24h $", justify="right")
    table.add_column("5m %", justify="right")
    table.add_column("1h %", justify="right")
    table.add_column("Top-10 %", justify="right")
    table.add_column("Rug")

    for c in candidates:
        market = c.market
        liq = (market.liquidity_usd if market else None) or 0.0
        fdv = (market.fdv_usd if market else None) or (
            market.market_cap_usd if market else None
        )
        vol = (market.volume_24h_usd if market else None) or 0.0
        m5 = market.price_change_5m_pct if market else None
        h1 = market.price_change_1h_pct if market else None
        conc = c.safety.checks.get("holder_concentration", {}) if c.safety.checks else {}
        top10 = conc.get("top_10_pct") if isinstance(conc, dict) else None
        table.add_row(
            f"{c.score.total}",
            f"[{_label_color(c.score.label.value)}]{c.score.label.value}[/]",
            f"[{_verdict_color(c.safety.verdict.value)}]{c.safety.verdict.value}[/]",
            c.symbol or "?",
            c.mint,
            f"{liq:,.0f}",
            f"{fdv:,.0f}" if fdv else "-",
            f"{vol:,.0f}",
            f"{m5:+.1f}" if m5 is not None else "-",
            f"{h1:+.1f}" if h1 is not None else "-",
            f"{top10:.1f}" if isinstance(top10, (int, float)) else "-",
            f"{c.safety.rug_score}",
        )
    console.print(table)


@memecoin_app.command("check")
def check(
    mint: str = typer.Argument(..., help="Solana mint address (base58)."),
    json_out: bool = typer.Option(
        False, "--json", help="Emit raw JSON instead of the formatted block."
    ),
) -> None:
    """Run the full safety + score pipeline on a single mint."""
    scanner = MemecoinScanner()
    candidate = scanner.check(mint)
    payload = candidate.to_dict()

    if json_out:
        typer.echo(_json.dumps(payload, default=str, indent=2))
        return

    console = Console()
    safety = candidate.safety
    score = candidate.score
    market = candidate.market

    console.print()
    console.print(
        f"[bold]{candidate.symbol or '?'}[/bold]  "
        f"({candidate.name or 'unknown name'})  "
        f"[dim]{candidate.mint}[/dim]"
    )
    console.print(
        f"verdict: [{_verdict_color(safety.verdict.value)}]{safety.verdict.value}[/]   "
        f"rug_score: {safety.rug_score}   "
        f"label: [{_label_color(score.label.value)}]{score.label.value}[/] "
        f"({score.total}/100)"
    )
    if candidate.skipped_reason:
        console.print(f"[red]skipped:[/] {candidate.skipped_reason}")

    if market:
        console.print(
            f"market: liq=${(market.liquidity_usd or 0):,.0f}  "
            f"fdv=${(market.fdv_usd or market.market_cap_usd or 0):,.0f}  "
            f"vol24h=${(market.volume_24h_usd or 0):,.0f}  "
            f"dex={market.dex or '-'}"
        )

    console.print()
    console.print("[bold]Safety checks[/bold]")
    for name, value in (safety.checks or {}).items():
        console.print(f"  - {name}: {value}")

    console.print()
    console.print("[bold]Score breakdown[/bold]")
    for band_name, band in (score.bands or {}).items():
        console.print(f"  - {band_name}: {band}")
    if score.rationale:
        console.print()
        console.print("[bold]Rationale[/bold]")
        for line in score.rationale:
            console.print(f"  • {line}")
    console.print()
