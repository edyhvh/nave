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
    from backend.app.services.aaii import fetch_aaii_sentiment
    from backend.app.services.onchain import fetch_onchain_metrics
    from backend.app.services.openbb import fetch_openbb_indicator

    if indicator == "all":
        payload = {
            "aaii": fetch_aaii_sentiment(),
            "onchain_btc": fetch_onchain_metrics("bitcoin"),
            "rrp": fetch_openbb_indicator("rrp"),
            "tga": fetch_openbb_indicator("tga"),
        }
        typer.echo(payload)
        return

    if indicator == "aaii":
        typer.echo(fetch_aaii_sentiment())
        return

    if indicator in {"onchain", "onchain_btc"}:
        typer.echo(fetch_onchain_metrics("bitcoin"))
        return

    typer.echo(fetch_openbb_indicator(indicator))


@trading_app.command("run-strategy")
def run_strategy(
    wallet: str = typer.Option("hermes", help="Wallet name"),
    coins: Optional[str] = typer.Option(None, help="Coins to trade"),
    dry_run: bool = typer.Option(True, help="Dry run mode"),
    mainnet: bool = typer.Option(False, help="Use mainnet"),
):
    """Run trading strategy (delegates to trading.strategy)."""
    from trading.client import HyperliquidClient
    from trading.strategy import MacroMomentumStrategy

    parsed_coins = coins.split() if coins else ["BTC", "ETH"]
    client = HyperliquidClient(wallet_name=wallet, testnet=not mainnet)
    strategy = MacroMomentumStrategy(
        client,
        coins=parsed_coins,
        dry_run=dry_run,
    )
    result = strategy.run_once()
    typer.echo(result)


@trading_app.command("run")
def run_trading(
    strategy: str = typer.Option(
        "cot-weekly",
        "--strategy",
        help="Strategy id to run (e.g. cot-weekly)",
    ),
    wallet: str = typer.Option("hermes", help="Wallet name"),
    capital: float = typer.Option(
        2000.0, help="Capital for weekly COT analysis"),
    paper: bool = typer.Option(
        False,
        "--paper",
        help="Run in paper mode (recommended default path)",
    ),
    backtest: bool = typer.Option(
        False,
        "--backtest",
        help="Run backtest mode for strategy validation",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        help="Disable dry-run safeguards (real execution path)",
    ),
    learn: bool = typer.Option(
        False,
        "--learn",
        help="Run setup learning pipeline from backtest outcomes",
    ),
):
    """Run trading workflows.

    Examples:
        nave trading run --paper --strategy cot-weekly
        nave trading run --backtest --strategy cot-weekly
    """
    import subprocess
    import sys

    if paper and backtest:
        raise typer.BadParameter("Use either --paper or --backtest, not both.")

    if strategy == "cot-weekly":
        cmd = [sys.executable, "scripts/weekly_cot_analysis.py",
               f"--capital={capital}"]
        if backtest:
            cmd.append("--backtest")
        else:
            cmd.append("--paper")
        if live:
            cmd.append("--live")
        if learn:
            cmd.append("--learn")
        typer.echo(
            f"Running {strategy} (paper={not backtest}, backtest={backtest})")
        subprocess.run(cmd, check=False)
        return

    cmd = [sys.executable, "-m", "trading.strategy", f"--wallet={wallet}"]
    if not live:
        cmd.append("--dry-run")
    typer.echo(f"Running strategy={strategy} via trading.strategy module")
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
    import sys
    subprocess.run([sys.executable, "-m", "trading.mcp_server"], check=False)


@cot_app.command("analyze")
def analyze_cot(coins: str = typer.Option("BTC ETH", help="Coins to analyze")):
    """Analyze COT data as main trading driver."""
    typer.echo(f"Analyzing COT for {coins}...")
    import subprocess
    import sys
    subprocess.run(
        [sys.executable, "-m", "trading.cot.cot_analyzer"], check=False)


@cot_app.command("report")
def cot_report(
    coins: str = typer.Option(
        "BTC ETH", help="Coins to analyze (space-separated)"),
    capital: float = typer.Option(2000.0, help="Available capital USD"),
    json_out: bool = typer.Option(
        False, "--json", help="Output as JSON instead of table"),
):
    """Weekly COT report with indicators for manual setup hunting.

    Fetches latest CFTC COT data, computes bias/strength/regime/volatility
    for each coin, and prints a clean summary you can use to find setups
    on the 4H/1H chart yourself.

    Examples:
        nave cot report
        nave cot report --coins "BTC ETH SOL"
        nave cot report --json
    """
    import json as _json
    from datetime import datetime as _dt

    from trading.cot.cot_fetcher import fetch_latest_cot
    from trading.cot.cot_analyzer import COTAnalyzer

    coin_list = coins.split()
    cot_data = fetch_latest_cot()

    analyzer = COTAnalyzer()
    biases = analyzer.analyze(cot_data)

    now = _dt.now().strftime("%Y-%m-%d %H:%M")

    if json_out:
        payload = {
            "generated_at": now,
            "capital_usd": capital,
            "coins": {},
        }
        for coin in coin_list:
            b = biases.get(coin)
            if not b:
                continue
            m = b.metadata
            payload["coins"][coin] = {
                "bias": b.bias,
                "confidence": round(b.confidence, 2),
                "net_non_commercial": b.net_non_commercial,
                "pct_oi": m["pct_oi"],
                "weekly_change": b.weekly_change,
                "fits_score": m["fits_weighted_score"],
                "bias_strength": m["bias_strength"],
                "market_regime": m["market_regime"],
                "momentum": m["momentum"],
                "volatility": round(m["volatility"], 4),
                "report_date": m.get("report_date", "N/A"),
            }
        typer.echo(_json.dumps(payload, indent=2))
        return

    # ── Pretty table output ──
    header = f"NAVE WEEKLY COT REPORT — {now}"
    typer.echo()
    typer.echo("=" * 68)
    typer.echo(f"  {header}")
    typer.echo("=" * 68)
    typer.echo(
        f"  Capital: ${capital:,.0f}  |  Philosophy: F.I.T.S. contrarian COT")
    typer.echo()

    for coin in coin_list:
        b = biases.get(coin)
        if not b:
            typer.echo(f"  {coin}: no COT data available")
            continue
        m = b.metadata

        arrow = {"bullish": "▲", "bearish": "▼",
                 "neutral": "–"}.get(b.bias, "?")

        typer.echo(f"  ┌─ {coin} ────────────────────────────────────────────")
        typer.echo(
            f"  │  Bias:           {b.bias.upper()} {arrow}  (confidence {b.confidence:.0%})")
        typer.echo(
            f"  │  Bias Strength:  {m['bias_strength'].upper()}  (FITS score {m['fits_weighted_score']}/100)")
        typer.echo(f"  │  Market Regime:  {m['market_regime']}")
        typer.echo(f"  │")
        typer.echo(f"  │  Net Non-Comm:   {b.net_non_commercial:,}")
        typer.echo(f"  │  % of OI:        {m['pct_oi']:.1f}%")
        typer.echo(f"  │  Weekly Δ:       {b.weekly_change:+,}")
        typer.echo(f"  │  Momentum:       {m['momentum']:+,.0f}")
        typer.echo(f"  │  Volatility:     {m['volatility']:.2%}")
        typer.echo(f"  │  Report Date:    {m.get('report_date', 'N/A')}")
        typer.echo(f"  │")

        # Actionable hint
        if b.bias == "bullish":
            typer.echo(
                f"  │  → Look for LONG setups on 4H/1H (OB, FVG, liq sweep)")
        elif b.bias == "bearish":
            typer.echo(
                f"  │  → Look for SHORT setups on 4H/1H (OB, FVG, liq sweep)")
        else:
            typer.echo(f"  │  → NEUTRAL — no clear edge, wait or reduce size")

        typer.echo(f"  └────────────────────────────────────────────────────")
        typer.echo()

    # Best asset
    ranked = sorted(
        [(c, biases[c]) for c in coin_list if c in biases],
        key=lambda x: x[1].confidence,
        reverse=True,
    )
    if ranked:
        best_coin, best_bias = ranked[0]
        typer.echo(f"  Best edge: {best_coin} {best_bias.bias.upper()} "
                   f"({best_bias.confidence:.0%} confidence, "
                   f"{best_bias.metadata['bias_strength']} strength)")
    typer.echo()
    typer.echo("  Use this report to find setups manually on the chart.")
    typer.echo("  Setups to look for: 75% retracement, order block, FVG,")
    typer.echo("  liquidity sweep, breaker block.")
    typer.echo("=" * 68)
    typer.echo()


if __name__ == "__main__":
    app()
