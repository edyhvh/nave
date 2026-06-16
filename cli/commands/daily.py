"""Top-level daily BTC/ETH entry command — primary operator CLI."""

from __future__ import annotations

import json
from typing import Any

import typer
from rich.console import Console

from cli.professional_typer import ProfessionalTyper
from trading.crypto.analysis.daily_display import render_daily_entry_check, run_daily_entry_check

daily_app = ProfessionalTyper(help="Daily BTC/ETH entry check (COT + regime + momentum + options)")


def _parse_coins(coins: str) -> list[str]:
    return [part.strip().upper() for part in coins.replace(",", " ").split() if part.strip()]


def _json_default(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    return str(value)


@daily_app.callback(invoke_without_command=True)
def daily_entry(
    ctx: typer.Context,
    coins: str = typer.Option("BTC,ETH", "--coins", "-c", help="BTC and/or ETH."),
    account_equity: float = typer.Option(10_000.0, "--account-equity"),
    risk_pct: float = typer.Option(0.005, "--risk-pct"),
    include_options: bool = typer.Option(True, "--options/--no-options"),
    options_source: str = typer.Option("deribit", "--options-source"),
    adaptive_threshold: bool = typer.Option(
        True,
        "--adaptive-threshold/--no-adaptive-threshold",
        help="Apply the cadence-recommended threshold in the daily review.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Daily entry check for BTC/ETH — enter, watch, or stand aside in one screen."""
    if ctx.invoked_subcommand is not None:
        return

    coin_list = _parse_coins(coins)
    payload = run_daily_entry_check(
        coin_list,
        account_equity=account_equity,
        risk_pct=risk_pct,
        include_options=include_options,
        options_source=options_source,
        apply_cadence_policy=adaptive_threshold,
    )
    if json_out:
        typer.echo(json.dumps(payload, indent=2, default=_json_default))
        return
    render_daily_entry_check(payload, console=Console())
