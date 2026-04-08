"""Unified Nave CLI entrypoint.

The command implementation lives in modular command groups under cli/commands.
This module only assembles the application surface.
"""

from __future__ import annotations

import typer

from cli.commands.core import api_app, data_app, mcp_app, trading_app
from cli.commands.cot import cot_app
from cli.commands.hermes import hermes_app

app = typer.Typer(
    name="nave",
    help="Nave - Professional macro trading and data platform CLI",
    add_completion=True,
)

app.add_typer(data_app, name="data")
app.add_typer(trading_app, name="trading")
app.add_typer(api_app, name="api")
app.add_typer(mcp_app, name="mcp")
app.add_typer(cot_app, name="cot")
app.add_typer(hermes_app, name="hermes")


@app.command("version")
def version() -> None:
    """Show Nave version."""
    typer.echo("Nave v0.1.0 (refactored with modular CLI)")


if __name__ == "__main__":
    app()
