"""Core CLI command groups: data, trading, api, mcp, journal, and version."""

from __future__ import annotations

import json
from typing import Optional

import typer

from cli.professional_typer import ProfessionalTyper
from cli.utils import prompt_float, select_option
from core.config import CliDefaults

DEFAULTS = CliDefaults()

data_app = ProfessionalTyper(help="Data fetching and analysis commands")
trading_app = ProfessionalTyper(help="Trading and strategy commands")
api_app = ProfessionalTyper(help="Backend API commands")
mcp_app = ProfessionalTyper(help="MCP server commands")
journal_app = ProfessionalTyper(help="Manual trade journal commands")

trading_app.add_typer(journal_app, name="journal")


@data_app.command("fetch")
def fetch_data(indicator: str = typer.Argument("all")) -> None:
    """Fetch macro data using OpenBB-backed services."""
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
    wallet: str = typer.Option(DEFAULTS.wallet, help="Wallet name"),
    coins: Optional[str] = typer.Option(None, help="Coins to trade"),
    dry_run: bool = typer.Option(True, help="Dry run mode"),
    mainnet: bool = typer.Option(False, help="Use mainnet"),
) -> None:
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
    wallet: str = typer.Option(DEFAULTS.wallet, help="Wallet name"),
    capital: float = typer.Option(DEFAULTS.capital_usd, help="Capital for weekly COT analysis"),
    paper: bool = typer.Option(
        False,
        "--paper",
        help="Run in paper mode (recommended default path)",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        help="Disable dry-run safeguards (real execution path)",
    ),
) -> None:
    """Run trading workflows."""
    import subprocess
    import sys

    if strategy == "cot-weekly":
        cmd = [sys.executable, "scripts/weekly_cot_analysis.py", f"--capital={capital}"]
        if paper or not live:
            cmd.append("--paper")
        if live:
            cmd.append("--live")
        typer.echo(f"Running {strategy} (paper={paper or not live})")
        subprocess.run(cmd, check=False)
        return

    cmd = [sys.executable, "-m", "trading.strategy", f"--wallet={wallet}"]
    if not live:
        cmd.append("--dry-run")
    typer.echo(f"Running strategy={strategy} via trading.strategy module")
    subprocess.run(cmd, check=False)


@api_app.command("start")
def start_api(
    host: str = typer.Option(DEFAULTS.host, help="Host to bind"),
    port: int = typer.Option(DEFAULTS.api_port, help="Port to listen on"),
    reload: bool = typer.Option(True, help="Enable auto-reload"),
) -> None:
    """Start the FastAPI backend server."""
    import subprocess

    typer.echo(f"Starting Nave API on {host}:{port} (reload={reload})...")
    cmd = [
        "uvicorn",
        "--app-dir=backend",
        "app.main:app",
        f"--host={host}",
        f"--port={port}",
        "--reload" if reload else "",
    ]
    cmd = [item for item in cmd if item]
    subprocess.run(cmd, check=False)


@mcp_app.command("run")
def run_mcp() -> None:
    """Run the MCP server for AI agents."""
    import subprocess
    import sys

    typer.echo("Starting MCP server (uses trading/crypto/mcp_server)...")
    subprocess.run([sys.executable, "-m", "trading.crypto.mcp_server"], check=False)


@mcp_app.command("fmp-connector")
def fmp_connector(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of prose."),
) -> None:
    """Print the remote FMP MCP connector URL for agent clients."""
    import json as _json
    import os

    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        raise typer.BadParameter("FMP_API_KEY is not set. Add it to .env before using the FMP MCP connector.")

    payload = {
        "name": "fmp-remote",
        "url": f"https://financialmodelingprep.com/mcp?apikey={api_key}",
        "limits": {
            "daily_calls": 250,
            "monthly_mb": 512,
        },
        "notes": [
            "Remote MCP calls count against the same FMP API quota as REST calls.",
            "Prefer Nave's local MCP server for repo-native tools and FMP's remote MCP only for direct vendor data access.",
        ],
    }

    if json_out:
        typer.echo(_json.dumps(payload, indent=2))
        return

    typer.echo("FMP remote MCP connector")
    typer.echo(payload["url"])
    typer.echo("Quota: 250 calls/day, 512 MB/month")
    typer.echo("Use this in Claude/Cursor/other MCP clients as a remote server URL.")


@journal_app.command("create")
def journal_create() -> None:
    """Create a manual trade record with interactive prompts."""
    from trading.journal.manual_trade import (
        MARKET_TYPES,
        SIDES,
        TRADING_MODES,
        ManualTrade,
        ManualTradeStore,
        fetch_cot_insight,
    )

    store = ManualTradeStore()
    asset = typer.prompt("Asset", default="BTC").strip().upper()
    platform = typer.prompt("Platform", default="binance").strip().lower()
    side = select_option("Select side", list(SIDES), default="long")
    market_type = select_option("Select market type", list(MARKET_TYPES), default="futures")
    trading_mode = select_option("Select trading mode", list(TRADING_MODES), default="demo")

    entry_price = prompt_float("Entry price", min_value=0.000001)
    target_price = prompt_float("Target price", min_value=0.000001)
    stop_loss_price = prompt_float("Stop loss price", min_value=0.000001)
    fees = prompt_float("Fees", default=0.0, min_value=0.0)
    size = prompt_float("Position size (USD/contracts)", min_value=0.0)
    leverage = prompt_float("Leverage", default=1.0, min_value=1.0)
    setup = typer.prompt("Setup (optional)", default="")
    notes = typer.prompt("Notes (optional)", default="")

    cot_insight = None
    cot_warning = None
    try:
        cot_insight = fetch_cot_insight(asset)
    except Exception as exc:
        typer.echo(f"COT fetch failed: {exc}")
        retry = typer.confirm("Retry COT fetch once?", default=True)
        if retry:
            try:
                cot_insight = fetch_cot_insight(asset)
            except Exception as second_exc:
                cot_warning = f"COT unavailable after retry: {second_exc}"
        else:
            cot_warning = "COT fetch skipped by user"

    trade = ManualTrade(
        asset=asset,
        platform=platform,
        side=side,
        market_type=market_type,
        trading_mode=trading_mode,
        entry_price=entry_price,
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        fees=fees,
        size=size,
        leverage=leverage,
        setup=setup,
        notes=notes,
        cot_insight=cot_insight,
        cot_warning=cot_warning,
    )
    store.create_trade(trade)
    typer.echo(f"Created manual trade: {trade.trade_id}")
    typer.echo("Next: nave trading journal update --id <TRADE_ID>")


@journal_app.command("update")
def journal_update(
    id: str = typer.Option(..., "--id", help="Trade ID to update"),
) -> None:
    """Update an existing manual trade with guided actions."""
    from trading.journal.manual_trade import ManualTradeStore

    store = ManualTradeStore()
    trade = store.get_trade(id)
    if trade is None:
        raise typer.BadParameter(f"Trade not found: {id}")

    action = select_option(
        "Select update action",
        [
            "take_profit_price_1",
            "take_profit_price_2",
            "take_profit_final_price",
            "stop_loss adjustment",
            "fees adjustment",
            "notes update",
        ],
        default="take_profit_price_1",
    )

    if action == "notes update":
        value = typer.prompt("New notes")
    else:
        value = prompt_float("New value", min_value=0.0)

    updated = store.apply_update(id, action, value)
    typer.echo(f"Updated trade: {updated.trade_id}")
    typer.echo(f"Status: {updated.status}")
    if action == "take_profit_price_1" and updated.tp1_progress_percent is not None:
        typer.echo(f"TP1 progress: {updated.tp1_progress_percent:.2f}%")
    if action == "take_profit_price_2" and updated.tp2_progress_percent is not None:
        typer.echo(f"TP2 progress: {updated.tp2_progress_percent:.2f}%")


@journal_app.command("list")
def journal_list(
    status: Optional[str] = typer.Option(None, help="Filter by status (open/closed)"),
) -> None:
    """List manual journal trades."""
    from trading.journal.manual_trade import ManualTradeStore

    store = ManualTradeStore()
    trades = store.list_trades(status=status)
    if not trades:
        typer.echo("No manual trades found.")
        return

    for trade in trades:
        synced = "yes" if trade.sync.get("wiki_synced_at") else "no"
        typer.echo(
            f"{trade.trade_id} | {trade.asset} {trade.side} | {trade.trading_mode} | "
            f"status={trade.status} | synced={synced}"
        )


@journal_app.command("show")
def journal_show(
    id: str = typer.Option(..., "--id", help="Trade ID"),
) -> None:
    """Show full manual trade JSON."""
    from trading.journal.manual_trade import ManualTradeStore

    store = ManualTradeStore()
    trade = store.get_trade(id)
    if trade is None:
        raise typer.BadParameter(f"Trade not found: {id}")
    typer.echo(json.dumps(trade.to_dict(), indent=2))


@journal_app.command("sync-wiki")
def journal_sync_wiki(
    owner: str = typer.Option("edyhvh", help="GitHub owner"),
    repo: str = typer.Option("nave", help="GitHub repository name"),
    token: Optional[str] = typer.Option(None, help="GitHub token; defaults to NAVE_GITHUB_TOKEN"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview unsynced trades only"),
) -> None:
    """Sync unsynced manual trades to monthly GitHub wiki pages."""
    import os

    from trading.journal.manual_trade import ManualTradeStore
    from trading.journal.manual_wiki_sync import ManualTradeWikiSync

    store = ManualTradeStore()
    rows = store.unsynced_trades()
    if not rows:
        typer.echo("No unsynced trades found.")
        return

    typer.echo(f"Unsynced trades: {len(rows)}")
    if dry_run:
        for trade in rows:
            typer.echo(f"- {trade.trade_id} ({trade.date_created[:7]})")
        return

    github_token = token or os.getenv("NAVE_GITHUB_TOKEN", "")
    if not github_token:
        raise typer.BadParameter("Missing token: use --token or set NAVE_GITHUB_TOKEN")

    if not typer.confirm("Proceed with wiki sync?", default=False):
        typer.echo("Sync cancelled.")
        return

    syncer = ManualTradeWikiSync(owner=owner, repo=repo, token=github_token)
    result = syncer.sync(rows)
    if result["synced"] == 0:
        typer.echo("No new entries were synced.")
        return

    month_pages = sorted({f"Journal-{trade.date_created[:7]}" for trade in rows})
    for page in month_pages:
        ids = [trade.trade_id for trade in rows if page.endswith(trade.date_created[:7])]
        store.mark_synced(ids, page)
    typer.echo(f"Synced {result['synced']} trades across {result['pages']} page(s).")
