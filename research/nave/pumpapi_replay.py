"""Minimal normalized PumpApi replay event contract for local research."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping


UTC = timezone.utc
ALIASES = {"createtoken": "create", "createpool": "create_pool", "pumpammcreate": "create_pool"}
SUPPORTED = {"transfer", "create", "create_pool", "buy", "sell", "add", "remove", "migrate"}


def _first(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if raw.get(key) is not None:
            return raw[key]
    return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _timestamp_ms(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    if number < 10_000_000_000:
        number *= 1000
    return int(number)


def _iso(timestamp_ms: int | None) -> str | None:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z") if timestamp_ms is not None else None


def _wallet(raw: Mapping[str, Any]) -> tuple[str | None, bool]:
    breakdown = raw.get("breakdown")
    if isinstance(breakdown, list):
        wallets = sorted({str(row["trader"]) for row in breakdown if isinstance(row, Mapping) and row.get("trader") is not None})
        if len(wallets) == 1:
            return wallets[0], False
        if len(wallets) > 1:
            return None, True
    value = _first(raw, "user", "wallet", "trader", "buyer", "seller", "txSigner")
    return (str(value) if value is not None else None), False


def normalize_event(raw: Mapping[str, Any]) -> dict[str, Any]:
    action_value = _first(raw, "action", "txType")
    action = str(action_value).strip().lower().replace("-", "_") if action_value is not None else None
    action = ALIASES.get(action, action)
    event_time_ms = _timestamp_ms(_first(raw, "timestamp", "timestampMs"))
    received_ms = _timestamp_ms(raw.get("localTimestamp"))
    mint = _first(raw, "mint", "tokenMint", "token_mint")
    wallet, ambiguous = _wallet(raw)
    flags: list[str] = []
    if action not in SUPPORTED:
        flags.append("UNKNOWN_ACTION")
    if not mint:
        flags.append("MISSING_MINT")
    if not _first(raw, "signature", "txSignature", "transaction", "tx_id"):
        flags.append("MISSING_SIGNATURE")
    if action in {"buy", "sell"} and not wallet:
        flags.append("MISSING_WALLET")
    if ambiguous:
        flags.append("AMBIGUOUS_PARTICIPANT")
    if action in {"buy", "sell"} and _number(_first(raw, "quoteAmount", "solAmount", "quote_amount", "sol_amount")) is None:
        flags.append("MISSING_QUOTE_AMOUNT")
    if event_time_ms is None:
        flags.append("MISSING_EVENT_TIME")
    return {
        "provider": "pumpapi", "venue": _first(raw, "pool", "dex"),
        "event_type": action.upper() if action else None, "mint": str(mint) if mint is not None else None,
        "event_time": _iso(event_time_ms), "event_time_ms": event_time_ms,
        "provider_received_at": _iso(received_ms), "provider_received_at_ms": received_ms,
        "available_at": _iso(received_ms), "slot": _first(raw, "block", "slot", "blockNumber"),
        "tx_signature": str(_first(raw, "signature", "txSignature", "transaction", "tx_id")) if _first(raw, "signature", "txSignature", "transaction", "tx_id") is not None else None,
        "transaction_index": _first(raw, "transactionIndex", "txIndex", "tx_index"),
        "instruction_index": _first(raw, "instructionIndex", "instruction_index"),
        "wallet": wallet, "is_buy": action == "buy", "side": action if action in {"buy", "sell"} else None,
        "token_amount": _number(_first(raw, "tokenAmount", "tokens", "token_amount")),
        "quote_amount": _number(_first(raw, "quoteAmount", "solAmount", "quote_amount", "sol_amount")),
        "quote_mint": _first(raw, "quoteMint", "quote_mint"), "price": _number(raw.get("price")),
        "virtual_token_reserves": _number(_first(raw, "virtualTokenReserves", "virtualTokensInPool")),
        "virtual_quote_reserves": _number(_first(raw, "virtualQuoteReserves", "virtualSolReserves", "virtualSolInPool")),
        "real_token_reserves": _number(_first(raw, "realTokenReserves", "tokensInPool")),
        "real_quote_reserves": _number(_first(raw, "realQuoteReserves", "quoteInPool", "solInPool")),
        "pool_id": _first(raw, "poolId"), "creator": raw.get("creator"),
        "protocol_state_json": json_state({"mayhem": _first(raw, "mayhemMode", "isMayhemMode"), "token_program": _first(raw, "tokenProgram", "token_program"), "quote_mint": _first(raw, "quoteMint", "quote_mint")}),
        "raw_schema": "legacy" if "action" not in raw and "txType" in raw else "current",
        "quality_flags_json": json_state(sorted(set(flags))),
    }


def json_state(value: Any) -> str:
    import json
    return json.dumps(value, sort_keys=True)
