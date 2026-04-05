"""Unified Nave CLI using Typer.

Provides clean commands for data, trading, API, MCP, and COT analysis.
Orchestrates existing components without removing integrations.
"""

import typer
from typing import Optional
from pathlib import Path

app = typer.Typer(
    name="nave",
    help="Nave - Professional macro trading and data platform CLI",
    add_completion=True,
)

# Sub-apps
data_app = typer.Typer(help="Data fetching and analysis commands")
trading_app = typer.Typer(help="Trading and strategy commands")
api_app = typer.Typer(help="Backend API commands")
mcp_app = typer.Typer(help="MCP server commands")
cot_app = typer.Typer(help="COT specific commands")

app.add_typer(data_app, name="data")
app.add_typer(trading_app, name="trading")
app.add_typer(api_app, name="api")
app.add_typer(mcp_app, name="mcp")
app.add_typer(cot_app, name="cot")


@app.command()
def version():
    """Show Nave version."""
    typer.echo("Nave v0.1.0 (refactored with unified CLI)")

# Stub commands - will be fleshed out in later steps


@data_app.command("fetch")
def fetch_data(indicator: str = typer.Argument("all")):
    """Fetch macro data using OpenBB."""
    typer.echo(
        f"Fetching data for {indicator}... (using existing OpenBB services)")
    # TODO: integrate with backend/services or scripts/openbb_tools.py


@trading_app.command("run-strategy")
def run_strategy(
    wallet: str = typer.Option("openfang", help="Wallet name"),
    coins: Optional[str] = typer.Option(None, help="Coins to trade"),
    dry_run: bool = typer.Option(True, help="Dry run mode"),
    mainnet: bool = typer.Option(False, help="Use mainnet"),
):
    """Run trading strategy (delegates to trading.strategy)."""
    typer.echo(f"Running strategy for wallet={wallet}, dry_run={dry_run}...")
    # TODO: import and call from trading.strategy (direct call in future refactor)
    import subprocess
    cmd = ["python", "-m", "trading.strategy", f"--wallet={wallet}"]
    if dry_run:
        cmd.append("--dry-run")
    subprocess.run(cmd, check=False)


@api_app.command("start")
def start_api(
    host: str = typer.Option("127.0.0.1", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to listen on"),
    reload: bool = typer.Option(True, help="Enable auto-reload"),
):
    """Start the FastAPI backend server."""
    typer.echo(f"Starting Nave API on {host}:{port} (reload={reload})...")
    import subprocess
    cmd = [
        "uvicorn",
        "--app-dir=backend",
        "app.main:app",
        f"--host={host}",
        f"--port={port}",
        "--reload" if reload else "",
    ]
    cmd = [c for c in cmd if c]
    subprocess.run(cmd, check=False)


@mcp_app.command("run")
def run_mcp():
    """Run the MCP server for AI agents."""
    typer.echo("Starting MCP server (uses trading/mcp_server)...")
    import subprocess
    subprocess.run(["python", "-m", "trading.mcp_server"], check=False)


@cot_app.command("analyze")
def analyze_cot(coins: str = typer.Option("BTC ETH", help="Coins to analyze")):
    """Analyze COT data as main trading driver."""
    typer.echo(f"Analyzing COT for {coins}...")
    import subprocess
    subprocess.run(["python", "-m", "trading.cot.cot_analyzer"], check=False)


if __name__ == "__main__":
    app()
