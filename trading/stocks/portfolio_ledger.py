"""Read-only ONDO ledger refresh for the human-gated portfolio.

This module never signs, submits, or executes transactions. It records
on-chain evidence and updates local state only after inventory discovery
succeeds.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from trading.crypto.chain_audit import SolanaRpcClient, summarize_solana_transaction

DEFAULT_STATE = Path(os.path.expanduser("~/.hermes/state/portfolio_manager/portfolio.json"))
DEFAULT_AUDIT = Path(os.path.expanduser("~/.hermes/state/portfolio_manager/ondo_solana_audit.json"))
DEFAULT_RPC_URLS = (
    "https://solana-rpc.publicnode.com,https://api.mainnet-beta.solana.com"
)
USDC_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}
USDC_DECIMALS = 6
# Officially validated local mapping. Unknown future ONDO mints stay pending.
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
_BASE58_RE = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,88}")
CONFIRMED = "confirmed_on_chain"
PENDING = "pending_review"
RESIDUAL_STATUS = "average_cost_residual"
CONFIRMED_STATUS = "on_chain_confirmed"
INCOMPLETE_STATUS = "incomplete_history"
ClientFactory = Callable[[str], Any]


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


def _as_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal(0)
    return Decimal(str(value))


def is_ondo_mint(mint: str | None) -> bool:
    if not mint:
        return False
    return mint in KNOWN_ONDO or mint.lower().endswith("ondo")


def lookup_ondo(mint: str | None) -> tuple[str, str]:
    if mint and mint in KNOWN_ONDO:
        return KNOWN_ONDO[mint]
    label = f"UNKNOWN:{mint}" if mint else "UNKNOWN"
    return label, "UNKNOWN"


def canonicalize_signature(signature: str | None) -> str | None:
    if not signature:
        return None
    try:
        from solders.signature import Signature

        return str(Signature.from_string(signature))
    except Exception:
        return None


def normalize_timestamp(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    return text[:19]


def economic_key(fill: dict[str, Any]) -> tuple[Any, ...] | None:
    mint = fill.get("mint")
    side = fill.get("side")
    quantity = fill.get("quantity")
    stamp = normalize_timestamp(fill.get("date_utc"))
    if not (mint and side and quantity is not None and stamp):
        return None
    return (mint, side, str(_as_decimal(quantity)), stamp)


def _signatures_can_fallback_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Match a legacy truncated signature only to its canonical prefix.

    Distinct valid signatures are separate transactions even when their economic
    fields happen to be identical in the same second.
    """
    left_raw = str(left.get("signature") or "")
    right_raw = str(right.get("signature") or "")
    left_canonical = canonicalize_signature(left_raw)
    right_canonical = canonicalize_signature(right_raw)
    if left_canonical and right_canonical:
        return left_canonical == right_canonical
    if left_canonical and right_raw:
        return len(right_raw) >= 80 and left_canonical.startswith(right_raw)
    if right_canonical and left_raw:
        return len(left_raw) >= 80 and right_canonical.startswith(left_raw)
    return False


def redact_rpc_error(message: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        value = match.group(0)
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        return f"ref:{digest}"

    return _BASE58_RE.sub(_replace, message)


def _signature_key(fill: dict[str, Any]) -> tuple[Any, Any, Any] | None:
    signature = canonicalize_signature(fill.get("signature")) or fill.get("signature")
    mint = fill.get("mint")
    side = fill.get("side")
    if not (signature and mint and side):
        return None
    return (signature, mint, side)


def _prefer_fill(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    incoming_confirmed = incoming.get("reconciliation_status") == CONFIRMED
    current_confirmed = current.get("reconciliation_status") == CONFIRMED
    if incoming_confirmed and not current_confirmed:
        merged = dict(incoming)
        merged.setdefault("symbol", current.get("symbol"))
        merged.setdefault("underlying", current.get("underlying"))
    incoming_sig = incoming.get("signature") or ""
    current_sig = merged.get("signature") or ""
    if canonicalize_signature(incoming_sig) and (
        not canonicalize_signature(current_sig) or len(incoming_sig) > len(current_sig)
    ):
        merged["signature"] = canonicalize_signature(incoming_sig)
    if incoming.get("mint"):
        merged["mint"] = incoming["mint"]
    if incoming.get("underlying") and incoming.get("underlying") != "UNKNOWN":
        merged["underlying"] = incoming["underlying"]
    incoming_symbol = incoming.get("symbol")
    if incoming_symbol and (
        not merged.get("symbol") or not str(incoming_symbol).startswith("UNKNOWN")
    ):
        merged["symbol"] = incoming_symbol
    return merged


def _enrich_fill(fill: dict[str, Any]) -> dict[str, Any]:
    row = dict(fill)
    mint = row.get("mint")
    if not mint:
        symbol = row.get("symbol")
        mint = next((key for key, (name, _) in KNOWN_ONDO.items() if name == symbol), None)
    if mint:
        row["mint"] = mint
        symbol, underlying = lookup_ondo(mint)
        row.setdefault("symbol", symbol)
        row.setdefault("underlying", underlying if underlying != "UNKNOWN" else row.get("underlying"))
        if row.get("underlying") in {None, "UNKNOWN"}:
            row["underlying"] = underlying
    canonical = canonicalize_signature(row.get("signature"))
    if canonical:
        row["signature"] = canonical
    return row


def normalize_existing_fills(fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedup by canonical signature and by mint/side/qty/timestamp."""
    normalized: list[dict[str, Any]] = []
    by_signature: dict[tuple[Any, Any, Any], int] = {}
    by_economic: dict[tuple[Any, ...], list[int]] = {}
    for fill in fills:
        row = _enrich_fill(fill)
        sig_key = _signature_key(row)
        econ = economic_key(row)
        index = by_signature.get(sig_key) if sig_key else None
        if index is None and econ is not None:
            index = next(
                (
                    candidate
                    for candidate in by_economic.get(econ, [])
                    if _signatures_can_fallback_match(normalized[candidate], row)
                ),
                None,
            )
        if index is not None:
            normalized[index] = _prefer_fill(normalized[index], row)
            sig_key = _signature_key(normalized[index])
            econ = economic_key(normalized[index])
            if sig_key:
                by_signature[sig_key] = index
            if econ:
                by_economic.setdefault(econ, [])
                if index not in by_economic[econ]:
                    by_economic[econ].append(index)
            continue
        index = len(normalized)
        normalized.append(row)
        if sig_key:
            by_signature[sig_key] = index
        if econ:
            by_economic.setdefault(econ, []).append(index)
    return normalized


def upsert_fill(fills: list[dict[str, Any]], fill: dict[str, Any]) -> bool:
    """Insert or upgrade a fill. Returns True when a new row is appended."""
    before = len(fills)
    fills[:] = normalize_existing_fills([*fills, fill])
    return len(fills) > before


def new_fill(
    activity: dict[str, Any],
    mint: str,
    ondo_delta: int,
    usdc_delta: int,
    *,
    apply_cash: bool,
) -> dict[str, Any]:
    symbol, underlying = lookup_ondo(mint)
    decimals = next(
        (
            int(change.get("decimals"))
            for change in activity.get("token_balance_changes", [])
            if change.get("mint") == mint and change.get("decimals") is not None
        ),
        9,
    )
    side = "BUY" if ondo_delta > 0 else "SELL"
    cash = usdc_delta if apply_cash else 0
    return {
        "symbol": symbol,
        "underlying": underlying,
        "mint": mint,
        "side": side,
        "date_utc": activity.get("block_time"),
        "quantity": _decimal_amount(abs(ondo_delta), decimals),
        "usdc_delta": str(Decimal(cash) / (Decimal(10) ** USDC_DECIMALS)),
        "network_fee_lamports": activity.get("fee_lamports"),
        "signature": activity.get("signature"),
        "reconciliation_status": CONFIRMED if apply_cash else PENDING,
        "evidence": (
            "token_balance_delta_plus_usdc_balance_delta"
            if apply_cash
            else "token_balance_delta_usdc_unattributed"
        ),
    }


def residual_average_cost(fills: list[dict[str, Any]]) -> dict[str, Any]:
    """Average-cost residual lots. Pending fills do not change cash or quantity."""
    quantity = Decimal(0)
    cost = Decimal(0)
    proceeds = Decimal(0)
    realized = Decimal(0)
    confirmed_fills = 0
    pending_fills = 0
    ordered = sorted(fills, key=lambda row: (normalize_timestamp(row.get("date_utc")) or "", row.get("signature") or ""))
    for fill in ordered:
        if fill.get("reconciliation_status") == PENDING:
            pending_fills += 1
            continue
        side = fill.get("side")
        fill_qty = _as_decimal(fill.get("quantity"))
        usdc = _as_decimal(fill.get("usdc_delta"))
        if side == "BUY":
            quantity += fill_qty
            cost += -usdc
            confirmed_fills += 1
        elif side == "SELL":
            sold = min(fill_qty, quantity) if quantity > 0 else Decimal(0)
            average = cost / quantity if quantity > 0 else Decimal(0)
            lot_cost = average * sold
            quantity -= sold
            cost -= lot_cost
            proceeds += usdc
            realized += usdc - lot_cost
            confirmed_fills += 1
    if pending_fills and not confirmed_fills:
        status = PENDING
    elif proceeds:
        status = RESIDUAL_STATUS
    else:
        status = CONFIRMED_STATUS
    return {
        "quantity": quantity,
        "cost_basis_usd": cost,
        "sale_proceeds_usd": proceeds,
        "realized_pnl_usd": realized,
        "cost_basis_status": status,
        "gross_purchase_usd": sum(
            (
                -_as_decimal(fill.get("usdc_delta"))
                for fill in fills
                if fill.get("side") == "BUY"
                and fill.get("reconciliation_status") != PENDING
            ),
            Decimal(0),
        ),
    }


def token_ui_amount(raw_amount: Any, decimals: Any) -> Decimal:
    return Decimal(str(raw_amount)) / (Decimal(10) ** int(decimals))


def _rpc_urls() -> list[str]:
    return [
        url.strip()
        for url in os.environ.get("SOLANA_RPC_URLS", DEFAULT_RPC_URLS).split(",")
        if url.strip()
    ]


def _collect_signatures(
    client: Any,
    pubkey: str,
    known_signatures: set[str],
    *,
    page_limit: int = 1_000,
    max_items: int = 5_000,
) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    before = None
    while len(rows) < max_items:
        requested = min(page_limit, max_items - len(rows))
        page = client.get_signatures(pubkey, limit=requested, before=before)
        if not page:
            break
        for row in page:
            signature = row.get("signature")
            canonical = canonicalize_signature(signature) if signature else None
            if signature in known_signatures or (canonical and canonical in known_signatures):
                return rows, False
            rows.append(row)
        if len(page) < requested:
            break
        before = page[-1].get("signature")
        if not before:
            break
    return rows[:max_items], len(rows) >= max_items


def _discover_token_accounts(
    rpc_urls: list[str],
    wallet: str,
    *,
    client_factory: ClientFactory,
    require_accounts: bool,
    allow_empty: bool,
) -> tuple[Any, list[dict[str, Any]], list[str]]:
    rpc_errors: list[str] = []
    empty_responses: list[Any] = []
    for rpc_url in rpc_urls:
        try:
            candidate = client_factory(rpc_url)
            token_accounts = candidate.get_token_accounts(wallet)
        except Exception as exc:
            rpc_errors.append(redact_rpc_error(f"{rpc_url}: {exc}"))
            continue
        if not token_accounts and require_accounts and not allow_empty:
            rpc_errors.append(redact_rpc_error(f"{rpc_url}: empty token account set"))
            empty_responses.append(candidate)
            if len(empty_responses) >= 2:
                return candidate, [], rpc_errors
            continue
        return candidate, token_accounts, rpc_errors
    raise RuntimeError("all Solana RPC endpoints failed: " + " | ".join(rpc_errors))


def refresh(
    *,
    state_path: Path = DEFAULT_STATE,
    audit_path: Path = DEFAULT_AUDIT,
    rpc_urls: list[str] | None = None,
    client_factory: ClientFactory | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    previous = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
    wallet = state["wallets"]["solana"]["address"]
    existing_fills = normalize_existing_fills(list(previous.get("fills", [])))
    previous_fill_count = len(existing_fills)
    positions = list(state.get("positions") or [])
    require_accounts = bool(positions)
    factory = client_factory or SolanaRpcClient
    client, token_accounts, rpc_errors = _discover_token_accounts(
        rpc_urls or _rpc_urls(),
        wallet,
        client_factory=factory,
        require_accounts=require_accounts,
        allow_empty=allow_empty,
    )
    if require_accounts and not token_accounts:
        raise RuntimeError(
            "all Solana RPC endpoints returned an empty token account set; "
            "refusing to rewrite existing positions"
        )

    ondo_accounts = [account for account in token_accounts if is_ondo_mint(account.get("mint"))]
    known_signatures = {
        key
        for fill in existing_fills
        for key in (fill.get("signature"), canonicalize_signature(fill.get("signature")))
        if key
    }
    activities: list[dict[str, Any]] = []
    signatures: dict[str, dict[str, Any]] = {}
    history_complete = True
    history_addresses = [wallet] + [
        account.get("pubkey") for account in ondo_accounts if account.get("pubkey")
    ]
    for pubkey in dict.fromkeys(history_addresses):
        if not pubkey:
            continue
        try:
            account_signatures, truncated = _collect_signatures(client, pubkey, known_signatures)
            if truncated:
                history_complete = False
                rpc_errors.append(f"signatures:{pubkey}: history truncated at max_items")
        except Exception as exc:
            history_complete = False
            rpc_errors.append(redact_rpc_error(f"signatures:{pubkey}: {exc}"))
            continue
        for row in account_signatures:
            signature = row.get("signature")
            if signature:
                signatures[signature] = row

    for signature in signatures:
        try:
            transaction = client.get_transaction(signature)
            if transaction is None:
                history_complete = False
                activities.append({"signature": signature, "status": "unavailable"})
                continue
            activity = summarize_solana_transaction(transaction, wallet, signature=signature)
            activities.append(activity)
            if activity.get("err"):
                continue
            changes = activity.get("token_balance_changes", [])
            ondo_changes = [change for change in changes if is_ondo_mint(change.get("mint"))]
            usdc_delta = sum(
                int(change.get("delta_raw_amount", 0))
                for change in changes
                if change.get("mint") in USDC_MINTS
            )
            for change in ondo_changes:
                ondo_delta = int(change.get("delta_raw_amount", 0))
                if not ondo_delta:
                    continue
                apply_cash = len(ondo_changes) == 1 and (
                    (ondo_delta > 0 and usdc_delta < 0)
                    or (ondo_delta < 0 and usdc_delta > 0)
                )
                fill = new_fill(
                    activity,
                    change["mint"],
                    ondo_delta,
                    usdc_delta,
                    apply_cash=apply_cash,
                )
                upsert_fill(existing_fills, fill)
        except Exception as exc:
            history_complete = False
            activities.append(
                {
                    "signature": signature,
                    "status": "unavailable",
                    "error": redact_rpc_error(str(exc)),
                }
            )

    by_mint: dict[str, Decimal] = {}
    for account in ondo_accounts:
        mint = account.get("mint")
        if mint and account.get("raw_amount") is not None and account.get("decimals") is not None:
            by_mint[mint] = by_mint.get(mint, Decimal(0)) + token_ui_amount(
                account["raw_amount"], account["decimals"]
            )

    fills_by_mint: dict[str, list[dict[str, Any]]] = {}
    for fill in existing_fills:
        mint = fill.get("mint")
        if mint:
            fills_by_mint.setdefault(mint, []).append(fill)

    audit_positions = []
    tracked_mints = set(KNOWN_ONDO) | set(by_mint) | set(fills_by_mint)
    for mint in sorted(tracked_mints):
        symbol, underlying = lookup_ondo(mint)
        basis = residual_average_cost(fills_by_mint.get(mint, []))
        if mint not in by_mint and mint not in fills_by_mint:
            continue
        audit_positions.append(
            {
                "symbol": symbol,
                "underlying": underlying,
                "mint": mint,
                "current_amount": str(by_mint.get(mint, Decimal(0))),
                "gross_purchase_usd": str(basis["gross_purchase_usd"]),
                "sale_proceeds_usd": str(basis["sale_proceeds_usd"]),
                "realized_pnl_usd": str(basis["realized_pnl_usd"]),
                "cost_basis_usd": str(basis["cost_basis_usd"]),
                "cost_basis_status": (
                    basis["cost_basis_status"] if history_complete else INCOMPLETE_STATUS
                ),
            }
        )

    positions_by_ticker = {position["ticker"]: position for position in positions}
    for mint, (_symbol, underlying) in KNOWN_ONDO.items():
        position = positions_by_ticker.get(underlying)
        if position is None:
            continue
        amount = by_mint.get(mint, Decimal(0))
        basis = residual_average_cost(fills_by_mint.get(mint, []))
        position["quantity"] = float(amount)
        position["cost_basis_usd"] = float(basis["cost_basis_usd"])
        position["cost_basis_status"] = (
            basis["cost_basis_status"] if history_complete else INCOMPLETE_STATUS
        )
        position["sale_proceeds_usd"] = float(basis["sale_proceeds_usd"])
        position["realized_pnl_usd"] = float(basis["realized_pnl_usd"])

    audit = {
        "schema_version": 3,
        "observed_at": datetime.now(UTC).isoformat(),
        "chain": "solana-mainnet",
        "source": "public_rpc_idempotent_ondo_refresh",
        "wallet_address": "[LOCAL_ONLY]",
        "platform_fee_usd": 0.0,
        "positions": audit_positions,
        "fills": existing_fills,
        "recent_activity": activities,
        "new_fill_count": len(existing_fills) - previous_fill_count,
        "rpc_errors": rpc_errors,
        "history_complete": history_complete,
        "state_updated": True,
        "limitations": [
            "Unknown ONDO mints remain pending_review until official metadata mapping is added.",
            "USDC is attributed only when exactly one ONDO mint moved in the transaction.",
            "Remaining cost_basis_usd is average-cost of residual lots, not net cash flow.",
            "Public RPC rate limits can leave individual transactions unavailable.",
        ],
    }
    _atomic_write(audit_path, audit)
    state["updated_at"] = audit["observed_at"]
    state["ledger_history_complete"] = history_complete
    _atomic_write(state_path, state)
    return {
        "new_fill_count": audit["new_fill_count"],
        "known_positions": len([row for row in audit_positions if row["underlying"] != "UNKNOWN"]),
        "pending_unknown_mints": len([row for row in audit_positions if row["underlying"] == "UNKNOWN"]),
        "history_complete": history_complete,
        "audit_path": str(audit_path),
        "state_path": str(state_path),
    }


def main() -> None:
    import json as json_lib

    print(json_lib.dumps(refresh(), indent=2))
