"""Top-level Congressional trades command — new disclosures since last run."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from cli.professional_typer import ProfessionalTyper
from trading.stocks.politicians.display import render_congress_scan
from trading.stocks.politicians.scanner import run_daily_scan

congress_app = ProfessionalTyper(
    help="Congressional STOCK Act disclosures (new since last run)"
)


def _json_default(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    return str(value)


def _run_congress_scan(
    *,
    persist: bool,
    save_report: bool,
) -> dict[str, Any]:
    payload = run_daily_scan(persist=persist)
    if save_report:
        project_root = Path(__file__).resolve().parents[2]
        report_dir = project_root / "var" / "reports" / "politicians"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{date.today().isoformat()}.json"
        report_path.write_text(json.dumps(payload, indent=2, default=str))
        payload["saved_to"] = str(report_path)
    return payload


@congress_app.callback(invoke_without_command=True)
def congress_scan(
    ctx: typer.Context,
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    telegram_markdown_v2: bool = typer.Option(
        False,
        "--telegram-markdown-v2",
        help="Telegram MarkdownV2 digest (chunked).",
    ),
    no_persist: bool = typer.Option(
        False,
        "--no-persist",
        help="Dry run — do not update last-run cache.",
    ),
    save_report: bool = typer.Option(
        True,
        "--save-report/--no-save-report",
        help="Write JSON under var/reports/politicians/.",
    ),
) -> None:
    """New House + Senate stock disclosures since you last ran this command."""
    if ctx.invoked_subcommand is not None:
        return

    payload = _run_congress_scan(persist=not no_persist, save_report=save_report)

    if json_out:
        typer.echo(json.dumps(payload, indent=2, default=_json_default))
        return

    if telegram_markdown_v2:
        from trading.stocks.politicians.formatters import render_politicians_scan_markdown_v2

        messages = render_politicians_scan_markdown_v2(payload, include_empty=True)
        if not messages:
            typer.echo("No Telegram digest generated.")
            return
        for idx, message in enumerate(messages, start=1):
            if idx > 1:
                typer.echo("\n---\n")
            typer.echo(message)
        return

    render_congress_scan(payload, console=Console())