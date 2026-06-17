"""Terminal display for the daily BTC/ETH entry check."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from trading.crypto.analysis.review import format_options_display


def _action_style(action: str) -> str:
    if action == "enter":
        return "bold green"
    if action == "watch":
        return "bold yellow"
    return "dim"


def _format_zone(zone: list[float] | None) -> str:
    if not zone:
        return "—"
    if len(zone) == 1:
        return f"{zone[0]:,.2f}"
    return f"{zone[0]:,.0f} – {zone[1]:,.0f}"


def _format_risk_hint(rec: dict[str, Any]) -> str:
    hint = rec.get("suggested_risk") or {}
    if not hint:
        return "—"
    current = float(hint.get("current_risk_pct") or 0.0)
    suggested = float(hint.get("suggested_risk_pct") or current)
    label = f"{suggested * 100:.2f}%"
    if hint.get("blocked"):
        return f"{current * 100:.2f}% blocked"
    if suggested > current:
        return f"{label}*"
    return label


def render_daily_entry_check(payload: dict[str, Any], *, console: Console | None = None) -> None:
    """Human-first daily view: when to enter BTC/ETH."""
    out = console or Console()
    recs = payload.get("recommendations") or []
    generated = payload.get("generated_at", "")[:19].replace("T", " ")

    enters = [r for r in recs if r.get("action") == "enter"]
    watches = [r for r in recs if r.get("action") == "watch"]
    aside = [r for r in recs if r.get("action") == "stand_aside"]

    headline = Text()
    if enters:
        headline.append("ENTER NOW: ", style="bold")
        headline.append(", ".join(f"{r['coin']} {r['direction']}" for r in enters), style="bold green")
    if watches:
        if enters:
            headline.append("  |  ", style="dim")
        else:
            headline.append("WATCH: ", style="bold")
        headline.append(", ".join(f"{r['coin']} {r['direction']}" for r in watches), style="bold yellow")
    if not enters and not watches:
        headline.append("NO ENTRY", style="bold dim")
        headline.append(" — stand aside on BTC/ETH today", style="dim")

    out.print(
        Panel(
            headline,
            title=f"[bold]BTC/ETH daily entry[/bold]  {generated} UTC",
            subtitle=(
                f"enter={len(enters)}  watch={len(watches)}  aside={len(aside)}"
            ),
        )
    )

    table = Table(show_header=True, header_style="bold", show_lines=False, pad_edge=False)
    table.add_column("Coin", style="bold")
    table.add_column("Action")
    table.add_column("Side")
    table.add_column("Conf", justify="right")
    table.add_column("Regime")
    table.add_column("Entry zone", justify="right")
    table.add_column("Stop", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Risk", justify="right")
    table.add_column("Options")

    for rec in recs:
        action = str(rec.get("action", "stand_aside"))
        table.add_row(
            rec.get("coin", "?"),
            Text(action.upper(), style=_action_style(action)),
            rec.get("direction") or "—",
            f"{float(rec.get('confidence') or 0):.0%}",
            rec.get("regime_phase") or "—",
            _format_zone(rec.get("entry_zone")),
            f"{rec['invalidation']:,.2f}" if rec.get("invalidation") else "—",
            str(rec.get("momentum_score") or "—"),
            _format_risk_hint(rec),
            format_options_display(rec.get("options")) or "—",
        )
    out.print(table)

    for rec in enters + watches:
        action = rec.get("action", "").upper()
        out.print(f"\n[bold]{rec['coin']}[/bold] — {action} {rec.get('direction') or ''}")
        if rec.get("playbook"):
            out.print(f"  [dim]Playbook:[/dim] {rec['playbook']}")
        for line in rec.get("reasons", [])[:4]:
            out.print(f"  [green]•[/green] {line}")
        for line in rec.get("blockers", [])[:2]:
            out.print(f"  [red]•[/red] {line}")
        targets = rec.get("targets") or []
        if targets:
            out.print(f"  targets: {' / '.join(f'{t:,.0f}' for t in targets[:3])}")
        risk_hint = rec.get("suggested_risk") or {}
        if risk_hint and risk_hint.get("blocked"):
            blockers = risk_hint.get("blockers") or []
            reason = f": {', '.join(str(item) for item in blockers[:2])}" if blockers else ""
            out.print(f"  risk hint blocked{reason}")
        elif risk_hint:
            current = float(risk_hint.get("current_risk_pct") or 0.0)
            suggested = float(risk_hint.get("suggested_risk_pct") or current)
            if suggested > current:
                out.print(
                    f"  risk hint: {suggested * 100:.2f}% "
                    f"([dim]advisory, primary ENTER only[/dim])"
                )
        thesis = rec.get("thesis") or {}
        if thesis.get("thesis_state") == "active":
            out.print(
                f"  thesis: {thesis.get('thesis_status')} "
                f"({thesis.get('thesis_phase', '')})"
            )

    secondary_rows = [
        (rec, opp)
        for rec in recs
        for opp in (rec.get("secondary_opportunities") or [])
    ]
    if secondary_rows:
        out.print("\n[bold yellow]Secondary opportunities[/bold yellow] [dim](notrend / fade / forming)[/dim]")
        sec_table = Table(show_header=True, header_style="bold", show_lines=False)
        sec_table.add_column("Coin")
        sec_table.add_column("Kind")
        sec_table.add_column("Side")
        sec_table.add_column("Conf", justify="right")
        sec_table.add_column("Entry zone", justify="right")
        sec_table.add_column("Stop", justify="right")
        for rec, opp in secondary_rows:
            sec_table.add_row(
                rec.get("coin", "?"),
                opp.get("kind", "—"),
                opp.get("direction", "—"),
                f"{float(opp.get('confidence') or 0):.0%}",
                _format_zone(opp.get("entry_zone")),
                f"{opp['invalidation']:,.2f}" if opp.get("invalidation") else "—",
            )
        out.print(sec_table)
        for rec, opp in secondary_rows[:4]:
            out.print(
                f"  [yellow]{rec['coin']}[/yellow] {opp.get('kind')}: {opp.get('playbook', '')[:100]}"
            )

    if aside and not enters and not watches:
        if secondary_rows:
            out.print(
                "\n[dim]Primary stack: stand aside — see secondary lanes above for "
                "relief-rally fades and notrend scalps.[/dim]"
            )
        else:
            out.print("\n[dim]Both coins are stand-aside — no COT+momentum entry today.[/dim]")

    out.print(
        "\n[dim]Stack: COT → regime → momentum 4H/1H → perp (primary). "
        "Deribit options may show as advisory when touch/quality gates block. "
        "JSON: add --json · refresh doc: python scripts/refresh_current_setup.py[/dim]"
    )


def run_daily_entry_check(
    coins: list[str],
    *,
    account_equity: float = 10_000.0,
    risk_pct: float = 0.005,
    include_options: bool = True,
    options_source: str = "deribit",
    apply_cadence_policy: bool = True,
) -> dict[str, Any]:
    from trading.crypto.analysis import CryptoAnalysisService

    payload = CryptoAnalysisService().review(
        coins,
        account_equity=account_equity,
        risk_pct=risk_pct,
        include_options=include_options,
        options_source=options_source,
        apply_cadence_policy=apply_cadence_policy,
    )
    payload["check_type"] = "daily_entry"
    payload["checked_at"] = datetime.now(timezone.utc).isoformat()
    return payload
