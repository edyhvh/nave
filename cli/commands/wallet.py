"""Wallet commands — create EVM wallets and verify Hyperliquid testnet readiness."""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cli.professional_typer import ProfessionalTyper
from core.config import HyperliquidSettings
from trading.crypto.vault import SECRETS_POLICY_MESSAGE
from trading.crypto.wallet_service import (
    DEFAULT_TEST_COIN,
    DEFAULT_TEST_SIZE_USD,
    MIN_MAINNET_DEPOSIT_USDC,
    TESTNET_DRIP_URL,
    claim_testnet_drip,
    create_wallet,
    deposit_mainnet_usdc,
    get_account_status,
    is_mainnet_activated,
    list_wallets,
    run_test_trade,
    setup_default_wallets,
    validate_wallet_name,
    verify_testnet_trading,
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
    """Create the default nave trading wallet (hermes)."""
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
    typer.echo(SECRETS_POLICY_MESSAGE)
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
        typer.echo("Testnet wallet is unfunded or not activated.")
        typer.echo("  1. nave wallet fund")
        typer.echo("  2. https://app.hyperliquid-testnet.xyz/drip")


def _print_activation_steps(address: str) -> None:
    typer.echo("")
    typer.echo("One-time activation required before testnet drip works:")
    typer.echo(f"  1. Send ≥{MIN_MAINNET_DEPOSIT_USDC:.0f} USDC + a little ETH to this address on Arbitrum:")
    typer.echo(f"     {address}")
    typer.echo("     (Withdraw from a CEX directly to Arbitrum network.)")
    typer.echo("  2. Run: nave wallet deposit-mainnet --amount 5")
    typer.echo("  3. Wait ~1 minute, then run: nave wallet claim")
    typer.echo(f"  Or use the web UI: {TESTNET_DRIP_URL} (Connect wallet first)")


@wallet_app.command("claim")
def wallet_claim(
    wallet: Optional[str] = typer.Option(None, "--wallet", "-w", help="Wallet name"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Claim 1,000 mock USDC from Hyperliquid testnet drip."""
    settings = _hl_settings()
    wallet_name = wallet or settings.wallet

    try:
        validate_wallet_name(wallet_name)
        status = get_account_status(wallet_name, testnet=True)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"Claiming testnet drip for {status.address} ...")
    result = claim_testnet_drip(status.address)

    payload = {
        "address": result.address,
        "success": result.success,
        "message": result.message,
        "equity_usd": result.equity_usd,
    }
    if json_out:
        typer.echo(json.dumps(payload, indent=2))
        if not result.success:
            raise typer.Exit(code=1)
        return

    typer.echo(result.message)
    if result.success:
        refreshed = get_account_status(wallet_name, testnet=True)
        typer.echo(f"Testnet equity: ${refreshed.equity_usd:,.2f}")
        return

    if "does not exist on mainnet" in result.message.lower():
        _print_activation_steps(status.address)
    raise typer.Exit(code=1)


@wallet_app.command("fund")
def wallet_fund(
    wallet: Optional[str] = typer.Option(None, "--wallet", "-w", help="Wallet name"),
) -> None:
    """Alias for ``nave wallet claim``."""
    wallet_claim(wallet=wallet, json_out=False)


@wallet_app.command("deposit-mainnet")
def wallet_deposit_mainnet(
    wallet: Optional[str] = typer.Option(None, "--wallet", "-w", help="Wallet name"),
    amount: float = typer.Option(
        MIN_MAINNET_DEPOSIT_USDC,
        "--amount",
        help=f"USDC to send to Hyperliquid bridge (min {MIN_MAINNET_DEPOSIT_USDC})",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Send the Arbitrum USDC transfer (default is preview only)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Deposit USDC on Arbitrum into Hyperliquid mainnet to unlock testnet drip."""
    settings = _hl_settings()
    wallet_name = wallet or settings.wallet

    try:
        validate_wallet_name(wallet_name)
        from trading.crypto.vault import WalletVault

        address = WalletVault().address(wallet_name)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    preview = {
        "wallet": wallet_name,
        "address": address,
        "amount_usdc": amount,
        "minimum_usdc": MIN_MAINNET_DEPOSIT_USDC,
        "execute": execute,
        "mainnet_active": is_mainnet_activated(address),
    }

    if not execute:
        preview["note"] = (
            "Dry run. Fund this address on Arbitrum first, then re-run with --execute."
        )
        if json_out:
            typer.echo(json.dumps(preview, indent=2))
            return
        typer.echo("Mainnet activation preview:")
        typer.echo(json.dumps(preview, indent=2))
        _print_activation_steps(address)
        return

    if not typer.confirm(
        f"Send {amount:.2f} USDC from '{wallet_name}' to Hyperliquid mainnet bridge?",
        default=False,
    ):
        typer.echo("Cancelled.")
        raise typer.Exit()

    try:
        result = deposit_mainnet_usdc(wallet_name, amount)
    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_out:
        typer.echo(json.dumps(result, indent=2))
        return

    typer.echo("Mainnet deposit submitted.")
    typer.echo(json.dumps(result, indent=2))
    typer.echo("Wait ~1 minute, then run: nave wallet claim")


@wallet_app.command("test-trade")
def wallet_test_trade(
    wallet: Optional[str] = typer.Option(None, "--wallet", "-w", help="Wallet name"),
    coin: str = typer.Option(DEFAULT_TEST_COIN, "--coin", help="Perp symbol"),
    side: str = typer.Option("long", "--side", help="long or short"),
    size_usd: Optional[float] = typer.Option(
        None,
        "--size-usd",
        help=f"Notional size in USD (defaults to {DEFAULT_TEST_SIZE_USD:.0f})",
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
    notional = size_usd if size_usd is not None else DEFAULT_TEST_SIZE_USD

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
        "reserve_note": "Keeps most of testnet balance untouched via small BTC size + immediate close",
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


@wallet_app.command("verify-trading")
def wallet_verify_trading(
    wallet: Optional[str] = typer.Option(None, "--wallet", "-w", help="Wallet name"),
    coin: str = typer.Option(DEFAULT_TEST_COIN, "--coin", help="Perp symbol"),
    size_usd: Optional[float] = typer.Option(
        None,
        "--size-usd",
        help=f"Notional size in USD per leg (defaults to {DEFAULT_TEST_SIZE_USD:.0f})",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Run live long+short testnet round trips (default is dry-run preview)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Verify Hyperliquid testnet can open and close both long and short trades."""
    settings = _hl_settings()
    wallet_name = wallet or settings.wallet
    notional = size_usd if size_usd is not None else DEFAULT_TEST_SIZE_USD

    if not settings.testnet:
        raise typer.BadParameter("HL_TESTNET=false. Verification requires testnet.")

    preview = {
        "wallet": wallet_name,
        "env": "TESTNET",
        "coin": coin.upper(),
        "size_usd": notional,
        "steps": ["open long + close", "open short + close"],
        "execute": execute,
        "estimated_max_exposure_usd": notional * 2,
    }

    if not execute:
        preview["note"] = "Dry run only. Re-run with --execute to verify on testnet."
        if json_out:
            typer.echo(json.dumps(preview, indent=2))
            return
        typer.echo("Testnet trading verification preview:")
        typer.echo(json.dumps(preview, indent=2))
        return

    if not typer.confirm(
        f"Run TESTNET long+short verification (${notional:.2f} {coin.upper()}) "
        f"for wallet '{wallet_name}'?",
        default=False,
    ):
        typer.echo("Cancelled.")
        raise typer.Exit()

    try:
        result = verify_testnet_trading(
            wallet_name,
            coin=coin,
            size_usd=notional,
        )
    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    typer.echo("Testnet long and short verification passed.")
    typer.echo(json.dumps(result, indent=2, default=str))
