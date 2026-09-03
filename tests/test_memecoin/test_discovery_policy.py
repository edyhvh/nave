"""Tests for the chain-neutral asymmetric-discovery admission policy."""

from __future__ import annotations

from trading.memecoin.discovery_policy import (
    REQUIRED_GATES,
    CandidateEvidence,
    Chain,
    GateEvidence,
    GateStatus,
    Recommendation,
    RiskPlan,
    RunOutcome,
    evaluate_candidate,
    summarize_run,
)


def _passing_gates() -> dict[str, GateEvidence]:
    return {
        name: GateEvidence(
            status=GateStatus.PASS,
            observed_at="2026-08-21T10:00:00+00:00",
            source_urls=(f"https://evidence.example/{name}",),
            details=f"{name} verified",
        )
        for name in REQUIRED_GATES
    }


def _risk_plan(**overrides: object) -> RiskPlan:
    values: dict[str, object] = {
        "entry_zone_low_usd": 0.0009,
        "entry_zone_high_usd": 0.001,
        "invalidation_price_usd": 0.00075,
        "max_loss_usd": 25.0,
        "max_loss_pct_nav": 0.25,
        "max_position_usd": 100.0,
        "max_exit_notional_usd": 150.0,
        "liquidity_aware_exit": "Exit in two clips, each below 1% of verified pool depth.",
        "monitoring_triggers": ("deployer transfer", "liquidity down 20%"),
        "execution_trigger": "1h reclaim and retest inside the entry zone",
        "time_stop": "exit after 24h if the trigger has not expanded",
        "targets_usd": (0.00125, 0.0015),
        "fee_slippage_bps": 150.0,
    }
    values.update(overrides)
    return RiskPlan(**values)  # type: ignore[arg-type]


def _candidate(
    *,
    chain: Chain = Chain.SOLANA,
    gates: dict[str, GateEvidence] | None = None,
    risk_plan: RiskPlan | None = None,
    trigger_confirmed: bool = False,
) -> CandidateEvidence:
    return CandidateEvidence(
        chain=chain,
        asset_address="AssetAddress111",
        symbol="ASYM",
        observed_at="2026-08-21T10:01:00+00:00",
        hypothesis="Verified liquidity plus controlled distribution may support a short move.",
        timeframe="1h trigger; maximum 24h hold",
        gates=gates if gates is not None else _passing_gates(),
        risk_plan=risk_plan if risk_plan is not None else _risk_plan(),
        trigger_confirmed=trigger_confirmed,
    )


def test_complete_candidate_without_trigger_is_watch() -> None:
    decision = evaluate_candidate(_candidate())

    assert decision.recommendation == Recommendation.WATCH
    assert decision.eligible is True
    assert decision.human_gate_required is True
    assert decision.blockers == ()


def test_complete_candidate_with_trigger_is_human_gated_enter() -> None:
    decision = evaluate_candidate(_candidate(chain=Chain.TON, trigger_confirmed=True))

    assert decision.recommendation == Recommendation.ENTER
    assert decision.eligible is True
    assert decision.human_gate_required is True
    assert decision.to_dict()["chain"] == "ton"


def test_any_hard_gate_failure_forces_review() -> None:
    gates = _passing_gates()
    gates["authorities"] = GateEvidence(
        status=GateStatus.FAIL,
        observed_at="2026-08-21T10:00:00+00:00",
        source_urls=("https://evidence.example/authorities",),
        details="mint authority remains active",
    )

    decision = evaluate_candidate(_candidate(gates=gates, trigger_confirmed=True))

    assert decision.recommendation == Recommendation.REVIEW
    assert decision.eligible is False
    assert decision.terminal_rejection is True
    assert "hard_fail:authorities" in decision.blockers


def test_unknown_or_untraceable_gate_fails_closed() -> None:
    gates = _passing_gates()
    gates["unlocks"] = GateEvidence(
        status=GateStatus.UNKNOWN,
        observed_at="2026-08-21T10:00:00+00:00",
        source_urls=("https://evidence.example/unlocks",),
    )
    gates["volume_integrity"] = GateEvidence(
        status=GateStatus.PASS,
        observed_at=None,
        source_urls=(),
    )

    decision = evaluate_candidate(_candidate(gates=gates))

    assert decision.recommendation == Recommendation.REVIEW
    assert decision.terminal_rejection is False
    assert "unknown:unlocks" in decision.blockers
    assert "untraceable:volume_integrity" in decision.blockers


def test_missing_required_gate_fails_closed() -> None:
    gates = _passing_gates()
    gates.pop("custody_bridge")

    decision = evaluate_candidate(_candidate(gates=gates))

    assert decision.recommendation == Recommendation.REVIEW
    assert "missing_gate:custody_bridge" in decision.blockers


def test_incomplete_or_unexitable_risk_plan_forces_review() -> None:
    plan = _risk_plan(
        max_position_usd=200.0,
        max_exit_notional_usd=100.0,
        monitoring_triggers=(),
    )

    decision = evaluate_candidate(_candidate(risk_plan=plan, trigger_confirmed=True))

    assert decision.recommendation == Recommendation.REVIEW
    assert "risk_plan:position_exceeds_exit_capacity" in decision.blockers
    assert "risk_plan:monitoring_triggers" in decision.blockers


def test_complete_run_can_return_valid_no_setup() -> None:
    gates = _passing_gates()
    gates["liquidity"] = GateEvidence(
        status=GateStatus.FAIL,
        observed_at="2026-08-21T10:00:00+00:00",
        source_urls=("https://evidence.example/liquidity",),
        details="depth below configured floor",
    )
    rejected = evaluate_candidate(_candidate(gates=gates))

    summary = summarize_run(
        [rejected],
        universe_count=1,
        coverage_complete=True,
    )

    assert summary.outcome == RunOutcome.NO_VALID_SETUP
    assert summary.valid_no_setup is True
    assert summary.coverage_complete is True
    assert summary.blocker_counts == {"hard_fail:liquidity": 1}


def test_unresolved_review_cannot_become_valid_no_setup() -> None:
    gates = _passing_gates()
    gates["unlocks"] = GateEvidence(
        status=GateStatus.UNKNOWN,
        observed_at="2026-08-21T10:00:00+00:00",
        source_urls=("https://evidence.example/unlocks",),
    )
    unresolved = evaluate_candidate(_candidate(gates=gates))

    summary = summarize_run(
        [unresolved],
        universe_count=1,
        coverage_complete=True,
    )

    assert summary.outcome == RunOutcome.DATA_INCOMPLETE
    assert summary.valid_no_setup is False


def test_source_failure_cannot_masquerade_as_no_setup() -> None:
    summary = summarize_run(
        [],
        universe_count=10,
        coverage_complete=False,
        source_errors=["ton_indexer_timeout"],
    )

    assert summary.outcome == RunOutcome.DATA_INCOMPLETE
    assert summary.valid_no_setup is False
    assert summary.coverage_complete is False


def test_partial_evaluation_is_data_incomplete_even_without_explicit_error() -> None:
    decision = evaluate_candidate(_candidate())

    summary = summarize_run(
        [decision],
        universe_count=2,
        coverage_complete=True,
    )

    assert summary.outcome == RunOutcome.DATA_INCOMPLETE
    assert summary.valid_no_setup is False


def test_watch_only_run_is_not_no_setup() -> None:
    decision = evaluate_candidate(_candidate())

    summary = summarize_run(
        [decision],
        universe_count=1,
        coverage_complete=True,
    )

    assert summary.outcome == RunOutcome.WATCHLIST_ONLY
    assert summary.valid_no_setup is False
