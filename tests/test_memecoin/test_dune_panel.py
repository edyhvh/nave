"""Offline tests for the Dune-to-local transformation layer."""

from datetime import datetime, timedelta, timezone

from research.dune.panel import normalize_proof_events, participant_episodes, point_in_time_history, reconstruct_price_sol

UTC = timezone.utc
T0 = datetime(2026, 8, 27, 11, 33, 18, tzinfo=UTC)


def row(seconds, *, side=None, wallet=None, event_type="BUY", slot=1, tx="tx"):
    return {
        "mint": "mint",
        "event_time": (T0 + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S.000 UTC"),
        "block_slot": slot,
        "tx_id": tx,
        "tx_index": 1,
        "outer_instruction_index": 1,
        "inner_instruction_index": 1,
        "event_type": event_type,
        "venue": "pumpfun",
        "wallet": wallet,
        "side": side,
        "token_amount": 10.0 if side else None,
        "quote_amount_sol": 1.0 if side else None,
        "price_sol": 0.1 if side else None,
        "price_usd": 10.0 if side else None,
        "pool_id": None,
        "creator": "creator",
    }


def test_normalization_links_migration_pool_to_post_migration_events():
    events = normalize_proof_events([
        row(0, side=None, event_type="CREATE"),
        {**row(60, side=None, event_type="MIGRATE"), "pool_id": "pool"},
        {**row(61, side="buy", wallet="w"), "venue": "pumpswap", "event_type": "PUMPSWAP_BUY"},
    ])
    assert events[-1]["pool_id"] == "pool"
    assert events[-1]["event_ts"] == T0 + timedelta(seconds=61)


def test_episode_landmarks_and_realized_inventory_are_separate():
    events = normalize_proof_events([
        row(0, side=None, event_type="CREATE"),
        row(10, side="buy", wallet="w"),
        {**row(20, side="sell", wallet="w"), "token_amount": 5.0, "quote_amount_sol": 1.0, "price_sol": 0.2},
    ])
    episode = participant_episodes(events, T0)[0]
    assert episode["entry_30s"] and episode["entry_60s"] and episode["entry_5m"]
    assert episode["inventory_remaining"] == 5.0
    assert episode["realized_pnl_sol_before_fees"] > 0


def test_point_in_time_history_excludes_cutoff_and_future_events():
    events = normalize_proof_events([row(0, side=None, event_type="CREATE"), row(10, side="buy", wallet="past"), row(70, side="buy", wallet="future")])
    history = point_in_time_history(events, T0 + timedelta(seconds=70))
    assert history["prior_wallets"] == ["past"]
    assert history["future_event_exclusion_checked"] is True


def test_price_reconstruction_is_fail_closed():
    assert reconstruct_price_sol(2, 10) == 0.2
    assert reconstruct_price_sol(None, 10) is None
    assert reconstruct_price_sol(2, 0) is None


def test_duplicate_decoded_event_is_removed_without_collapsing_same_tx_events():
    events = normalize_proof_events([row(0, side=None, event_type="CREATE"), row(1, side="buy", wallet="w", tx="same"), row(1, side="buy", wallet="w", tx="same"), row(1, side="buy", wallet="x", tx="same", slot=2)])
    assert len([e for e in events if e.get("side") == "buy"]) == 2
