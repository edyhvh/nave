"""Options analysis command group for Nave CLI."""

from __future__ import annotations

import json

import typer

from cli.professional_typer import ProfessionalTyper
from options.analyzer import OptionsAnalyzer
from options.exceptions import OptionsError

options_app = ProfessionalTyper(help="Options analytics commands")


@options_app.command("analyze")
def analyze(
    ticker: str = typer.Option(
        "MSFT", "--ticker", help="Underlying ticker symbol"),
    days_to_exp: int = typer.Option(
        30, "--days-to-exp", min=1, max=365, help="Target days to expiration"),
    json_out: bool = typer.Option(
        True, "--json/--no-json", help="Emit machine-stable JSON output"),
) -> None:
    """Run options analysis and print recommendations."""
    analyzer = OptionsAnalyzer()
    try:
        payload = analyzer.run(ticker=ticker, days_to_exp=days_to_exp)
    except OptionsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_out:
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    underlying = payload.get("underlying_analysis", {})
    typer.echo(f"Ticker: {payload.get('ticker')}")
    typer.echo(f"Price: {underlying.get('price')}")
    typer.echo("Top strategies:")
    for rec in payload.get("recommendations", [])[:3]:
        strategy = (rec.get("strategy", {}) or {}).get("name", "unknown")
        metrics = rec.get("metrics", {}) or {}
        typer.echo(
            f"- {strategy}: score={metrics.get('composite_score')} pop={metrics.get('pop')} ev={metrics.get('expected_value')}"
        )
