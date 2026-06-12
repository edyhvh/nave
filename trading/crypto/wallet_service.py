"""
Hyperliquid wallet lifecycle — generate EVM wallets and inspect testnet readiness.

Wallets are stored in the encrypted local vault (~/.secrets/nave-wallets/).
The same EVM address is used on Hyperliquid mainnet and testnet; no separate
"link" step is required beyond funding the testnet account.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests

from trading.crypto.client import TESTNET_API, HyperliquidClient
from trading.crypto.vault import WalletVault

DEFAULT_WALLET_NAMES = ("ironclaw", "openfang", "hermes")
_WALLET_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


@dataclass(frozen=True)
class WalletRecord:
    name: str
    address: str


@dataclass(frozen=True)
class WalletCreateResult:
    created: list[WalletRecord]
    skipped: list[str]


@dataclass(frozen=True)
class AccountStatus:
    wallet: str
    address: str
    env: str
    equity_usd: float
    margin_used_usd: float
    position_count: int
    order_count: int
    funded: bool


def validate_wallet_name(name: str) -> str:
    normalized = name.strip().lower()
    if not _WALLET_NAME_RE.fullmatch(normalized):
        raise ValueError(
            "Wallet name must start with a letter and use only lowercase letters, "
            "digits, underscores, or hyphens (max 32 chars)."
        )
    return normalized


def generate_evm_wallet() -> dict[str, str]:
    """Generate a BIP39 mnemonic and derive an EVM HD wallet (m/44'/60'/0'/0/0)."""
    from mnemonic import Mnemonic
    from eth_account import Account

    Account.enable_unaudited_hdwallet_features()
    mnemonic = Mnemonic("english").generate(strength=256)
    account = Account.from_mnemonic(mnemonic, account_path="m/44'/60'/0'/0/0")
    return {
        "mnemonic": mnemonic,
        "address": account.address,
        "private_key": account.key.hex(),
    }


def create_wallet(name: str, vault: WalletVault | None = None) -> WalletRecord:
    """Create and store a new wallet. Raises if the name already exists."""
    vault = vault or WalletVault()
    normalized = validate_wallet_name(name)
    if vault.exists(normalized):
        raise FileExistsError(f"Wallet '{normalized}' already exists.")

    wallet = generate_evm_wallet()
    vault.store(
        normalized,
        mnemonic=wallet["mnemonic"],
        address=wallet["address"],
        private_key=wallet["private_key"],
    )
    return WalletRecord(name=normalized, address=wallet["address"])


def setup_default_wallets(
    names: tuple[str, ...] = DEFAULT_WALLET_NAMES,
    vault: WalletVault | None = None,
) -> WalletCreateResult:
    """Create the standard nave wallets, skipping any that already exist."""
    vault = vault or WalletVault()
    created: list[WalletRecord] = []
    skipped: list[str] = []

    for raw_name in names:
        name = validate_wallet_name(raw_name)
        if vault.exists(name):
            skipped.append(name)
            continue
        record = create_wallet(name, vault=vault)
        created.append(record)

    return WalletCreateResult(created=created, skipped=skipped)


def list_wallets(vault: WalletVault | None = None) -> list[WalletRecord]:
    vault = vault or WalletVault()
    return [
        WalletRecord(name=name, address=vault.address(name))
        for name in sorted(vault.list_wallets())
    ]


def get_account_status(
    wallet_name: str,
    *,
    testnet: bool = True,
    vault: WalletVault | None = None,
) -> AccountStatus:
    """Return a safe account summary for Hyperliquid (no private data)."""
    vault = vault or WalletVault()
    normalized = validate_wallet_name(wallet_name)
    if not vault.exists(normalized):
        raise FileNotFoundError(
            f"No wallet found for '{normalized}'. Run: nave wallet create --name {normalized}"
        )

    client = HyperliquidClient(wallet_name=normalized, testnet=testnet)
    state = client.get_account_state()
    margin = state.get("marginSummary", {})
    equity = float(margin.get("accountValue", 0) or 0)
    margin_used = float(margin.get("totalMarginUsed", 0) or 0)

    return AccountStatus(
        wallet=normalized,
        address=client.address,
        env=client.env,
        equity_usd=equity,
        margin_used_usd=margin_used,
        position_count=len(client.get_open_positions()),
        order_count=len(client.get_open_orders()),
        funded=equity > 0,
    )


def request_testnet_faucet(address: str) -> dict[str, Any]:
    """Best-effort testnet faucet request via Hyperliquid /info."""
    payload = {"type": "userFaucet", "user": address}
    response = requests.post(f"{TESTNET_API}/info", json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {"response": data}


def run_test_trade(
    wallet_name: str,
    *,
    coin: str = "ETH",
    side: str = "long",
    size_usd: float = 10.0,
    testnet: bool = True,
    close_after: bool = True,
    vault: WalletVault | None = None,
) -> dict[str, Any]:
    """Open (and optionally close) a small market position for connectivity testing."""
    if not testnet:
        raise ValueError("Test trades are restricted to testnet. Pass testnet=True.")

    normalized = validate_wallet_name(wallet_name)
    status = get_account_status(normalized, testnet=testnet, vault=vault)
    if status.equity_usd < size_usd:
        raise ValueError(
            f"Insufficient testnet equity (${status.equity_usd:.2f}). "
            f"Fund the wallet first: nave wallet fund --wallet {normalized}"
        )

    client = HyperliquidClient(wallet_name=normalized, testnet=testnet)
    coin = coin.upper()
    if side not in {"long", "short"}:
        raise ValueError("side must be 'long' or 'short'")

    open_result = client.market_open(coin, side, size_usd)
    result: dict[str, Any] = {
        "wallet": normalized,
        "env": client.env,
        "coin": coin,
        "side": side,
        "size_usd": size_usd,
        "open": open_result,
    }
    if close_after:
        result["close"] = client.market_close(coin)
    return result
