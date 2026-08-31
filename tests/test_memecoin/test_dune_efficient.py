"""Offline tests for the credit-efficient Dune panel architecture."""

from datetime import datetime, timedelta, timezone
import json

from research.dune.efficient import (
    append_cost_ledger,
    build_outcomes,
    deterministic_mint_sample,
    first_hour_aggregate_query,
    migration_query,
    first_hour_query,
    next_incremental_checkpoint,
    participant_episodes_multi_token,
    point_in_time_history_multi_token,
    token_panel_query,
    pumpswap_query,
    window_aggregate,
)

UTC = timezone.utc
T0 = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def event(mint, wallet, seconds, side, price, qty=10.0, quote=1.0):
    return {
        "mint": mint,
        "wallet": wallet,
        "event_ts": T0 + timedelta(seconds=seconds),
        "launch_ts": T0,
        "side": side,
        "price_usd": price,
        "token_amount": qty,
        "quote_amount_sol": quote,
        "fee_sol": 0.01,
        "slot": seconds + 1,
        "tx_index": 0,
        "outer_instruction_index": 0,
        "inner_instruction_index": 0,
        "transaction": f"{mint}-{wallet}-{seconds}",
    }


def test_deterministic_sample_is_stable_and_outcome_independent():
    launches = [{"mint": f"mint-{i}", "outcome": i} for i in range(20)]
    first = deterministic_mint_sample(launches, 7)
    second = deterministic_mint_sample(list(reversed(launches)), 7)
    assert [r["mint"] for r in first] == [r["mint"] for r in second]
    assert len(first) == 7


def test_window_aggregation_has_no_launch_landmark_explosion():
    rows = [event("a", "w", 5, "buy", 1), event("a", "w", 35, "sell", 2)]
    aggregate = window_aggregate(rows, [30, 60, 300])
    assert len(aggregate) == 3
    assert [r["trade_count"] for r in aggregate] == [1, 2, 2]


def test_first_hour_query_is_single_pass_and_bounded():
    sql = first_hour_query(["mint-a", "mint-b"], start="2026-08-27 00:00:00", end="2026-08-28 00:00:00")
    assert "selected_mints" in sql
    assert "CROSS JOIN" not in sql.upper()
    assert "UNNEST" not in sql.upper()  # no artificial landmark rows
    assert "evt_block_time >= TIMESTAMP" in sql


def test_first_hour_aggregate_is_one_row_per_mint():
    sql = first_hour_aggregate_query(["mint-a"], start="2026-08-27 00:00:00", end="2026-08-28 00:00:00")
    assert "GROUP BY mint" in sql
    assert "date_diff('second', e.event_time, e.event_time)" not in sql


def test_token_panel_keeps_one_row_per_mint_and_separates_horizons():
    sql = token_panel_query(["mint-a", "mint-b"], start="2026-08-27 00:00:00", end="2026-08-28 00:00:00", observation_end="2026-08-30 00:00:00")
    assert "GROUP BY l.mint" in sql
    assert "trade_count_60m" in sql and "mark_price_72h_usd" in sql
    assert "CROSS JOIN" not in sql.upper()


def test_migration_query_is_migration_first():
    sql = migration_query(["mint-a"], start="2026-08-27 00:00:00", end="2026-08-31 00:00:00")
    assert "selected_mints" in sql and "pump_call_migrate" in sql
    assert "GROUP BY m.account_mint" in sql


def test_pumpswap_query_has_chain_and_time_bounds():
    sql = pumpswap_query(["mint-a"], start="2026-08-27 00:00:00", end="2026-08-30 00:00:00")
    assert "d.blockchain = 'solana'" in sql
    assert "d.block_time >= TIMESTAMP" in sql and "d.block_time < TIMESTAMP" in sql


def test_right_censoring_does_not_turn_missing_mark_into_zero():
    rows = [event("a", "w", 10, "buy", 1)]
    rows[0]["coverage_end"] = T0 + timedelta(minutes=30)
    outcome = build_outcomes(rows, horizons=[3600])[0]
    assert outcome["outcome_status"] == "RIGHT_CENSORED"
    assert outcome["mark_price_usd"] is None


def test_incremental_checkpoint_is_half_open_and_overlap_is_explicit():
    previous = T0 + timedelta(days=1)
    start, end = next_incremental_checkpoint(previous, T0 + timedelta(days=2), overlap_seconds=60)
    assert start == previous - timedelta(seconds=60)
    assert end == T0 + timedelta(days=2)


def test_cost_ledger_appends_compact_jsonl(tmp_path):
    target = tmp_path / "query_cost_ledger.jsonl"
    append_cost_ledger(target, {"timestamp": "now", "query_name": "probe", "purpose": "test", "decision": "keep"})
    record = json.loads(target.read_text())
    assert record["query_name"] == "probe"


def test_multi_token_episodes_and_point_in_time_history():
    rows = []
    for i in range(10):
        wallet = f"wallet-{i}"
        rows.extend([
            event("mint-a", wallet, 10, "buy", 1, quote=1),
            event("mint-a", wallet, 20, "sell", 2, qty=5, quote=1),
            event("mint-b", wallet, 30, "buy", 1, quote=1),
            event("mint-b", wallet, 40, "sell", 0.5, qty=5, quote=0.25),
            event("mint-b", wallet, 400, "buy", 1),
        ])
    episodes = participant_episodes_multi_token(rows, {"mint-a": {"launch_time": T0}, "mint-b": {"launch_time": T0}})
    assert len(episodes) == 20
    assert {row["mint"] for row in episodes} == {"mint-a", "mint-b"}
    assert all(row["entry_within_window"] for row in episodes)
    assert all(row["realized_pnl_sol_before_fees"] > 0 for row in episodes if row["mint"] == "mint-a")
    history = point_in_time_history_multi_token(rows, "wallet-0", T0 + timedelta(seconds=100))
    assert {row["mint"] for row in history} == {"mint-a", "mint-b"}
    assert all(max(e["event_ts"] for e in row["events"]) < T0 + timedelta(seconds=100) for row in history)
