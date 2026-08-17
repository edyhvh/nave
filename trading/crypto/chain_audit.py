"""Read-only EVM and Solana wallet auditing with public RPCs.

This module deliberately does not manage keys, sign transactions, or send funds.
It provides small adapters for balance and activity discovery; RPC URLs can be
replaced with another public or self-hosted endpoint without changing callers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from web3 import Web3
from web3.types import BlockIdentifier

DEFAULT_EVM_RPC_URLS = {
    "ethereum": "https://cloudflare-eth.com",
    "bsc": "https://bsc-dataseed.binance.org",
}
DEFAULT_SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
TRANSFER_EVENT_SIGNATURE = "Transfer(address,address,uint256)"


@dataclass(frozen=True)
class EvmBalance:
    chain: str
    address: str
    wei: int
    decimals: int = 18

    @property
    def amount(self) -> Decimal:
        return Decimal(self.wei) / (Decimal(10) ** self.decimals)


@dataclass(frozen=True)
class Erc20Balance:
    chain: str
    wallet: str
    token: str
    symbol: str
    raw_balance: int
    decimals: int

    @property
    def amount(self) -> Decimal:
        return Decimal(self.raw_balance) / (Decimal(10) ** self.decimals)


@dataclass(frozen=True)
class SolanaBalance:
    address: str
    lamports: int

    @property
    def sol(self) -> Decimal:
        return Decimal(self.lamports) / Decimal(1_000_000_000)


class EvmRpcClient:
    """Read-only client for Ethereum-compatible JSON-RPC networks."""

    def __init__(self, rpc_url: str, *, chain: str = "evm") -> None:
        self.chain = chain
        self.web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))

    def is_connected(self) -> bool:
        return bool(self.web3.is_connected())

    def get_native_balance(self, address: str) -> EvmBalance:
        checksum = self.web3.to_checksum_address(address)
        return EvmBalance(
            chain=self.chain,
            address=checksum,
            wei=int(self.web3.eth.get_balance(checksum)),
        )

    def get_erc20_balance(self, wallet: str, token: str) -> Erc20Balance:
        wallet_checksum = self.web3.to_checksum_address(wallet)
        token_checksum = self.web3.to_checksum_address(token)
        contract = self.web3.eth.contract(address=token_checksum, abi=ERC20_READ_ABI)
        raw_balance = int(contract.functions.balanceOf(wallet_checksum).call())
        decimals = int(contract.functions.decimals().call())
        symbol = str(contract.functions.symbol().call())
        return Erc20Balance(
            chain=self.chain,
            wallet=wallet_checksum,
            token=token_checksum,
            symbol=symbol,
            raw_balance=raw_balance,
            decimals=decimals,
        )

    def get_transfer_logs(
        self,
        wallet: str,
        *,
        token: str | None = None,
        from_block: BlockIdentifier = 0,
        to_block: BlockIdentifier = "latest",
    ) -> list[dict[str, Any]]:
        """Return ERC-20 Transfer logs involving ``wallet``.

        This is event-level evidence, not a complete transaction/fill history.
        Router swaps and internal transfers require additional transaction/log
        decoding by the caller.
        """
        wallet_checksum = self.web3.to_checksum_address(wallet)
        wallet_topic = "0x" + wallet_checksum[2:].lower().rjust(64, "0")
        event_topic = self.web3.keccak(text=TRANSFER_EVENT_SIGNATURE).hex()
        address = None if token is None else self.web3.to_checksum_address(token)
        logs = self.web3.eth.get_logs(
            {
                "address": address,
                "topics": [event_topic, [wallet_topic], None],
                "fromBlock": from_block,
                "toBlock": to_block,
            }
        )
        reverse_logs = self.web3.eth.get_logs(
            {
                "address": address,
                "topics": [event_topic, None, [wallet_topic]],
                "fromBlock": from_block,
                "toBlock": to_block,
            }
        )
        return [_normalize_log(log) for log in [*logs, *reverse_logs]]


class SolanaRpcClient:
    """Read-only client for Solana JSON-RPC."""

    def __init__(self, rpc_url: str = DEFAULT_SOLANA_RPC_URL) -> None:
        from solana.rpc.api import Client

        self.client = Client(rpc_url)

    def get_native_balance(self, address: str) -> SolanaBalance:
        from solders.pubkey import Pubkey

        public_key = Pubkey.from_string(address)
        response = self.client.get_balance(public_key)
        return SolanaBalance(address=str(public_key), lamports=int(response.value))

    def get_token_accounts(self, owner: str, *, mint: str | None = None) -> list[dict[str, Any]]:
        from solana.rpc.types import TokenAccountOpts
        from solders.pubkey import Pubkey

        owner_key = Pubkey.from_string(owner)
        opts = None if mint is None else TokenAccountOpts(mint=Pubkey.from_string(mint))
        response = self.client.get_token_accounts_by_owner(owner_key, opts)
        accounts = response.value
        return [
            {
                "pubkey": str(item.pubkey),
                "account": (
                    item.account.to_json()
                    if hasattr(item.account, "to_json")
                    else item.account
                ),
            }
            for item in accounts
        ]

    def get_signatures(self, address: str, *, limit: int = 100) -> list[dict[str, Any]]:
        from solders.pubkey import Pubkey

        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        response = self.client.get_signatures_for_address(Pubkey.from_string(address), limit=limit)
        return [item.to_json() if hasattr(item, "to_json") else item for item in response.value]


ERC20_READ_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def _normalize_log(log: Any) -> dict[str, Any]:
    return {
        "address": str(log["address"]),
        "block_number": int(log["blockNumber"]),
        "transaction_hash": log["transactionHash"].hex(),
        "log_index": int(log["logIndex"]),
        "topics": [topic.hex() for topic in log["topics"]],
        "data": log["data"],
    }


def build_evm_snapshot(client: EvmRpcClient, address: str) -> dict[str, Any]:
    """Build a JSON-safe native-balance snapshot for an EVM address."""
    balance = client.get_native_balance(address)
    return {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "chain": balance.chain,
        "address": balance.address,
        "native_balance": {
            "raw": str(balance.wei),
            "decimals": balance.decimals,
            "amount": str(balance.amount),
        },
        "source": "public_rpc",
    }


def build_solana_snapshot(client: SolanaRpcClient, address: str) -> dict[str, Any]:
    """Build a JSON-safe SOL balance snapshot for a public address."""
    balance = client.get_native_balance(address)
    return {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "chain": "solana",
        "address": balance.address,
        "native_balance": {
            "raw": str(balance.lamports),
            "decimals": 9,
            "amount": str(balance.sol),
            "unit": "SOL",
        },
        "source": "public_rpc",
    }


def write_snapshot(snapshot: dict[str, Any], path: str | Path) -> Path:
    """Write an explicitly requested snapshot, creating parent directories."""
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return destination
