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

from trading.crypto.client import MAINNET_API, TESTNET_API, HyperliquidClient
from trading.crypto.vault import WalletVault

DEFAULT_WALLET_NAME = "hermes"
DEFAULT_TEST_COIN = "BTC"
DEFAULT_TEST_SIZE_USD = 50.0
MIN_TEST_SIZE_USD = 25.0
ARBITRUM_USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
HL_BRIDGE_MAINNET = "0x2df1c51e09aecf9cacb7bc98cb1742757f163df7"
ARBITRUM_RPC_URL = "https://arb1.arbitrum.io/rpc"
MIN_MAINNET_DEPOSIT_USDC = 5.0
TESTNET_DRIP_URL = "https://app.hyperliquid-testnet.xyz/drip"
DEFAULT_WALLET_NAMES = (DEFAULT_WALLET_NAME,)
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


@dataclass(frozen=True)
class DripClaimResult:
    address: str
    success: bool
    message: str
    equity_usd: float | None = None


def _parse_info_response(response: requests.Response) -> Any:
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return response.text


def is_mainnet_activated(address: str) -> bool:
    """Return True after a mainnet bridge deposit has credited the address."""
    response = requests.post(
        f"{MAINNET_API}/info",
        json={"type": "clearinghouseState", "user": address},
        timeout=15,
    )
    data = _parse_info_response(response)
    if not isinstance(data, dict):
        return False
    margin = data.get("marginSummary", {})
    return float(margin.get("accountValue", 0) or 0) >= MIN_MAINNET_DEPOSIT_USDC


def claim_testnet_drip(address: str) -> DripClaimResult:
    """Claim 1,000 mock USDC from Hyperliquid testnet drip."""
    response = requests.post(
        f"{TESTNET_API}/info",
        json={"type": "claimDrip", "user": address},
        timeout=15,
    )
    body = _parse_info_response(response)
    message = body if isinstance(body, str) else str(body)
    success = "claimed" in message.lower() or "success" in message.lower()

    equity_usd = None
    if success:
        state = requests.post(
            f"{TESTNET_API}/info",
            json={"type": "clearinghouseState", "user": address},
            timeout=15,
        ).json()
        if isinstance(state, dict):
            equity_usd = float(state.get("marginSummary", {}).get("accountValue", 0) or 0)

    return DripClaimResult(
        address=address,
        success=success,
        message=message,
        equity_usd=equity_usd,
    )


def request_testnet_faucet(address: str) -> dict[str, Any]:
    """Claim testnet drip via Hyperliquid /info."""
    result = claim_testnet_drip(address)
    return {
        "address": result.address,
        "success": result.success,
        "message": result.message,
        "equity_usd": result.equity_usd,
    }


def deposit_mainnet_usdc(
    wallet_name: str,
    amount_usdc: float,
    *,
    vault: WalletVault | None = None,
    rpc_url: str = ARBITRUM_RPC_URL,
) -> dict[str, Any]:
    """Send native Arbitrum USDC to the Hyperliquid bridge to activate mainnet."""
    if amount_usdc < MIN_MAINNET_DEPOSIT_USDC:
        raise ValueError(
            f"Minimum mainnet deposit is {MIN_MAINNET_DEPOSIT_USDC} USDC. "
            f"Smaller amounts are not credited."
        )

    from eth_account import Account
    from web3 import Web3

    vault = vault or WalletVault()
    normalized = validate_wallet_name(wallet_name)
    if not vault.exists(normalized):
        raise FileNotFoundError(f"No wallet found for '{normalized}'.")

    private_key = vault.private_key(normalized)
    account = Account.from_key(private_key)
    del private_key

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError(f"Could not connect to Arbitrum RPC: {rpc_url}")

    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(ARBITRUM_USDC),
        abi=[
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"},
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            },
        ],
    )

    sender = Web3.to_checksum_address(account.address)
    bridge = Web3.to_checksum_address(HL_BRIDGE_MAINNET)
    amount_wei = int(round(amount_usdc * 1_000_000))

    usdc_balance = int(usdc.functions.balanceOf(sender).call())
    if usdc_balance < amount_wei:
        raise ValueError(
            f"Insufficient Arbitrum USDC on {sender}. "
            f"Have ${usdc_balance / 1_000_000:.2f}, need ${amount_usdc:.2f}. "
            f"Withdraw USDC on Arbitrum to this address first."
        )

    eth_balance = int(w3.eth.get_balance(sender))
    if eth_balance == 0:
        raise ValueError(
            f"No ETH on Arbitrum for gas at {sender}. "
            "Send a small amount of ETH on Arbitrum (≈0.001 ETH is enough)."
        )

    nonce = w3.eth.get_transaction_count(sender)
    chain_id = int(w3.eth.chain_id)
    tx = usdc.functions.transfer(bridge, amount_wei).build_transaction(
        {
            "from": sender,
            "nonce": nonce,
            "chainId": chain_id,
            "gas": 120_000,
        }
    )
    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    return {
        "wallet": normalized,
        "address": sender,
        "amount_usdc": amount_usdc,
        "bridge": bridge,
        "tx_hash": tx_hash.hex(),
        "arbiscan": f"https://arbiscan.io/tx/{tx_hash.hex()}",
        "note": "Mainnet credit usually arrives in under 1 minute.",
    }


TESTNET_ACTIVATION_URL = TESTNET_DRIP_URL


def _order_statuses(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    response = raw.get("response")
    if not isinstance(response, dict):
        return []
    data = response.get("data")
    if not isinstance(data, dict):
        return []
    statuses = data.get("statuses", [])
    return [row for row in statuses if isinstance(row, dict)]


def _trade_succeeded(raw: Any) -> bool:
    if raw is None:
        return False
    if isinstance(raw, dict) and str(raw.get("status", "")).lower() == "err":
        return False

    statuses = _order_statuses(raw)
    if statuses:
        if any("filled" in row for row in statuses):
            return True
        return not any("error" in row for row in statuses)

    if isinstance(raw, dict) and str(raw.get("status", "")).lower() in {"ok", "success"}:
        return True
    return False


def _trade_error_message(raw: Any) -> str:
    if isinstance(raw, dict) and str(raw.get("status", "")).lower() == "err":
        return str(raw.get("response", "unknown exchange error"))

    for row in _order_statuses(raw):
        if "error" in row:
            return str(row["error"])
    return str(raw)


def _raise_trade_error(side: str, raw: Any) -> None:
    message = _trade_error_message(raw)
    if "does not exist" in message.lower():
        raise RuntimeError(
            f"Hyperliquid testnet account is not activated for this wallet. "
            f"Visit {TESTNET_ACTIVATION_URL} and claim testnet USDC, then retry."
        )
    raise RuntimeError(f"Testnet {side} trade failed: {message}")


def run_test_trade(
    wallet_name: str,
    *,
    coin: str = DEFAULT_TEST_COIN,
    side: str = "long",
    size_usd: float = DEFAULT_TEST_SIZE_USD,
    testnet: bool = True,
    close_after: bool = True,
    vault: WalletVault | None = None,
    client: HyperliquidClient | None = None,
) -> dict[str, Any]:
    """Open (and optionally close) a small market position for connectivity testing."""
    if not testnet:
        raise ValueError("Test trades are restricted to testnet. Pass testnet=True.")

    normalized = validate_wallet_name(wallet_name)
    status = get_account_status(normalized, testnet=testnet, vault=vault)
    reserve_usd = max(size_usd * 3, 100.0)
    if status.equity_usd < size_usd + reserve_usd:
        raise ValueError(
            f"Insufficient testnet equity (${status.equity_usd:.2f}) for a safe "
            f"${size_usd:.2f} test trade with reserve. "
            f"Fund the wallet first: nave wallet claim --wallet {normalized}"
        )
    if size_usd < MIN_TEST_SIZE_USD:
        raise ValueError(
            f"Test trade size must be at least ${MIN_TEST_SIZE_USD:.0f} on testnet."
        )

    client = client or HyperliquidClient(wallet_name=normalized, testnet=testnet)
    coin = coin.upper()
    if side not in {"long", "short"}:
        raise ValueError("side must be 'long' or 'short'")

    open_result = client.market_open(coin, side, size_usd)
    open_ok = _trade_succeeded(open_result)
    result: dict[str, Any] = {
        "wallet": normalized,
        "env": client.env,
        "coin": coin,
        "side": side,
        "size_usd": size_usd,
        "open": open_result,
        "open_ok": open_ok,
    }
    if not open_ok:
        _raise_trade_error(side, open_result)

    if close_after:
        if not client.get_open_positions():
            raise RuntimeError(
                f"Expected an open {coin} position before close, but none was found."
            )
        close_result = client.market_close(coin)
        close_ok = _trade_succeeded(close_result)
        result["close"] = close_result
        result["close_ok"] = close_ok
        if not close_ok:
            _raise_trade_error(f"close {side}", close_result)
    return result


def verify_testnet_trading(
    wallet_name: str = DEFAULT_WALLET_NAME,
    *,
    coin: str = DEFAULT_TEST_COIN,
    size_usd: float = DEFAULT_TEST_SIZE_USD,
    vault: WalletVault | None = None,
    client: HyperliquidClient | None = None,
) -> dict[str, Any]:
    """Run long and short round-trip test trades on Hyperliquid testnet."""
    normalized = validate_wallet_name(wallet_name)
    results: dict[str, Any] = {
        "wallet": normalized,
        "coin": coin.upper(),
        "size_usd": size_usd,
        "env": "TESTNET",
        "sides": {},
    }

    for side in ("long", "short"):
        trade = run_test_trade(
            normalized,
            coin=coin,
            side=side,
            size_usd=size_usd,
            testnet=True,
            close_after=True,
            vault=vault,
            client=client,
        )
        results["sides"][side] = trade
        if not trade.get("open_ok") or not trade.get("close_ok"):
            raise RuntimeError(f"Testnet {side} trade verification failed.")

    results["verified"] = True
    return results
