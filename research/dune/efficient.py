"""Credit-efficient, chain-neutral helpers for the NAVE historical panel.

This module is intentionally local-first.  Dune SQL templates provide source
rows; all window construction, outcomes, participant episodes, and FIFO
accounting happen here so changing a research threshold never re-scans Dune.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

UTC = timezone.utc


CANONICAL_FIELDS = (
    "mint", "launch_time", "creator", "slot", "transaction", "quote_mint",
    "supply", "mayhem", "cashback", "token_program",
)


def deterministic_mint_sample(
    launches: Iterable[Mapping[str, Any]], size: int, *, seed: str = "nave-2026-08-27-v2"
) -> list[dict[str, Any]]:
    """Return a reproducible outcome-independent mint sample.

    SHA-256 ordering is stable across processes and does not depend on launch
    outcomes, row order, or Python's randomized hash seed.
    """
    if size < 0:
        raise ValueError("size must be non-negative")
    rows = []
    seen: set[str] = set()
    for row in launches:
        mint = row.get("mint")
        if not mint or str(mint) in seen:
            continue
        mint = str(mint)
        seen.add(mint)
        digest = hashlib.sha256(f"{seed}:{mint}".encode()).hexdigest()
        rows.append((digest, mint, dict(row)))
    rows.sort(key=lambda item: (item[0], item[1]))
    return [row for _, _, row in rows[:size]]


def sql_string_list(values: Iterable[Any]) -> str:
    """Render a validated string literal list for a bounded Dune query."""
    escaped = []
    for value in values:
        text = str(value)
        if "'" in text or "\n" in text or "\r" in text:
            raise ValueError("unsafe SQL list value")
        escaped.append("'" + text + "'")
    return ", ".join(escaped) or "NULL"


def first_hour_query(mints: Sequence[str], *, start: str, end: str) -> str:
    """Render one-pass Pump.fun event extraction for a bounded mint set."""
    return f"""WITH selected_mints(mint) AS (VALUES {', '.join(f'({sql_string_list([mint])})' for mint in mints)})
,
launches AS (
    SELECT c.mint, MIN(c.evt_block_time) AS launch_time
    FROM pumpdotfun_solana.pump_evt_createevent c
    JOIN selected_mints s ON s.mint = c.mint
    WHERE c.evt_block_time >= TIMESTAMP '{start} UTC'
      AND c.evt_block_time < TIMESTAMP '{end} UTC'
    GROUP BY c.mint
)
SELECT
    t.mint,
    t.evt_block_time AS event_time,
    t.evt_block_slot AS slot,
    t.evt_tx_id AS transaction,
    t.evt_tx_index AS tx_index,
    t.evt_outer_instruction_index AS outer_instruction_index,
    t.evt_inner_instruction_index AS inner_instruction_index,
    CAST(t.user AS varchar) AS wallet,
    CASE WHEN t.is_buy THEN 'buy' ELSE 'sell' END AS side,
    CAST(t.token_amount AS double) / 1000000 AS token_amount,
    CAST(t.sol_amount AS double) / 1000000000 AS quote_amount_sol,
    CAST(t.fee AS double) / 1000000000 AS fee_sol,
    CAST(t.virtual_sol_reserves AS double) / 1000000000 AS virtual_quote_reserves_sol,
    CAST(t.virtual_token_reserves AS double) / 1000000 AS virtual_token_reserves,
    CAST(t.real_sol_reserves AS double) / 1000000000 AS real_quote_reserves_sol,
    CAST(t.real_token_reserves AS double) / 1000000 AS real_token_reserves
FROM pumpdotfun_solana.pump_evt_tradeevent t
JOIN selected_mints s ON s.mint = t.mint
JOIN launches l ON l.mint = t.mint
WHERE t.evt_block_time >= TIMESTAMP '{start} UTC'
  AND t.evt_block_time < TIMESTAMP '{end} UTC'
  AND t.evt_block_time >= l.launch_time
  AND t.evt_block_time < date_add('hour', 1, l.launch_time)
ORDER BY t.mint, t.evt_block_time, t.evt_block_slot, t.evt_tx_index,
         t.evt_outer_instruction_index, t.evt_inner_instruction_index
"""


def first_hour_aggregate_query(mints: Sequence[str], *, start: str, end: str) -> str:
    """Render compact one-row-per-mint burst features for a bounded sample."""
    base = first_hour_query(mints, start=start, end=end)
    base = base[:base.rfind("ORDER BY")].rstrip()
    return f"""WITH events AS (
{base}
)
SELECT mint,
       COUNT(*) AS trade_count,
       COUNT_IF(side = 'buy') AS buy_count,
       COUNT_IF(side = 'sell') AS sell_count,
       COUNT(DISTINCT CASE WHEN side = 'buy' THEN wallet END) AS unique_buyers,
       SUM(CASE WHEN side = 'buy' THEN quote_amount_sol ELSE 0 END) AS buy_volume_sol,
       SUM(CASE WHEN side = 'sell' THEN quote_amount_sol ELSE 0 END) AS sell_volume_sol,
       MAX(real_quote_reserves_sol) AS max_real_quote_reserves_sol,
       MAX_BY(virtual_quote_reserves_sol, event_time) AS last_virtual_quote_reserves_sol,
       MAX_BY(real_quote_reserves_sol, event_time) AS last_real_quote_reserves_sol,
       MIN_BY(event_time, event_time) AS first_trade_time,
       MAX_BY(event_time, event_time) AS last_trade_time
FROM events
GROUP BY mint
"""


def token_panel_query(
    mints: Sequence[str], *, start: str, end: str, observation_end: str
) -> str:
    """Render one compact Pump.fun-only row per mint with burst and marks."""
    values = ", ".join(f"({sql_string_list([mint])})" for mint in mints)
    return f"""WITH selected_mints(mint) AS (VALUES {values}),
sol_marks AS (
    SELECT minute, MAX(price) AS sol_usd
    FROM prices.usd
    WHERE minute >= TIMESTAMP '{start} UTC'
      AND minute < TIMESTAMP '{observation_end} UTC'
      AND blockchain = 'solana' AND symbol = 'SOL'
    GROUP BY minute
), launches AS (
    SELECT c.mint, MIN(c.evt_block_time) AS launch_time
    FROM pumpdotfun_solana.pump_evt_createevent c
    JOIN selected_mints s ON s.mint = c.mint
    WHERE c.evt_block_time >= TIMESTAMP '{start} UTC'
      AND c.evt_block_time < TIMESTAMP '{end} UTC'
    GROUP BY c.mint
), events AS (
    SELECT t.mint, t.evt_block_time AS event_time,
           date_diff('second', l.launch_time, t.evt_block_time) AS rel_sec,
           CASE WHEN t.is_buy THEN 'buy' ELSE 'sell' END AS side,
           CAST(t.user AS varchar) AS wallet,
           (CAST(t.sol_amount AS double) / NULLIF(CAST(t.token_amount AS double), 0)) / 1000 * sm.sol_usd AS price_usd,
           CAST(t.sol_amount AS double) / 1000000000 AS quote_amount_sol,
           CAST(t.virtual_sol_reserves AS double) / 1000000000 AS virtual_quote_reserves_sol,
           CAST(t.real_sol_reserves AS double) / 1000000000 AS real_quote_reserves_sol
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN launches l ON l.mint = t.mint
    LEFT JOIN sol_marks sm ON sm.minute = date_trunc('minute', t.evt_block_time)
    WHERE t.evt_block_time >= TIMESTAMP '{start} UTC'
      AND t.evt_block_time < TIMESTAMP '{observation_end} UTC'
      AND t.evt_block_time >= l.launch_time
      AND t.evt_block_time < date_add('hour', 72, l.launch_time)
)
SELECT l.mint,
       COUNT(e.event_time) FILTER (WHERE e.rel_sec BETWEEN 0 AND 3600) AS trade_count_60m,
       COUNT_IF(e.side = 'buy' AND e.rel_sec BETWEEN 0 AND 3600) AS buy_count_60m,
       COUNT_IF(e.side = 'sell' AND e.rel_sec BETWEEN 0 AND 3600) AS sell_count_60m,
       COUNT(DISTINCT e.wallet) FILTER (WHERE e.side = 'buy' AND e.rel_sec BETWEEN 0 AND 3600) AS unique_buyers_60m,
       MAX(e.price_usd) FILTER (WHERE e.rel_sec BETWEEN 0 AND 3600) AS high_price_60m_usd,
       MIN_BY(e.price_usd, e.rel_sec) FILTER (WHERE e.price_usd IS NOT NULL AND e.rel_sec BETWEEN 0 AND 3600) AS open_price_60m_usd,
       MAX_BY(e.price_usd, e.rel_sec) FILTER (WHERE e.price_usd IS NOT NULL AND e.rel_sec BETWEEN 0 AND 3600) AS close_price_60m_usd,
       MIN_BY(e.price_usd, ABS(e.rel_sec - 14400)) FILTER (WHERE e.price_usd IS NOT NULL AND ABS(e.rel_sec - 14400) <= 300) AS mark_price_4h_usd,
       MIN_BY(e.price_usd, ABS(e.rel_sec - 86400)) FILTER (WHERE e.price_usd IS NOT NULL AND ABS(e.rel_sec - 86400) <= 300) AS mark_price_24h_usd,
       MIN_BY(e.price_usd, ABS(e.rel_sec - 172800)) FILTER (WHERE e.price_usd IS NOT NULL AND ABS(e.rel_sec - 172800) <= 300) AS mark_price_48h_usd,
       MIN_BY(e.price_usd, ABS(e.rel_sec - 259200)) FILTER (WHERE e.price_usd IS NOT NULL AND ABS(e.rel_sec - 259200) <= 300) AS mark_price_72h_usd,
       MAX(e.real_quote_reserves_sol) FILTER (WHERE e.rel_sec BETWEEN 0 AND 3600) AS max_real_quote_reserves_60m_sol,
       MAX(e.event_time) AS last_observed_event_time
FROM launches l
LEFT JOIN events e ON e.mint = l.mint
GROUP BY l.mint
"""


def migration_query(mints: Sequence[str], *, start: str, end: str) -> str:
    """Render a compact migration map restricted to selected launches."""
    values = ", ".join(f"({sql_string_list([mint])})" for mint in mints)
    return f"""WITH selected_mints(mint) AS (VALUES {values})
SELECT m.account_mint AS mint,
       MIN(m.call_block_time) AS migration_time,
       MIN_BY(m.account_pool, m.call_block_time) AS pool_id,
       MIN_BY(m.account_pump_amm, m.call_block_time) AS pump_amm
FROM pumpdotfun_solana.pump_call_migrate m
JOIN selected_mints s ON s.mint = m.account_mint
WHERE m.call_block_time >= TIMESTAMP '{start} UTC'
  AND m.call_block_time < TIMESTAMP '{end} UTC'
GROUP BY m.account_mint
"""


def pumpswap_query(mints: Sequence[str], *, start: str, end: str) -> str:
    """Render post-migration PumpSwap trades only for verified migrated mints."""
    values = ", ".join(f"({sql_string_list([mint])})" for mint in mints)
    return f"""WITH migrated_mints(mint) AS (VALUES {values})
SELECT CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
            THEN d.token_sold_mint_address ELSE d.token_bought_mint_address END AS mint,
       d.block_time AS event_time, d.block_slot AS slot, d.tx_id AS transaction,
       d.tx_index, d.outer_instruction_index, d.inner_instruction_index,
       d.trader_id AS wallet,
       CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
            THEN 'sell' ELSE 'buy' END AS side,
       CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
            THEN d.token_sold_amount ELSE d.token_bought_amount END AS token_amount,
       CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
            THEN d.token_bought_amount ELSE d.token_sold_amount END AS quote_amount_sol,
       d.amount_usd, d.fee_usd, d.fee_tier,
       d.token_bought_vault, d.token_sold_vault
FROM dex_solana.trades d
JOIN migrated_mints m ON m.mint = CASE
    WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
    THEN d.token_sold_mint_address ELSE d.token_bought_mint_address END
WHERE d.blockchain = 'solana'
  AND d.block_time >= TIMESTAMP '{start} UTC'
  AND d.block_time < TIMESTAMP '{end} UTC'
  AND d.project = 'pumpswap'
"""


def window_aggregate(events: Iterable[Mapping[str, Any]], windows: Sequence[int]) -> list[dict[str, Any]]:
    """Aggregate each event once into cumulative launch-relative windows.

    The output is one row per (mint, window), not one row per event-window join.
    Event timestamps must be UTC-aware; rows outside a window are ignored.
    """
    ordered = sorted((dict(e) for e in events), key=event_order_key)
    by_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in ordered:
        if event.get("mint") and event.get("event_ts"):
            by_mint[str(event["mint"])].append(event)
    output: list[dict[str, Any]] = []
    for mint, rows in sorted(by_mint.items()):
        launch_ts = next((e.get("launch_ts") for e in rows if e.get("launch_ts")), None)
        if not launch_ts:
            launch_ts = min(e["event_ts"] for e in rows)
        relative = [
            (e, (e["event_ts"] - launch_ts).total_seconds())
            for e in rows
        ]
        for seconds in sorted(set(windows)):
            bounded = [e for e, rel in relative if 0 <= rel <= seconds]
            buys = [e for e in bounded if e.get("side") == "buy"]
            sells = [e for e in bounded if e.get("side") == "sell"]
            prices = [number(e.get("price_usd")) for e in bounded]
            prices = [p for p in prices if p is not None]
            quote = [number(e.get("quote_amount_sol")) or 0 for e in bounded]
            output.append({
                "mint": mint,
                "window_end_seconds": seconds,
                "trade_count": len(bounded),
                "buy_count": len(buys),
                "sell_count": len(sells),
                "unique_buyers": len({e.get("wallet") for e in buys if e.get("wallet")}),
                "unique_sellers": len({e.get("wallet") for e in sells if e.get("wallet")}),
                "buy_quote_volume_sol": sum(number(e.get("quote_amount_sol")) or 0 for e in buys),
                "sell_quote_volume_sol": sum(number(e.get("quote_amount_sol")) or 0 for e in sells),
                "price_open_usd": prices[0] if prices else None,
                "price_high_usd": max(prices) if prices else None,
                "price_low_usd": min(prices) if prices else None,
                "price_close_usd": prices[-1] if prices else None,
                "last_event_time": bounded[-1].get("event_ts") if bounded else None,
                "coverage": "RESOLVED" if bounded else "UNKNOWN",
            })
    return output


def build_outcomes(
    events: Iterable[Mapping[str, Any]],
    horizons: Sequence[int] = (3600, 14400, 86400, 172800, 259200),
    tolerance_seconds: int = 300,
) -> list[dict[str, Any]]:
    """Build fail-closed nearest marks with explicit right-censoring."""
    by_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("mint") and event.get("event_ts"):
            by_mint[str(event["mint"])].append(dict(event))
    output = []
    for mint, rows in sorted(by_mint.items()):
        rows.sort(key=event_order_key)
        launch_ts = next((e.get("launch_ts") for e in rows if e.get("launch_ts")), None)
        if not launch_ts:
            launch_ts = rows[0]["event_ts"]
        coverage_end = next((e.get("coverage_end") for e in rows if e.get("coverage_end")), None)
        for horizon in horizons:
            target = launch_ts + timedelta(seconds=horizon)
            candidates = [
                e for e in rows
                if e.get("price_usd") is not None
                and abs((e["event_ts"] - target).total_seconds()) <= tolerance_seconds
            ]
            candidates.sort(key=lambda e: (abs((e["event_ts"] - target).total_seconds()), event_order_key(e)))
            mark = candidates[0] if candidates else None
            status = "RESOLVED" if mark else ("RIGHT_CENSORED" if coverage_end and coverage_end < target else "UNKNOWN")
            output.append({
                "mint": mint,
                "horizon_seconds": horizon,
                "mark_price_usd": number(mark.get("price_usd")) if mark else None,
                "mark_observed_ts": mark.get("event_ts") if mark else None,
                "outcome_status": status,
            })
    return output


def fifo_realized_pnl(trades: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Calculate FIFO realized PnL, inventory, and fees for one wallet-token."""
    lots: deque[list[float]] = deque()
    realized = 0.0
    fees = 0.0
    for trade in sorted(trades, key=event_order_key):
        qty = number(trade.get("token_amount"))
        quote = number(trade.get("quote_amount_sol"))
        if not qty or qty <= 0 or quote is None or quote < 0:
            continue
        fees += number(trade.get("fee_sol")) or 0
        if trade.get("side") == "buy":
            lots.append([qty, quote])
            continue
        remaining = qty
        proceeds_per_token = quote / qty
        while remaining > 1e-12 and lots:
            lot_qty, lot_cost = lots[0]
            used = min(remaining, lot_qty)
            realized += used * (proceeds_per_token - lot_cost / lot_qty)
            remaining -= used
            lot_qty -= used
            lot_cost *= lot_qty / (lot_qty + used)
            if lot_qty <= 1e-12:
                lots.popleft()
            else:
                lots[0] = [lot_qty, lot_cost]
    return {
        "realized_pnl_sol_before_fees": realized,
        "fees_sol": fees,
        "inventory_remaining": sum(lot[0] for lot in lots),
    }


def participant_episodes_multi_token(
    events: Iterable[Mapping[str, Any]],
    launches: Mapping[str, Mapping[str, Any]] | None = None,
    entry_window_seconds: int = 300,
) -> list[dict[str, Any]]:
    """Create point-in-time wallet-token episodes across multiple mints."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        wallet, mint = event.get("wallet"), event.get("mint")
        if wallet and mint and event.get("side") in {"buy", "sell"} and event.get("event_ts"):
            grouped[(str(wallet), str(mint))].append(dict(event))
    result = []
    for (wallet, mint), trades in sorted(grouped.items()):
        buys = [e for e in trades if e.get("side") == "buy"]
        if not buys:
            continue
        first = min(buys, key=event_order_key)
        launch_ts = (launches or {}).get(mint, {}).get("launch_time")
        launch_ts = launch_ts or first.get("launch_ts") or first["event_ts"]
        seconds = (first["event_ts"] - launch_ts).total_seconds()
        pnl = fifo_realized_pnl(trades)
        result.append({
            "wallet": wallet,
            "mint": mint,
            "first_entry_time": first["event_ts"],
            "seconds_since_launch": seconds,
            "entry_within_window": 0 <= seconds <= entry_window_seconds,
            "number_of_buys": len(buys),
            "number_of_sells": sum(e.get("side") == "sell" for e in trades),
            **pnl,
        })
    return result


def point_in_time_history_multi_token(
    events: Iterable[Mapping[str, Any]], wallet: str, cutoff: datetime
) -> list[dict[str, Any]]:
    """Return only pre-cutoff wallet activity, grouped by token."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("wallet") == wallet and event.get("event_ts") and event["event_ts"] < cutoff:
            grouped[str(event.get("mint"))].append(dict(event))
    return [{"wallet": wallet, "mint": mint, "events": sorted(rows, key=event_order_key)} for mint, rows in sorted(grouped.items())]


def event_order_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("event_ts") or datetime.max.replace(tzinfo=UTC),
        row.get("slot") if row.get("slot") is not None else 2**63,
        row.get("tx_index") if row.get("tx_index") is not None else 2**31,
        row.get("outer_instruction_index") if row.get("outer_instruction_index") is not None else 2**31,
        row.get("inner_instruction_index") if row.get("inner_instruction_index") is not None else 2**31,
        row.get("transaction") or row.get("tx_id") or "",
    )


def number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def read_json_rows(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text())
    rows = payload.get("result", {}).get("rows", []) if isinstance(payload, dict) else payload
    return [dict(row) for row in rows if isinstance(row, dict)]


def next_incremental_checkpoint(
    previous_end: datetime | None, observed_end: datetime, *, overlap_seconds: int = 0
) -> tuple[datetime, datetime]:
    """Return a fail-closed [start, end) checkpoint for a daily refresh."""
    if observed_end.tzinfo is None:
        raise ValueError("observed_end must be timezone-aware")
    if previous_end is None:
        return observed_end - timedelta(days=1), observed_end
    if previous_end.tzinfo is None:
        raise ValueError("previous_end must be timezone-aware")
    start = previous_end - timedelta(seconds=overlap_seconds)
    if observed_end <= start:
        raise ValueError("observed_end must be after checkpoint start")
    return start, observed_end


def append_cost_ledger(path: str | Path, entry: Mapping[str, Any]) -> None:
    """Append one compact, redacted cost observation as JSONL."""
    required = {"timestamp", "query_name", "purpose", "decision"}
    missing = required - set(entry)
    if missing:
        raise ValueError(f"missing cost fields: {sorted(missing)}")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(entry), sort_keys=True, default=str) + "\n")
