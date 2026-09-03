"""Bounded Dune/PumpApi semantic agreement checks."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import math
from typing import Any, Iterable, Mapping


def dune_to_canonical(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map the salvaged efficient-Dune row to the shared event vocabulary."""
    return {
        "mint": row.get("mint"),
        "event_time": row.get("event_time"),
        "slot": row.get("slot"),
        "tx_signature": row.get("transaction"),
        "wallet": row.get("wallet"),
        "side": row.get("side"),
        "token_amount": row.get("token_amount"),
        "quote_amount": row.get("quote_amount_sol"),
        "real_quote_reserves": row.get("real_quote_reserves_sol"),
        "real_token_reserves": row.get("real_token_reserves"),
        "virtual_quote_reserves": row.get("virtual_quote_reserves_sol"),
        "virtual_token_reserves": row.get("virtual_token_reserves"),
    }


def _close(left: Any, right: Any, *, relative: float = 1e-8, absolute: float = 1e-8) -> bool | None:
    if left is None or right is None:
        return None
    try:
        return math.isclose(float(left), float(right), rel_tol=relative, abs_tol=absolute)
    except (TypeError, ValueError):
        return False


def _dune_time_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace(" UTC", "+00:00")).timestamp() * 1000)


def compare_events(
    dune_rows: Iterable[Mapping[str, Any]],
    pumpapi_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare rows by transaction signature without treating either source as infallible."""
    indexed: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in pumpapi_rows:
        signature = row.get("tx_signature")
        if signature:
            indexed[str(signature)].append(row)

    counts: Counter[str] = Counter()
    timestamp_deltas: list[float] = []
    for raw_dune in dune_rows:
        dune = dune_to_canonical(raw_dune)
        signature = str(dune.get("tx_signature") or "")
        candidates = indexed.get(signature, [])
        counts["dune_rows"] += 1
        if not candidates:
            counts["missing_in_pumpapi"] += 1
            continue
        pump = candidates[0]
        counts["signature_matched"] += 1
        for field in ("mint", "wallet"):
            if dune.get(field) == pump.get(field):
                counts[f"{field}_exact"] += 1
        expected_side = "buy" if pump.get("event_type") == "CREATE" else pump.get("side")
        if dune.get("side") == expected_side:
            counts["side_semantic_exact"] += 1
        if pump.get("event_type") == "CREATE" and dune.get("side") == "buy":
            counts["known_create_as_buy"] += 1
        for field in ("token_amount", "quote_amount", "real_quote_reserves", "real_token_reserves"):
            result = _close(dune.get(field), pump.get(field))
            if result is None:
                counts[f"{field}_unknown"] += 1
            elif result:
                counts[f"{field}_within_tolerance"] += 1
            else:
                counts[f"{field}_mismatch"] += 1
        if dune.get("event_time") and pump.get("event_time_ms") is not None:
            timestamp_deltas.append(abs(_dune_time_ms(str(dune["event_time"])) - int(pump["event_time_ms"])))

    timestamp_deltas.sort()
    if timestamp_deltas:
        timestamp_summary = {
            "count": len(timestamp_deltas),
            "median_ms": timestamp_deltas[len(timestamp_deltas) // 2],
            "p95_ms": timestamp_deltas[int(0.95 * (len(timestamp_deltas) - 1))],
            "max_ms": max(timestamp_deltas),
            "within_1s_fraction": sum(delta <= 1000 for delta in timestamp_deltas) / len(timestamp_deltas),
        }
    else:
        timestamp_summary = {"count": 0}
    return {"counts": dict(counts), "timestamp_delta_ms": timestamp_summary}
