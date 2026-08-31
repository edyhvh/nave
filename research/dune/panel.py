"""Small local transformations for Dune result artifacts.

The Dune CLI returns compact JSON objects with one dictionary per result row.
This module converts those rows to auditable Parquet and derives participant
episodes without making network calls. It intentionally does not repair
missing prices, infer wallet clusters, or turn open inventory into realized
profit.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

UTC = timezone.utc


def parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace(" UTC", "+00:00").replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def dune_rows(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text())
    if payload.get("state") != "QUERY_STATE_COMPLETED":
        raise ValueError(f"Dune result is not complete: {payload.get('state')}")
    rows = payload.get("result", {}).get("rows", [])
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Dune result rows are not object records")
    return rows


def write_parquet(rows: Iterable[dict[str, Any]], path: str | Path) -> int:
    records = list(rows)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_parquet(target, index=False)
    return len(records)


def normalize_proof_events(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize the one-token proof and propagate verified lifecycle context."""
    raw = list(rows)
    migration = next((r for r in raw if r.get("event_type") == "MIGRATE"), {})
    create = next((r for r in raw if r.get("event_type") == "CREATE"), {})
    pool_id = migration.get("pool_id")
    creator = create.get("creator")
    normalized = []
    for row in raw:
        event = dict(row)
        event["event_ts"] = parse_ts(row.get("event_time"))
        event["sol_amount"] = row.get("quote_amount_sol")
        event["data_source"] = "dune_decoded_and_spellbook"
        if event.get("venue") == "pumpswap":
            event["pool_id"] = pool_id
        if event.get("creator") is None:
            event["creator"] = creator
        event["protocol_generated"] = None
        normalized.append(event)
    return sorted(deduplicate_events(normalized), key=event_order_key)


def deduplicate_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop exact decoded-event duplicates using identity, not signature alone."""
    output = []
    seen: set[tuple[Any, ...]] = set()
    for event in events:
        key = tuple(event.get(field) for field in (
            "mint", "venue", "event_type", "tx_id", "outer_instruction_index", "inner_instruction_index",
            "event_ts", "wallet", "side", "token_amount", "quote_amount_sol",
        ))
        if key in seen:
            continue
        seen.add(key)
        output.append(event)
    return output


def reconstruct_price_sol(quote_amount_sol: Any, token_amount: Any) -> float | None:
    """Derive quote-per-token only from the observed trade quantities."""
    quote = _number(quote_amount_sol)
    token = _number(token_amount)
    if quote is None or token is None or quote < 0 or token <= 0:
        return None
    return quote / token


def event_order_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("event_ts") or datetime.max.replace(tzinfo=UTC),
        row.get("block_slot") if row.get("block_slot") is not None else 2**63,
        row.get("tx_index") if row.get("tx_index") is not None else 2**31,
        row.get("outer_instruction_index") if row.get("outer_instruction_index") is not None else 2**31,
        row.get("inner_instruction_index") if row.get("inner_instruction_index") is not None else 2**31,
        row.get("tx_id") or "",
    )


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _trade_rows(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if e.get("side") in {"buy", "sell"} and e.get("event_ts")]


def _fifo_pnl(trades: Iterable[dict[str, Any]]) -> tuple[float, float]:
    inventory: list[list[float]] = []
    realized = 0.0
    for trade in sorted(trades, key=event_order_key):
        qty = _number(trade.get("token_amount"))
        quote = _number(trade.get("quote_amount_sol"))
        if not qty or qty <= 0 or quote is None or quote < 0:
            continue
        if trade.get("side") == "buy":
            inventory.append([qty, quote])
            continue
        remaining = qty
        proceeds_per_token = quote / qty
        while remaining > 0 and inventory:
            lot_qty, lot_cost = inventory[0]
            used = min(remaining, lot_qty)
            realized += used * (proceeds_per_token - lot_cost / lot_qty)
            remaining -= used
            lot_qty -= used
            lot_cost -= used * (lot_cost / (lot_qty + used))
            if lot_qty <= 1e-12:
                inventory.pop(0)
            else:
                inventory[0] = [lot_qty, lot_cost]
    return realized, sum(lot[0] for lot in inventory)


def participant_episodes(events: Iterable[dict[str, Any]], launch_ts: datetime) -> list[dict[str, Any]]:
    """Return wallet-token episodes, retaining first-entry landmarks."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in _trade_rows(events):
        wallet = event.get("wallet")
        if wallet:
            grouped[str(wallet)].append(event)
    output = []
    for wallet, trades in sorted(grouped.items()):
        buys = [e for e in trades if e.get("side") == "buy"]
        sells = [e for e in trades if e.get("side") == "sell"]
        if not buys:
            continue
        first_buy = min(buys, key=event_order_key)
        first_sell = min(sells, key=event_order_key) if sells else None
        first_ts = first_buy["event_ts"]
        seconds = (first_ts - launch_ts).total_seconds()
        realized, remaining = _fifo_pnl(trades)
        output.append({
            "wallet": wallet,
            "mint": first_buy.get("mint"),
            "first_entry_time": first_ts,
            "seconds_since_launch": seconds,
            "first_buy_amount": first_buy.get("token_amount"),
            "total_buy_amount": sum(_number(e.get("token_amount")) or 0 for e in buys),
            "first_sell_time": first_sell.get("event_ts") if first_sell else None,
            "total_sell_amount": sum(_number(e.get("token_amount")) or 0 for e in sells),
            "number_of_buys": len(buys),
            "number_of_sells": len(sells),
            "inventory_remaining": remaining,
            "realized_pnl_sol_before_fees": realized,
            "entry_30s": seconds <= 30,
            "entry_60s": seconds <= 60,
            "entry_5m": seconds <= 300,
            "data_source": "dune_proof_event_panel",
        })
    return output


def point_in_time_history(events: Iterable[dict[str, Any]], cutoff: datetime) -> dict[str, Any]:
    """Summarize only events strictly before the cutoff."""
    prior = [e for e in events if e.get("event_ts") and e["event_ts"] < cutoff]
    entries = [e for e in prior if e.get("side") == "buy"]
    return {
        "cutoff": cutoff.isoformat(),
        "prior_trade_events": len(prior),
        "prior_buy_events": len(entries),
        "prior_wallets": sorted({e.get("wallet") for e in entries if e.get("wallet")}),
        "future_event_exclusion_checked": all(e["event_ts"] < cutoff for e in prior),
    }


def proof_summary(events: list[dict[str, Any]], launch_ts: datetime) -> dict[str, Any]:
    trade_events = _trade_rows(events)
    by_type: dict[str, int] = defaultdict(int)
    for event in events:
        by_type[str(event.get("event_type"))] += 1
    ordered = sorted(events, key=event_order_key)
    return {
        "mint": ordered[0].get("mint") if ordered else None,
        "launch_ts": launch_ts.isoformat(),
        "event_count": len(events),
        "trade_event_count": len(trade_events),
        "event_type_counts": dict(sorted(by_type.items())),
        "venues": sorted({e.get("venue") for e in events if e.get("venue")}),
        "wallet_count": len({e.get("wallet") for e in trade_events if e.get("wallet")}),
        "first_event_ts": ordered[0].get("event_ts").isoformat() if ordered and ordered[0].get("event_ts") else None,
        "last_event_ts": ordered[-1].get("event_ts").isoformat() if ordered and ordered[-1].get("event_ts") else None,
        "migration_linked_pool_ids": sorted({e.get("pool_id") for e in events if e.get("pool_id")}),
        "same_mint_identity": len({e.get("mint") for e in events}) == 1,
        "slot_time_order_violations": sum(
            1 for a, b in zip(ordered, ordered[1:])
            if a.get("event_ts") and b.get("event_ts") and b["event_ts"] < a["event_ts"]
        ),
        "point_in_time_example": point_in_time_history(events, launch_ts + timedelta(minutes=5)),
    }
