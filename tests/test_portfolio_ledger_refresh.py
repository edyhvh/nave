from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from trading.crypto.chain_audit import summarize_solana_transaction
from trading.stocks.portfolio_ledger import (
    KNOWN_ONDO,
    USDC_MINTS,
    canonicalize_signature,
    economic_key,
    new_fill,
    normalize_existing_fills,
    redact_rpc_error,
    refresh,
    residual_average_cost,
    token_ui_amount,
    upsert_fill,
)

AMZN_MINT = "14Tqdo8V1FhzKsE3W2pFsZCzYPQxxupXRcqw9jv6ondo"
TSLA_MINT = "KeGv7bsfR4MheC1CkmnAVceoApjrkvBhHYjWb67ondo"
USDC_MINT = next(iter(USDC_MINTS))
UNKNOWN_MINT = "NewFutureMint1111111111111111111111ondo"
WALLET = "LedgerTestWallet111111111111111111111111111"


def test_existing_fills_are_normalized_and_deduplicated_by_signature():
    fills = [
        {"symbol": "AMZNON", "side": "BUY", "signature": "sig-1", "usdc_delta": "-100"},
        {
            "symbol": "AMZNON",
            "side": "BUY",
            "mint": AMZN_MINT,
            "signature": "sig-1",
            "usdc_delta": "-100",
        },
    ]
    normalized = normalize_existing_fills(fills)
    assert len(normalized) == 1
    assert normalized[0]["mint"].endswith("ondo")
    assert normalized[0]["underlying"] == "AMZN"


def test_truncated_and_canonical_signatures_merge_on_economic_key():
    fills = [
        {
            "symbol": "TSLAON",
            "mint": TSLA_MINT,
            "side": "BUY",
            "quantity": "0.012138236",
            "usdc_delta": "-5.00",
            "date_utc": "2026-02-20T20:09:14Z",
            "signature": "truncated-sig-87-chars-not-a-real-signature-xxxxxxxxxxxxxxxxxxxxx",
        },
        {
            "symbol": "TSLAON",
            "mint": TSLA_MINT,
            "side": "BUY",
            "quantity": "0.012138236",
            "usdc_delta": "-5",
            "date_utc": "2026-02-20T20:09:14+00:00",
            "signature": "canonical-sig-88-chars-not-a-real-signature-xxxxxxxxxxxxxxxxxxxxxx",
            "reconciliation_status": "confirmed_on_chain",
        },
    ]
    normalized = normalize_existing_fills(fills)
    assert len(normalized) == 1
    assert economic_key(normalized[0])[2] == "0.012138236"
    assert normalized[0]["reconciliation_status"] == "confirmed_on_chain"


def test_unknown_ondo_mint_is_retained_as_pending():
    fill = new_fill(
        {
            "block_time": "2026-08-18T00:00:00+00:00",
            "signature": "sig-unknown",
            "fee_lamports": 5000,
            "token_balance_changes": [{"mint": UNKNOWN_MINT, "decimals": 9}],
        },
        UNKNOWN_MINT,
        1_000_000_000,
        0,
        apply_cash=False,
    )
    assert fill["underlying"] == "UNKNOWN"
    assert fill["reconciliation_status"] == "pending_review"
    assert fill["symbol"].startswith("UNKNOWN:")
    assert normalize_existing_fills([fill])[0]["mint"] == UNKNOWN_MINT


def test_shared_usdc_across_two_mints_stays_pending():
    activity = {
        "block_time": "2026-08-18T00:00:00+00:00",
        "signature": "sig-multi",
        "fee_lamports": 5000,
        "token_balance_changes": [
            {"mint": AMZN_MINT, "decimals": 9},
            {"mint": TSLA_MINT, "decimals": 9},
        ],
    }
    first = new_fill(activity, AMZN_MINT, 10, -100_000_000, apply_cash=False)
    second = new_fill(activity, TSLA_MINT, 20, -100_000_000, apply_cash=False)
    assert first["reconciliation_status"] == "pending_review"
    assert first["usdc_delta"] == "0"
    assert second["usdc_delta"] == "0"


def test_missing_usdc_does_not_lock_out_later_confirmed_fill():
    pending = new_fill(
        {
            "block_time": "2026-08-18T00:00:00+00:00",
            "signature": "sig-upgrade",
            "token_balance_changes": [{"mint": AMZN_MINT, "decimals": 9}],
        },
        AMZN_MINT,
        1_000_000,
        0,
        apply_cash=False,
    )
    confirmed = new_fill(
        {
            "block_time": "2026-08-18T00:00:00+00:00",
            "signature": "sig-upgrade",
            "token_balance_changes": [{"mint": AMZN_MINT, "decimals": 9}],
        },
        AMZN_MINT,
        1_000_000,
        -100_000_000,
        apply_cash=True,
    )
    fills = [pending]
    assert upsert_fill(fills, confirmed) is False
    assert fills[0]["reconciliation_status"] == "confirmed_on_chain"
    assert fills[0]["usdc_delta"] == "-100"


def test_partial_sale_uses_residual_average_cost_not_net_cash():
    fills = [
        {
            "mint": "spy",
            "side": "BUY",
            "quantity": "0.004532114",
            "usdc_delta": "-3.05",
            "date_utc": "2026-03-12T17:10:38Z",
            "reconciliation_status": "confirmed_on_chain",
        },
        {
            "mint": "spy",
            "side": "SELL",
            "quantity": "0.002991235",
            "usdc_delta": "1.806268",
            "date_utc": "2026-03-12T17:11:26Z",
            "reconciliation_status": "confirmed_on_chain",
        },
    ]
    basis = residual_average_cost(fills)
    remaining_qty = Decimal("0.004532114") - Decimal("0.002991235")
    expected_cost = Decimal("3.05") * remaining_qty / Decimal("0.004532114")
    assert basis["cost_basis_status"] == "average_cost_residual"
    assert basis["sale_proceeds_usd"] == Decimal("1.806268")
    assert abs(basis["cost_basis_usd"] - expected_cost) < Decimal("0.000001")
    assert basis["cost_basis_usd"] != Decimal("3.05") - Decimal("1.806268")


def test_pending_fills_are_excluded_from_average_cost():
    fills = [
        {
            "mint": AMZN_MINT,
            "side": "BUY",
            "quantity": "1",
            "usdc_delta": "0",
            "date_utc": "2026-01-01T00:00:00+00:00",
            "reconciliation_status": "pending_review",
        }
    ]
    basis = residual_average_cost(fills)
    assert basis["cost_basis_usd"] == Decimal(0)
    assert basis["cost_basis_status"] == "pending_review"


def test_token_2022_ui_amount_uses_raw_over_decimals():
    assert token_ui_amount("1000000000", 9) == Decimal("1")
    assert token_ui_amount(99, 2) == Decimal("0.99")


def test_rpc_errors_redact_base58_pubkeys():
    raw = "signatures:9CNDXYDZ5iDNrYPTBD4Zdvj4h5VvfCX6pJzQNZjjhaR8: boom"
    redacted = redact_rpc_error(raw)
    assert "9CNDXYDZ5iDNrYPTBD4Zdvj4h5VvfCX6pJzQNZjjhaR8" not in redacted
    assert redacted.startswith("signatures:ref:")


def test_unknown_mint_normalize_does_not_crash():
    fills = [{"mint": UNKNOWN_MINT, "side": "BUY", "signature": "x", "quantity": "1"}]
    assert normalize_existing_fills(fills)[0]["underlying"] == "UNKNOWN"


def _tx(*, signature: str, block_time: int, err=None, balances: list[dict]) -> dict:
    return {
        "slot": 1,
        "blockTime": block_time,
        "meta": {"fee": 5000, "err": err, "preTokenBalances": [], "postTokenBalances": balances},
    }


class _FakeClient:
    def __init__(self, accounts, signatures, transactions):
        self.accounts = accounts
        self.signatures = signatures
        self.transactions = transactions

    def get_token_accounts(self, _owner, mint=None):
        if mint is None:
            return list(self.accounts)
        return [account for account in self.accounts if account.get("mint") == mint]

    def get_signatures(self, address, limit=100, before=None):
        rows = list(self.signatures.get(address, []))
        if before:
            index = next((i for i, row in enumerate(rows) if row.get("signature") == before), None)
            rows = rows[index + 1 :] if index is not None else []
        return rows[:limit]

    def get_transaction(self, signature):
        if signature == "missing":
            raise RuntimeError("rpc down")
        return self.transactions.get(signature)


def _state_and_audit(tmp_path: Path, *, positions=None, fills=None):
    state_path = tmp_path / "portfolio.json"
    audit_path = tmp_path / "ondo_solana_audit.json"
    state = {
        "positions": positions or [{"ticker": "AMZN", "thesis_status": "broken"}],
        "wallets": {"solana": {"address": WALLET}},
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    if fills is not None:
        audit_path.write_text(json.dumps({"fills": fills}), encoding="utf-8")
    return state_path, audit_path


def test_refresh_keeps_unknown_mint_and_does_not_clobber_thesis(tmp_path):
    accounts = [
        {
            "pubkey": "acct-amzn",
            "mint": AMZN_MINT,
            "raw_amount": "413147208",
            "decimals": 9,
        },
        {
            "pubkey": "acct-new",
            "mint": UNKNOWN_MINT,
            "raw_amount": "1000000000",
            "decimals": 9,
        },
    ]
    transactions = {
        "sig-amzn": _tx(
            signature="sig-amzn",
            block_time=1_700_000_000,
            balances=[
                {
                    "accountIndex": 0,
                    "owner": WALLET,
                    "mint": AMZN_MINT,
                    "uiTokenAmount": {"amount": "413147208", "decimals": 9},
                },
                {
                    "accountIndex": 1,
                    "owner": WALLET,
                    "mint": USDC_MINT,
                    "uiTokenAmount": {"amount": "0", "decimals": 6},
                },
            ],
        ),
    }
    # Pre-balance implied by post-only AMZN is a mint-in; add pre USDC so cash applies.
    transactions["sig-amzn"]["meta"]["preTokenBalances"] = [
        {
            "accountIndex": 1,
            "owner": WALLET,
            "mint": USDC_MINT,
            "uiTokenAmount": {"amount": "100000000", "decimals": 6},
        }
    ]
    client = _FakeClient(
        accounts,
        {"acct-amzn": [{"signature": "sig-amzn"}], "acct-new": []},
        transactions,
    )
    state_path, audit_path = _state_and_audit(tmp_path)
    result = refresh(
        state_path=state_path,
        audit_path=audit_path,
        rpc_urls=["https://example.invalid"],
        client_factory=lambda _url: client,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert state["positions"][0]["thesis_status"] == "broken"
    assert all(position["ticker"] != "UNKNOWN" for position in state["positions"])
    assert result["pending_unknown_mints"] == 1
    assert any(row["mint"] == UNKNOWN_MINT for row in audit["positions"])


def test_refresh_rejects_empty_inventory_when_book_has_positions(tmp_path):
    state_path, audit_path = _state_and_audit(tmp_path)
    client = _FakeClient([], {}, {})
    with pytest.raises(RuntimeError, match="empty token account set"):
        refresh(
            state_path=state_path,
            audit_path=audit_path,
            rpc_urls=["https://example.invalid"],
            client_factory=lambda _url: client,
        )
    assert json.loads(state_path.read_text())["positions"][0].get("quantity") is None


def test_failed_transaction_meta_err_does_not_create_fill(tmp_path):
    accounts = [
        {"pubkey": "acct-amzn", "mint": AMZN_MINT, "raw_amount": "1", "decimals": 9}
    ]
    transactions = {
        "sig-fail": _tx(
            signature="sig-fail",
            block_time=1_700_000_000,
            err={"InstructionError": [0, "Custom"]},
            balances=[
                {
                    "accountIndex": 0,
                    "owner": WALLET,
                    "mint": AMZN_MINT,
                    "uiTokenAmount": {"amount": "1", "decimals": 9},
                }
            ],
        )
    }
    client = _FakeClient(accounts, {"acct-amzn": [{"signature": "sig-fail"}]}, transactions)
    state_path, audit_path = _state_and_audit(tmp_path)
    refresh(
        state_path=state_path,
        audit_path=audit_path,
        rpc_urls=["https://example.invalid"],
        client_factory=lambda _url: client,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["fills"] == []


def test_summarize_sums_same_mint_across_account_indexes():
    transaction = {
        "slot": 9,
        "blockTime": 1_700_000_000,
        "meta": {
            "fee": 5000,
            "err": None,
            "preTokenBalances": [
                {
                    "accountIndex": 0,
                    "owner": WALLET,
                    "mint": AMZN_MINT,
                    "uiTokenAmount": {"amount": "5", "decimals": 9},
                },
                {
                    "accountIndex": 1,
                    "owner": WALLET,
                    "mint": AMZN_MINT,
                    "uiTokenAmount": {"amount": "7", "decimals": 9},
                },
            ],
            "postTokenBalances": [
                {
                    "accountIndex": 0,
                    "owner": WALLET,
                    "mint": AMZN_MINT,
                    "uiTokenAmount": {"amount": "6", "decimals": 9},
                },
                {
                    "accountIndex": 1,
                    "owner": WALLET,
                    "mint": AMZN_MINT,
                    "uiTokenAmount": {"amount": "10", "decimals": 9},
                },
            ],
        },
    }
    summary = summarize_solana_transaction(transaction, WALLET, signature="sig")
    assert len(summary["token_balance_changes"]) == 1
    assert summary["token_balance_changes"][0]["delta_raw_amount"] == "4"


def test_canonicalize_rejects_truncated_signatures():
    assert canonicalize_signature("not-a-signature") is None
    assert canonicalize_signature(None) is None


def test_known_ondo_map_still_covers_validated_names():
    assert KNOWN_ONDO[AMZN_MINT] == ("AMZNON", "AMZN")
