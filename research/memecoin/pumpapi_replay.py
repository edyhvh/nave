"""Independent, provider-neutral PumpApi replay normalization helpers.

The official archive is an input source only.  This module never signs,
trades, calls the Trade API, or loads a complete compressed hour into memory.
Callers feed it a binary/text line iterator and decide what compact rows to
retain.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from typing import Any, Iterable, Iterator, Mapping


UTC = timezone.utc
ACTION_ALIASES = {"createtoken": "create", "createpool": "create_pool", "pumpammcreate": "create_pool"}
SUPPORTED_ACTIONS = {"transfer", "create", "create_pool", "buy", "sell", "add", "remove", "migrate"}


def _first(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp_ms(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    if number < 10_000_000_000:
        number *= 1000
    return int(number)


def _iso_timestamp(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _action(raw: Mapping[str, Any]) -> tuple[str | None, bool]:
    value = _first(raw, "action", "txType")
    if value is None:
        return None, False
    normalized = str(value).strip().lower().replace("-", "_")
    normalized = ACTION_ALIASES.get(normalized, normalized)
    return normalized, "action" not in raw and "txType" in raw


def _economic_wallet(raw: Mapping[str, Any]) -> tuple[str | None, bool]:
    """Return the trade actor when the archive provides one unambiguously."""
    breakdown = raw.get("breakdown")
    if isinstance(breakdown, list):
        traders = [
            str(row.get("trader"))
            for row in breakdown
            if isinstance(row, Mapping) and row.get("trader") is not None
        ]
        unique = sorted(set(traders))
        if len(unique) == 1:
            return unique[0], False
        if len(unique) > 1:
            return None, True
    wallet = _first(raw, "user", "wallet", "trader", "buyer", "seller", "txSigner")
    return (str(wallet) if wallet is not None else None), False


def normalize_event(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one PumpApi replay event while retaining audit provenance."""
    action, legacy = _action(raw)
    event_time_ms = _timestamp_ms(_first(raw, "timestamp", "timestampMs"))
    received_ms = _timestamp_ms(raw.get("localTimestamp"))
    quality: list[str] = []
    if legacy:
        quality.append("LEGACY_SCHEMA")
    if action not in SUPPORTED_ACTIONS:
        quality.append("UNKNOWN_ACTION")
    mint = _first(raw, "mint", "tokenMint", "token_mint")
    signature = _first(raw, "signature", "txSignature", "transaction", "tx_id")
    wallet, ambiguous_wallet = _economic_wallet(raw)
    token_amount = _number(_first(raw, "tokenAmount", "tokens", "token_amount"))
    quote_amount = _number(_first(raw, "quoteAmount", "solAmount", "quote_amount", "sol_amount"))
    if not mint:
        quality.append("MISSING_MINT")
    if not signature:
        quality.append("MISSING_SIGNATURE")
    if action in {"buy", "sell"} and not wallet:
        quality.append("MISSING_WALLET")
    if ambiguous_wallet:
        quality.append("AMBIGUOUS_PARTICIPANT")
    if action in {"buy", "sell"} and quote_amount is None:
        quality.append("MISSING_QUOTE_AMOUNT")
    if event_time_ms is None:
        quality.append("MISSING_EVENT_TIME")
    if received_ms is not None and event_time_ms is not None and received_ms < event_time_ms:
        quality.append("RECEIVED_BEFORE_EVENT")
    side = action if action in {"buy", "sell"} else None
    return {
        "provider": "pumpapi",
        "venue": _first(raw, "pool", "dex"),
        "event_type": action.upper() if action else None,
        "mint": str(mint) if mint is not None else None,
        "event_time": _iso_timestamp(event_time_ms),
        "event_time_ms": event_time_ms,
        "provider_received_at": _iso_timestamp(received_ms),
        "provider_received_at_ms": received_ms,
        "available_at": _iso_timestamp(received_ms),
        "slot": _first(raw, "block", "slot", "blockNumber"),
        "tx_signature": str(signature) if signature is not None else None,
        "transaction_index": _first(raw, "transactionIndex", "txIndex", "tx_index"),
        "instruction_index": _first(raw, "instructionIndex", "instruction_index"),
        "wallet": str(wallet) if wallet is not None else None,
        "is_buy": side == "buy",
        "side": side,
        "token_amount": token_amount,
        "quote_amount": quote_amount,
        "quote_mint": _first(raw, "quoteMint", "quote_mint"),
        "price": _number(raw.get("price")),
        "virtual_token_reserves": _number(_first(raw, "virtualTokenReserves", "virtualTokensInPool")),
        "virtual_quote_reserves": _number(_first(raw, "virtualQuoteReserves", "virtualSolReserves", "virtualSolInPool")),
        "real_token_reserves": _number(_first(raw, "realTokenReserves", "tokensInPool")),
        "real_quote_reserves": _number(_first(raw, "realQuoteReserves", "quoteInPool", "solInPool")),
        "pool": _first(raw, "pool", "poolId"),
        "pool_id": _first(raw, "poolId"),
        "creator": raw.get("creator"),
        "protocol_state": {
            "mayhem": _first(raw, "mayhemMode", "isMayhemMode"),
            "token_program": _first(raw, "tokenProgram", "token_program"),
            "quote_mint": _first(raw, "quoteMint", "quote_mint"),
        },
        "raw_schema": "legacy" if legacy else "current",
        "quality_flags": sorted(set(quality)),
    }


def iter_normalized_events(lines: Iterable[bytes | str]) -> Iterator[dict[str, Any]]:
    """Parse JSONL incrementally; malformed lines are skipped by the caller."""
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        line = line.strip()
        if not line:
            continue
        yield normalize_event(json.loads(line))


def summarize_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Create compact counts for a normalized stream."""
    action_counts: Counter[str] = Counter()
    venue_counts: Counter[str] = Counter()
    mints: set[str] = set()
    wallets: set[str] = set()
    rows = 0
    quality_counts: Counter[str] = Counter()
    for event in events:
        rows += 1
        action_counts[str(event.get("event_type") or "UNKNOWN")] += 1
        venue_counts[str(event.get("venue") or "UNKNOWN")] += 1
        if event.get("mint"):
            mints.add(str(event["mint"]))
        if event.get("wallet"):
            wallets.add(str(event["wallet"]))
        quality_counts.update(event.get("quality_flags") or [])
    return {"rows": rows, "unique_mints": len(mints), "unique_wallets": len(wallets), "event_types": dict(action_counts), "venues": dict(venue_counts), "quality_flags": dict(quality_counts)}
