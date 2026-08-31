"""Invariant tests for the read-only dual-horizon research layer."""

from datetime import datetime, timedelta, timezone

import pytest

from trading.memecoin.m3_dual_horizon import (
    DEAD,
    PROVIDER_UNAVAILABLE,
    RESOLVED,
    UNKNOWN,
    UNEXITABLE,
    SYSTEM_PROGRAM,
    build_participant_profile,
    build_trajectory,
    classify_trajectory,
    clean_trade,
    cluster_trajectories,
    chronological_splits,
    classify_protocol_state,
    convergence_features,
    detect_sell_shocks,
    executable_return_pct,
    entry_timing_bucket,
    execution_price_constant_product,
    leave_one_participant_out,
    market_cap_from_price,
    reconstruct_episode,
    resolve_outcome,
    runner_exit_families,
    simulate_fast_burst_exit,
    trajectory_quality,
)


UTC = timezone.utc
T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def event(seconds, *, wallet="w1", side="buy", price=1.0, sol=1.0, **extra):
    return {
        "event_ts": (T0 + timedelta(seconds=seconds)).isoformat(),
        "wallet": wallet,
        "side": side,
        "price_usd": price,
        "sol_amount": sol,
        "token_amount": sol / price,
        "price_sol": price,
        **extra,
    }


def test_protocol_state_is_explicit_and_missing_is_unknown():
    state = classify_protocol_state({"mayhem_mode": True, "boost": False, "venue": "pumpswap"})
    assert state["mayhem_mode"] is True
    assert state["boost"] is False
    assert state["protocol_generated"] is None
    assert classify_protocol_state({})["canonical_pool"] is None


def test_mayhem_supply_uses_corrected_supply():
    assert market_cap_from_price(2.0, {"mayhem_mode": True}) == 4_000_000_000
    assert market_cap_from_price(2.0, {"mayhem_mode": True, "supply_corrected": 1_750_000}) == 3_500_000


def test_trade_quality_flags_system_program_missing_and_corrupt_rows():
    assert "SYSTEM_PROGRAM_WALLET" in clean_trade(event(1, wallet=SYSTEM_PROGRAM))["quality_flags"]
    assert "SOL_PRICE_MISSING" in clean_trade({**event(1), "sol_amount": None})["quality_flags"]
    assert "SOL_AMOUNT_SUSPECT" in clean_trade({**event(1), "sol_amount": 1_000_000})["quality_flags"]
    assert "CURVE_DEPLETION_OUT_OF_RANGE" in clean_trade({**event(1), "curve_pct_depleted": 110})["quality_flags"]


def test_trajectory_features_are_point_in_time_and_exclude_protocol_flow():
    events = [
        event(1, wallet="organic-1", price=1.0),
        event(100, wallet="protocol", price=1.2, protocol_generated=True),
        event(400, wallet="organic-2", price=2.0),
        event(1_000, wallet="organic-3", price=3.0),
    ]
    trajectory = build_trajectory("mint", events, launch_ts=T0, coverage_end=T0 + timedelta(hours=72))
    assert trajectory["intervals"]["5m"]["unique_buyers"] == 1
    assert trajectory["intervals"]["5m"]["protocol_generated_buy_volume_sol"] == 1.0
    assert trajectory["intervals"]["5m"]["cumulative_real_volume_sol"] == 1.0
    assert trajectory["intervals"]["10m"]["new_buyers"] == 1
    assert trajectory["intervals"]["30m"]["new_buyers"] == 1


def test_right_censoring_is_not_dead_or_loss():
    outcome = resolve_outcome(
        entry_ts=T0, entry_price=1.0, events=[], horizon_seconds=86_400,
        coverage_end=T0 + timedelta(hours=1),
    )
    assert outcome.status == UNKNOWN
    assert outcome.reason == "right_censored_at_collection_end"
    assert outcome.gross_return_pct is None


def test_outcome_statuses_preserve_dead_unexitability_and_provider_outage():
    kwargs = dict(entry_ts=T0, entry_price=1.0, events=[], horizon_seconds=300, coverage_end=T0 + timedelta(hours=1))
    assert resolve_outcome(**kwargs, pool_disappeared=True).status == DEAD
    assert resolve_outcome(**kwargs, route_available=False).status == UNEXITABLE
    assert resolve_outcome(**kwargs, provider_outage=True).status == PROVIDER_UNAVAILABLE
    resolved = resolve_outcome(**{**kwargs, "events": [event(301, price=1.5)]})
    assert resolved.status == RESOLVED
    assert resolved.gross_return_pct == pytest.approx(50.0)


def test_sell_shock_uses_only_prior_sell_history():
    events = [event(1, side="sell", sol=1), event(2, side="sell", sol=2), event(3, side="sell", sol=1), event(4, side="sell", sol=10)]
    shocks = detect_sell_shocks(events, multiplier=3.0, min_history=3)
    assert len(shocks) == 1
    assert shocks[0]["relative_size"] == pytest.approx(10.0)


def test_execution_pricing_and_notional_cap_are_fail_closed():
    output = execution_price_constant_product(input_amount=100, reserve_in=10_000, reserve_out=20_000)
    assert output is not None and 0 < output < 200
    assert executable_return_pct(
        entry_price=1, exit_price=1.2, notional_usd=100, liquidity_usd=50_000,
        fee_bps_round_trip=100, impact_bps_round_trip=100,
    ) == pytest.approx(17.6, abs=0.01)
    assert executable_return_pct(
        entry_price=1, exit_price=1.2, notional_usd=100, liquidity_usd=10_000,
        fee_bps_round_trip=100, impact_bps_round_trip=100,
    ) is None


def test_fifo_episode_keeps_open_inventory_separate_from_realized_result():
    trades = [event(1, side="buy", price=1, sol=10), event(2, side="sell", price=2, sol=5)]
    episode = reconstruct_episode("w1", "mint", trades, fee_bps=0)
    assert episode["state"] == "PARTIAL_REALIZATION"
    assert episode["realized_pnl"] > 0
    assert episode["remaining_inventory"] > 0


def test_participant_profile_cannot_use_future_episode():
    episodes = [
        {"participant": "w1", "outcome_ts": "2026-06-02T00:00:00Z", "eligible": True, "outcome": "FAST_BURST", "realized_return_pct": 10},
        {"participant": "w1", "outcome_ts": "2026-06-04T00:00:00Z", "eligible": True, "outcome": "SUSTAINED_RUNNER", "realized_return_pct": 20},
    ]
    profile = build_participant_profile("w1", episodes, as_of=datetime(2026, 6, 3, tzinfo=UTC))
    assert profile.prior_episodes == 1
    assert profile.burst_hits == 1
    assert profile.runner_hits == 0
    assert profile.discovery_hit_rate == pytest.approx(2 / 3)


def test_convergence_counts_clusters_not_wallets():
    entries = [event(0, wallet="a", economic_cluster="cluster-1"), event(1, wallet="b", economic_cluster="cluster-1"), event(2, wallet="c", economic_cluster="cluster-2")]
    result = convergence_features(entries, window_seconds=60)
    assert result["informative_participants"] == 3
    assert result["independent_clusters"] == 2


def test_chronological_split_adds_purge_gap():
    timestamps = [T0 + timedelta(hours=i) for i in range(10)]
    boundaries = chronological_splits(timestamps, horizon_seconds=3600)
    assert boundaries["holdout_start"] > boundaries["validation_end"]
    assert boundaries["validation_start"] > boundaries["development_end"]


def test_cluster_discovery_is_bounded_and_does_not_require_labels():
    trajectories = []
    for i in range(4):
        trajectories.append({
            "mint": f"m{i}",
            "intervals": {
                "5m": {"price": 1, "cumulative_real_volume_sol": 1, "unique_buyers": 1, "liquidity_usd": 10_000},
                "30m": {"price": 1 + i, "cumulative_real_volume_sol": 2 + i, "unique_buyers": 2 + i, "liquidity_usd": 10_000 + i},
                "4h": {"price": 1 + i, "cumulative_real_volume_sol": 3 + i, "unique_buyers": 3 + i, "liquidity_usd": 10_000 + i},
                "24h": {"price": 1 + i, "cumulative_real_volume_sol": 4 + i, "unique_buyers": 4 + i, "liquidity_usd": 10_000 + i},
                "48h": {"price": 1 + i, "cumulative_real_volume_sol": 5 + i, "unique_buyers": 5 + i, "liquidity_usd": 10_000 + i},
            },
        })
    result = cluster_trajectories(trajectories, 2)
    assert result["status"] == "OK"
    assert sum(result["cluster_sizes"].values()) == 4


def test_trajectory_taxonomy_requires_complete_quality_evidence():
    trajectory = build_trajectory("mint", [event(0, price=1), event(1_000, price=3)], launch_ts=T0, coverage_end=T0 + timedelta(hours=72))
    assert classify_trajectory(trajectory) in {"MINOR_PUMP", "SLOW_BLEED", "FALSE_RUNNER"}
    assert trajectory_quality(trajectory)["market_cap_alone_is_qualification"] is False


def test_fast_burst_preserves_stop_first_and_runner_exits_are_predeclared():
    events = [event(1, price=0.8), event(2, price=1.3), event(14_401, price=1.1)]
    result = simulate_fast_burst_exit(T0, 1.0, events)
    assert result["exit_reason"] == "STOP"
    exits = runner_exit_families(T0, 1.0, events, fixed_horizons=(3,))
    assert "3s" in exits["fixed"]


def test_entry_timing_and_leave_one_out_are_identity_agnostic_helpers():
    assert entry_timing_bucket(age_seconds=10, curve_progress=0.1, market_cap_fraction_of_peak=0.05) == "ULTRA_EARLY"
    summaries = leave_one_participant_out([
        {"participant": "a", "net_return_pct": 10},
        {"participant": "b", "net_return_pct": -10},
    ])
    assert {row["removed_participant"] for row in summaries} == {"a", "b"}
