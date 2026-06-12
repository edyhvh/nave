"""Wallet commands — create EVM wallets and verify Hyperliquid testnet readiness."""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cli.professional_typer import ProfessionalTyper
from core.config import HyperliquidSettings
from trading.crypto.wallet_service import (
    create_wallet,
    get_account_status,
    list_wallets,
    request_testnet_faucet,
    run_test_trade,
    setup_default_wallets,
    validate_wallet_name,
)

wallet_app = ProfessionalTyper(help="Hyperliquid wallet setup and testnet trading")
console = Console()


def _hl_settings() -> HyperliquidSettings:
    return HyperliquidSettings.from_env()


@wallet_app.command("create")
def wallet_create(
    name: str = typer.Option(..., "--name", "-n", help="Wallet name (e.g. trading, hermes)"),
) -> None:
    """Create a new encrypted EVM wallet for Hyperliquid."""
    try:
        record = create_wallet(name)
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"Created wallet '{record.name}'")
    typer.echo(f"Address: {record.address}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  1. nave wallet status --wallet {record.name}")
    typer.echo(f"  2. nave wallet fund --wallet {record.name}")
    typer.echo(f"  3. Set HL_WALLET={record.name} in .env for trading commands")


@wallet_app.command("setup")
def wallet_setup() -> None:
    """Create the default nave wallets (ironclaw, openfang, hermes)."""
    result = setup_default_wallets()

    if result.created:
        typer.echo("Created wallets:")
        for record in result.created:
            typer.echo(f"  {record.name}: {record.address}")

    if result.skipped:
        typer.echo(f"Skipped (already exist): {', '.join(result.skipped)}")

    if not result.created and not result.skipped:
        typer.echo("No wallets were created.")
        return

    typer.echo("")
    typer.echo("Seed phrases are encrypted in ~/.secrets/nave-wallets/")
    typer.echo("Set HL_WALLET in .env to choose which wallet trading commands use.")


@wallet_app.command("list")
def wallet_list(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """List wallets stored in the local encrypted vault."""
    records = list_wallets()
    if json_out:
        typer.echo(json.dumps([record.__dict__ for record in records], indent=2))
        return

    if not records:
        typer.echo("No wallets found. Run: nave wallet setup")
        return

    table = Table(title="Nave wallets", show_lines=False)
    table.add_column("Name")
    table.add_column("Address")
    for record in records:
        table.add_row(record.name, record.address)
    console.print(table)


@wallet_app.command("status")
def wallet_status(
    wallet: Optional[str] = typer.Option(None, "--wallet", "-w", help="Wallet name"),
    mainnet: bool = typer.Option(False, "--mainnet", help="Query mainnet instead of testnet"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Show Hyperliquid account state for a vault wallet."""
    settings = _hl_settings()
    wallet_name = wallet or settings.wallet
    testnet = False if mainnet else settings.testnet

    try:
        status = get_account_status(wallet_name, testnet=testnet)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    payload = {
        "wallet": status.wallet,
        "address": status.address,
        "env": status.env,
        "equity_usd": status.equity_usd,
        "margin_used_usd": status.margin_used_usd,
        "position_count": status.position_count,
        "order_count": status.order_count,
        "funded": status.funded,
    }
    if json_out:
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo(f"Wallet : {status.wallet}")
    typer.echo(f"Address: {status.address}")
    typer.echo(f"Env    : {status.env}")
    typer.echo(f"Equity : ${status.equity_usd:,.2f}")
    typer.echo(f"Margin : ${status.margin_used_usd:,.2f}")
    typer.echo(f"Open positions: {status.position_count}")
    typer.echo(f"Open orders   : {status.order_count}")

    if not status.funded and testnet:
        typer.echo("")
        typer.echo("Testnet wallet is unfunded. Run: nave wallet fund")


@wallet_app.command("fund")
def wallet_fund(
    wallet: Optional[str] = typer.Option(None, "--wallet", "-w", help="Wallet name"),
) -> None:
    """Request testnet USDC from the Hyperliquid faucet (best effort)."""
    settings = _hl_settings()
    wallet_name = wallet or settings.wallet

    try:
        validate_wallet_name(wallet_name)
        status = get_account_status(wallet_name, testnet=True)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"Requesting testnet funds for {status.address} ...")
    try:
        response = request_testnet_faucet(status.address)
        typer.echo(json.dumps(response, indent=2))
    except Exception as exc:
        typer.echo(f"Faucet request failed: {exc}")
        typer.echo("")
        typer.echo("Manual funding options:")
        typer.echo("  1. Visit https://app.hyperliquid-testnet.xyz/drip")
        typer.echo(f"  2. Connect wallet {status.address}")
        typer.echo("  3. Mainnet deposit with the same address may be required first")
        raise typer.Exit(code=1) from exc

    refreshed = get_account_status(wallet_name, testnet=True)
    typer.echo(f"Updated equity: ${refreshed.equity_usd:,.2f}")


@wallet_app.command("test-trade")
def wallet_test_trade(
    wallet: Optional[str] = typer.Option(None, "--wallet", "-w", help="Wallet name"),
    coin: str = typer.Option("ETH", "--coin", help="Perp symbol"),
    side: str = typer.Option("long", "--side", help="long or short"),
    size_usd: Optional[float] = typer.Option(
        None,
        "--size-usd",
        help="Notional size in USD (defaults to HL_MAX_POSITION_USD)",
    ),
    keep_open: bool = typer.Option(
        False,
        "--keep-open",
        help="Leave the position open after the test (default closes immediately)",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Place a real testnet order (default is dry-run preview only)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Run a small Hyperliquid testnet trade to verify signing and execution."""
    settings = _hl_settings()
    wallet_name = wallet or settings.wallet
    notional = size_usd if size_usd is not None else settings.max_position_usd

    if not settings.testnet:
        raise typer.BadParameter(
            "HL_TESTNET=false in .env. Test trades require testnet; set HL_TESTNET=true."
        )

    try:
        status = get_account_status(wallet_name, testnet=True)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    preview = {
        "wallet": wallet_name,
        "env": "TESTNET",
        "coin": coin.upper(),
        "side": side.lower(),
        "size_usd": notional,
        "close_after": not keep_open,
        "equity_usd": status.equity_usd,
        "execute": execute,
    }

    if not execute:
        preview["note"] = "Dry run only. Re-run with --execute to place the testnet order."
        if json_out:
            typer.echo(json.dumps(preview, indent=2))
            return
        typer.echo("Test trade preview (dry run):")
        typer.echo(json.dumps(preview, indent=2))
        return

    if status.equity_usd < notional:
        raise typer.BadParameter(
            f"Insufficient testnet equity (${status.equity_usd:.2f}). "
            f"Run: nave wallet fund --wallet {wallet_name}"
        )

    if not typer.confirm(
        f"Place TESTNET {side} ${notional:.2f} {coin.upper()} with wallet '{wallet_name}'?",
        default=False,
    ):
        typer.echo("Cancelled.")
        raise typer.Exit()

    try:
        result = run_test_trade(
            wallet_name,
            coin=coin,
            side=side,
            size_usd=notional,
            testnet=True,
            close_after=not keep_open,
        )
    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    typer.echo("Test trade completed on TESTNET.")
    typer.echo(json.dumps(result, indent=2, default=str))
