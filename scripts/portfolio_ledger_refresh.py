#!/usr/bin/env python3
"""Read-only, idempotent Solana ONDO ledger refresh for the local portfolio.

This script never signs, submits, or executes transactions. It only records
on-chain evidence and updates the local human-gated portfolio state.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with redirect_stdout(io.StringIO()):
    from trading.crypto.chain_audit import (
        SolanaRpcClient,
        _summarize_solana_transaction,
    )

STATE = Path(os.path.expanduser("~/.hermes/state/portfolio_manager/portfolio.json"))
AUDIT = Path(os.path.expanduser("~/.hermes/state/portfolio_manager/ondo_solana_audit.json"))
RPC_URLS = [
    url.strip()
    for url in os.environ.get(
        "SOLANA_RPC_URLS",
        "https://solana-rpc.publicnode.com,https://api.mainnet-beta.solana.com",
    ).split(",")
    if url.strip()
]
USDC_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}
# Officially validated local mapping. Unknown future ONDO mints remain pending.
KNOWN_ONDO = {
    "14Tqdo8V1FhzKsE3W2pFsZCzYPQxxupXRcqw9jv6ondo": ("AMZNON", "AMZN"),
    "fDxs5y12E7x7jBwCKBXGqt71uJmCWsAQ3Srkte6ondo": ("METAON", "META"),
    "FRmH6iRkMr33DLG6zVLR7EM4LojBFAuq6NtFzG6ondo": ("MSFTON", "MSFT"),
    "Wk8gC6iTNp8dqd4ghkJ3h1giiUnyhykwHh7tYWjondo": ("BACON", "BAC"),
    "6btaz134wjHkR8sqhAYrtSM6tavftfxnRvnyMd8ondo": ("COSTON", "COST"),
    "CY8ttw5rYCT6fFBJwqXofefqa7Ji9E8zfLmhRLmondo": ("FCXON", "FCX"),
    "KeGv7bsfR4MheC1CkmnAVceoApjrkvBhHYjWb67ondo": ("TSLAON", "TSLA"),
    "k18WJUULWheRkSpSquYGdNNmtuE2Vbw1hpuUi92ondo": ("SPYon", "SPY"),
}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _decimal_amount(raw: int | str, decimals: int) -> str:
    return str(Decimal(str(raw)) / (Decimal(10) ** decimals))


def _new_fill(activity: dict[str, Any], mint: str, ondo_delta: int, usdc_delta: int) -> dict[str, Any]:
    symbol, underlying = KNOWN_ONDO.get(mint, (f"UNKNOWN:{mint}", "UNKNOWN"))
    decimals = next(
        (int(change.get("decimals")) for change in activity.get("token_balance_changes", [])
         if change.get("mint") == mint and change.get("decimals") is not None),
        9,
    )
    side = "BUY" if ondo_delta > 0 else "SELL"
    return {
        "symbol": symbol,
        "underlying": underlying,
        "mint": mint,
        "side": side,
        "date_utc": activity.get("block_time"),
        "quantity": _decimal_amount(abs(ondo_delta), decimals),
        "usdc_delta": str(Decimal(usdc_delta) / Decimal(10**6)),
        "network_fee_lamports": activity.get("fee_lamports"),
        "signature": activity.get("signature"),
        "reconciliation_status": "confirmed_on_chain" if usdc_delta != 0 else "pending_review",
        "evidence": "token_balance_delta_plus_usdc_balance_delta",
    }


def _normalize_existing_fills(fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    mint_by_symbol = {symbol: mint for mint, (symbol, _) in KNOWN_ONDO.items()}
    for fill in fills:
        symbol = fill.get("symbol")
        mint = fill.get("mint") or mint_by_symbol.get(symbol)
        key = (fill.get("signature"), mint or symbol, fill.get("side"))
        if key in seen:
            continue
        seen.add(key)
        row = dict(fill)
        if mint:
            row["mint"] = mint
            row.setdefault("underlying", KNOWN_ONDO[mint][1])
        normalized.append(row)
    return normalized


def refresh() -> dict[str, Any]:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    previous = json.loads(AUDIT.read_text(encoding="utf-8")) if AUDIT.exists() else {}
    wallet = state["wallets"]["solana"]["address"]
    client = None
    token_accounts: list[dict[str, Any]] = []
    rpc_errors: list[str] = []
    for rpc_url in RPC_URLS:
        try:
            candidate = SolanaRpcClient(rpc_url)
            token_accounts = candidate.get_token_accounts(wallet)
            client = candidate
            break
        except Exception as exc:
            rpc_errors.append(f"{rpc_url}: {exc}")
    if client is None:
        raise RuntimeError("all Solana RPC endpoints failed: " + " | ".join(rpc_errors))
    ondo_accounts = [account for account in token_accounts if account.get("mint") in KNOWN_ONDO]

    previous_fill_count = len(_normalize_existing_fills(list(previous.get("fills", []))))
    existing_fills = _normalize_existing_fills(list(previous.get("fills", [])))
    seen = {(fill.get("signature"), fill.get("mint"), fill.get("side")) for fill in existing_fills}
    activities: list[dict[str, Any]] = []
    signatures: dict[str, dict[str, Any]] = {}
    for account in ondo_accounts:
        try:
            account_signatures = client.get_signatures(account["pubkey"], limit=100)
        except Exception as exc:
            rpc_errors.append(f"signatures:{account['pubkey']}: {exc}")
            continue
        for row in account_signatures:
            signature = row.get("signature")
            if signature:
                signatures[signature] = row

    for signature in signatures:
        try:
            transaction = client.get_transaction(signature)
            if transaction is None:
                continue
            activity = _summarize_solana_transaction(transaction, wallet, signature=signature)
            activities.append(activity)
            changes = activity.get("token_balance_changes", [])
            ondo_changes = [change for change in changes if change.get("mint") in KNOWN_ONDO]
            usdc_delta = sum(
                int(change.get("delta_raw_amount", 0))
                for change in changes
                if change.get("mint") in USDC_MINTS
            )
            for change in ondo_changes:
                ondo_delta = int(change.get("delta_raw_amount", 0))
                if not ondo_delta:
                    continue
                fill = _new_fill(activity, change["mint"], ondo_delta, usdc_delta)
                key = (fill["signature"], fill["mint"], fill["side"])
                if key not in seen:
                    existing_fills.append(fill)
                    seen.add(key)
        except Exception as exc:
            activities.append({"signature": signature, "status": "unavailable", "error": str(exc)})

    by_mint: dict[str, Decimal] = {}
    for account in ondo_accounts:
        mint = account.get("mint")
        if mint and account.get("raw_amount") is not None and account.get("decimals") is not None:
            by_mint[mint] = by_mint.get(mint, Decimal(0)) + Decimal(account["raw_amount"]) / (Decimal(10) ** int(account["decimals"]))

    positions_by_ticker = {position["ticker"]: position for position in state["positions"]}
    for mint, (symbol, underlying) in KNOWN_ONDO.items():
        fills = [fill for fill in existing_fills if fill.get("mint") == mint]
        buys = sum((Decimal(fill.get("usdc_delta", "0")) * -1 for fill in fills if fill.get("side") == "BUY"), Decimal(0))
        sells = sum((Decimal(fill.get("usdc_delta", "0")) for fill in fills if fill.get("side") == "SELL"), Decimal(0))
        position = positions_by_ticker.get(underlying)
        if position is None and mint not in by_mint:
            continue
        if position is None:
            position = {"ticker": underlying, "reported_market_value_usd": None}
            state["positions"].append(position)
            positions_by_ticker[underlying] = position
        position["quantity"] = float(by_mint.get(mint, Decimal(0)))
        position["cost_basis_usd"] = float(buys - sells)
        position["cost_basis_status"] = "provisional_net_cash_flow" if sells else "on_chain_confirmed"
        position["thesis_status"] = "on_chain_partial_after_sale" if sells else "on_chain_confirmed"

    audit = {
        "schema_version": 2,
        "observed_at": datetime.now(UTC).isoformat(),
        "chain": "solana-mainnet",
        "source": "public_rpc_idempotent_ondo_refresh",
        "wallet_address": "[LOCAL_ONLY]",
        "platform_fee_usd": 0.0,
        "positions": [
            {
                "symbol": symbol,
                "underlying": underlying,
                "mint": mint,
                "current_amount": str(by_mint.get(mint, Decimal(0))),
                "gross_purchase_usd": str(sum((Decimal(fill.get("usdc_delta", "0")) * -1 for fill in existing_fills if fill.get("mint") == mint and fill.get("side") == "BUY"), Decimal(0))),
                "sale_proceeds_usd": str(sum((Decimal(fill.get("usdc_delta", "0")) for fill in existing_fills if fill.get("mint") == mint and fill.get("side") == "SELL"), Decimal(0))),
            }
            for mint, (symbol, underlying) in KNOWN_ONDO.items()
            if mint in by_mint
        ],
        "fills": existing_fills,
        "recent_activity": activities,
        "new_fill_count": len(existing_fills) - previous_fill_count,
        "rpc_errors": rpc_errors,
        "limitations": [
            "Unknown ONDO mints remain pending until official metadata mapping is added.",
            "USDC/token deltas are evidence; inner-instruction decoding may be needed for final economic price.",
            "Public RPC rate limits can leave individual transactions unavailable.",
        ],
    }
    _atomic_write(AUDIT, audit)
    _atomic_write(STATE, state)
    return {"new_fill_count": audit["new_fill_count"], "known_positions": len(audit["positions"]), "audit_path": str(AUDIT)}


def main() -> None:
    print(json.dumps(refresh(), indent=2))


if __name__ == "__main__":
    main()
