from __future__ import annotations

import json
from decimal import Decimal

import pytest

from trading.crypto.chain_audit import (
    EvmRpcClient,
    SolanaBalance,
    SolanaRpcClient,
    summarize_solana_transaction,
    write_snapshot,
)


class _FakeContract:
    def __init__(self):
        self.functions = _FakeContractFunctions()


class _FakeContractFunctions:
    def balanceOf(self, _wallet):
        return _FakeCall(1_250_000)

    def decimals(self):
        return _FakeCall(6)

    def symbol(self):
        return _FakeCall("USDC")


class _FakeCall:
    def __init__(self, value):
        self.value = value

    def call(self):
        return self.value


class _FakeEth:
    def get_balance(self, _address):
        return 2_000_000_000_000_000_000

    def contract(self, **_kwargs):
        return _FakeContract()


class _FakeWeb3:
    eth = _FakeEth()

    @staticmethod
    def to_checksum_address(address):
        return address.lower()


def test_evm_native_balance_is_decimal() -> None:
    client = object.__new__(EvmRpcClient)
    client.chain = "bsc"
    client.web3 = _FakeWeb3()

    balance = client.get_native_balance("0xABC")

    assert balance.chain == "bsc"
    assert balance.wei == 2_000_000_000_000_000_000
    assert balance.amount == Decimal(2)


def test_erc20_balance_reads_metadata_and_amount() -> None:
    client = object.__new__(EvmRpcClient)
    client.chain = "bsc"
    client.web3 = _FakeWeb3()

    balance = client.get_erc20_balance("0xWALLET", "0xTOKEN")

    assert balance.symbol == "USDC"
    assert balance.raw_balance == 1_250_000
    assert balance.amount == Decimal("1.25")


def test_solana_balance_converts_lamports() -> None:
    balance = SolanaBalance(
        address="11111111111111111111111111111111",
        lamports=1_500_000_000,
    )

    assert balance.sol == Decimal("1.5")


def test_solana_native_balance_uses_public_key(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        value = 42

    class _Client:
        def __init__(self, _url):
            pass

        def get_balance(self, public_key):
            assert str(public_key) == "11111111111111111111111111111111"
            return _Response()

    monkeypatch.setattr("solana.rpc.api.Client", _Client)
    client = SolanaRpcClient("https://example.invalid")
    result = client.get_native_balance("11111111111111111111111111111111")

    assert result.lamports == 42


def test_solana_signature_limit_is_bounded() -> None:
    client = object.__new__(SolanaRpcClient)
    client.client = object()

    with pytest.raises(ValueError, match="between 1 and 1000"):
        client.get_signatures("11111111111111111111111111111111", limit=1001)


def test_summarize_aggregates_same_mint_across_token_accounts() -> None:
    wallet = "Wallet1111111111111111111111111111111111111"
    mint = "Mint111111111111111111111111111111111111111"
    transaction = {
        "slot": 2,
        "blockTime": 1_700_000_100,
        "meta": {
            "fee": 5000,
            "err": None,
            "preTokenBalances": [
                {
                    "accountIndex": 4,
                    "owner": wallet,
                    "mint": mint,
                    "uiTokenAmount": {"amount": "10", "decimals": 6},
                },
                {
                    "accountIndex": 7,
                    "owner": wallet,
                    "mint": mint,
                    "uiTokenAmount": {"amount": "3", "decimals": 6},
                },
            ],
            "postTokenBalances": [
                {
                    "accountIndex": 4,
                    "owner": wallet,
                    "mint": mint,
                    "uiTokenAmount": {"amount": "11", "decimals": 6},
                },
                {
                    "accountIndex": 7,
                    "owner": wallet,
                    "mint": mint,
                    "uiTokenAmount": {"amount": "8", "decimals": 6},
                },
            ],
        },
    }

    summary = summarize_solana_transaction(transaction, wallet, signature="sig")

    assert summary["token_balance_changes"] == [
        {
            "mint": mint,
            "decimals": 6,
            "pre_raw_amount": "13",
            "post_raw_amount": "19",
            "delta_raw_amount": "6",
        }
    ]


def test_write_snapshot_creates_json_file(tmp_path) -> None:
    path = write_snapshot({"chain": "solana", "address": "public"}, tmp_path / "audit.json")

    assert path.exists()
    assert json.loads(path.read_text()) == {"chain": "solana", "address": "public"}
