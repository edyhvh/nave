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
        normalized: list[dict[str, Any]] = []
        program_ids = (
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        )
        for program_id in program_ids:
            opts = TokenAccountOpts(
                program_id=Pubkey.from_string(program_id),
                mint=None if mint is None else Pubkey.from_string(mint),
            )
            response = self.client.get_token_accounts_by_owner_json_parsed(owner_key, opts)
            for item in response.value:
                account = item.account.to_json() if hasattr(item.account, "to_json") else item.account
                if isinstance(account, str):
                    account = json.loads(account)
                parsed = (((account.get("data") or {}).get("parsed") or {}).get("info") or {})
                token_amount = parsed.get("tokenAmount") or {}
                normalized.append(
                    {
                        "pubkey": str(item.pubkey),
                        "program_id": program_id,
                        "mint": parsed.get("mint"),
                        "owner": parsed.get("owner"),
                        "state": parsed.get("state"),
                        "raw_amount": token_amount.get("amount"),
                        "decimals": token_amount.get("decimals"),
                        "amount": (
                            str(
                                Decimal(token_amount["amount"])
                                / (Decimal(10) ** int(token_amount["decimals"]))
                            )
                            if token_amount.get("amount") is not None
                            and token_amount.get("decimals") is not None
                            else None
                        ),
                        "rpc_ui_amount": token_amount.get("uiAmountString"),
                        "account_lamports": account.get("lamports"),
                    }
                )
        return normalized

    def get_signatures(
        self,
        address: str,
        *,
        limit: int = 100,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        from solders.pubkey import Pubkey
        from solders.signature import Signature

        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        response = self.client.get_signatures_for_address(
            Pubkey.from_string(address),
            before=None if before is None else Signature.from_string(before),
            limit=limit,
        )
        normalized: list[dict[str, Any]] = []
        for item in response.value:
            row = item.to_json() if hasattr(item, "to_json") else item
            if isinstance(row, str):
                row = json.loads(row)
            normalized.append(row)
        return normalized

    def get_all_signatures(self, address: str, *, max_items: int = 5_000) -> list[dict[str, Any]]:
        """Page backward through address history up to a bounded safety limit."""
        if not 1 <= max_items <= 50_000:
            raise ValueError("max_items must be between 1 and 50000")
        rows: list[dict[str, Any]] = []
        before = None
        while len(rows) < max_items:
            page = self.get_signatures(
                address,
                limit=min(1_000, max_items - len(rows)),
                before=before,
            )
            if not page:
                break
            rows.extend(page)
            before = page[-1].get("signature")
            if len(page) < 1_000:
                break
        return rows[:max_items]

    def get_transaction(self, signature: str) -> dict[str, Any] | None:
        """Return one parsed transaction for evidence-level activity review."""
        from solders.signature import Signature

        response = self.client.get_transaction(
            Signature.from_string(signature),
            encoding="jsonParsed",
            max_supported_transaction_version=0,
        )
        value = response.value
        if value is None:
            return None
        row = value.to_json() if hasattr(value, "to_json") else value
        return json.loads(row) if isinstance(row, str) else row


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


def build_solana_snapshot(
    client: SolanaRpcClient,
    address: str,
    *,
    history_limit: int = 100,
) -> dict[str, Any]:
    """Build a JSON-safe SOL, SPL, and recent-activity snapshot."""
    balance = client.get_native_balance(address)
    token_accounts = client.get_token_accounts(address)
    signatures = client.get_all_signatures(address, max_items=history_limit)
    activity: list[dict[str, Any]] = []
    for signature in signatures:
        try:
            transaction = client.get_transaction(signature["signature"])
            if transaction is not None:
                activity.append(
                    _summarize_solana_transaction(
                        transaction, address, signature=signature["signature"]
                    )
                )
        except Exception as exc:  # one unavailable transaction must not erase the snapshot
            activity.append(
                {
                    "signature": signature.get("signature"),
                    "status": "unavailable",
                    "error": str(exc),
                }
            )
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
        "token_accounts": token_accounts,
        "recent_signatures": signatures,
        "activity": activity,
        "platform_fee_usd": 0.0,
        "source": "public_rpc",
    }


def _summarize_solana_transaction(
    transaction: dict[str, Any], wallet: str, *, signature: str | None = None
) -> dict[str, Any]:
    """Extract evidence useful for cost-basis review without guessing a swap."""
    meta = transaction.get("meta") or {}
    changes: list[dict[str, Any]] = []
    before = {
        (row.get("owner"), row.get("mint")): row.get("uiTokenAmount") or {}
        for row in meta.get("preTokenBalances") or []
        if row.get("owner") == wallet
    }
    after = {
        (row.get("owner"), row.get("mint")): row.get("uiTokenAmount") or {}
        for row in meta.get("postTokenBalances") or []
        if row.get("owner") == wallet
    }
    for key in sorted(set(before) | set(after)):
        pre = before.get(key, {})
        post = after.get(key, {})
        pre_raw = int(pre.get("amount", 0))
        post_raw = int(post.get("amount", 0))
        if pre_raw != post_raw:
            changes.append(
                {
                    "mint": key[1],
                    "decimals": post.get("decimals", pre.get("decimals")),
                    "pre_raw_amount": str(pre_raw),
                    "post_raw_amount": str(post_raw),
                    "delta_raw_amount": str(post_raw - pre_raw),
                }
            )
    block_time = transaction.get("blockTime")
    return {
        "signature": signature,
        "slot": transaction.get("slot"),
        "block_time": (
            datetime.fromtimestamp(block_time, UTC).isoformat() if block_time is not None else None
        ),
        "fee_lamports": meta.get("fee"),
        "err": meta.get("err"),
        "token_balance_changes": changes,
        "classification": "on_chain_evidence_only",
    }


def write_snapshot(snapshot: dict[str, Any], path: str | Path) -> Path:
    """Write an explicitly requested snapshot, creating parent directories."""
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return destination
