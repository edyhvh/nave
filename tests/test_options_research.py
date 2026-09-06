from datetime import UTC, datetime

from research.options import (
    OptionDomain,
    OptionResearchWorkflow,
    StrategyState,
    strategy_definition,
)
from research.core.contracts import ResearchStatus, SafetyBoundary


DECISION = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _snapshot(**overrides):
    row = {
        "underlying": "BTC",
        "available_at": "2026-09-04T11:00:00+00:00",
        "event_time": "2026-09-04T10:55:00+00:00",
        "implied_volatility": 0.48,
        "realized_volatility": 0.35,
        "skew": 0.02,
        "term_structure": "contango",
        "macro_regime": "risk_on",
        "volatility_regime": "elevated",
        "catalyst": "scheduled event",
        "directional_thesis": "neutral-to-bullish",
        "defined_risk": True,
        "source": "fixture",
    }
    row.update(overrides)
    return row


def test_strategy_definitions_keep_crypto_and_stocks_separate_and_conservative():
    crypto = strategy_definition(OptionDomain.CRYPTO)
    stocks = strategy_definition(OptionDomain.STOCKS)

    assert crypto.underlyings == ("BTC", "ETH")
    assert stocks.underlyings == ("EQUITY_UNIVERSE",)
    assert crypto.state is StrategyState.EXPERIMENTAL
    assert crypto.to_dict()["read_only"] is True


def test_scan_exposes_volatility_inputs_and_structured_read_only_result():
    result = OptionResearchWorkflow(clock=lambda: DECISION).scan(
        "crypto", [_snapshot()], decision_time=DECISION
    )

    assert result.status is ResearchStatus.STRATEGY_NOT_VALIDATED
    assert result.payload["eligible_inputs"] == 1
    assert result.payload["observations"][0]["iv_rv_spread"] == 0.13
    assert result.payload["execution_enabled"] is False
    assert result.safety_boundary is SafetyBoundary.READ_ONLY_RESEARCH_ONLY_HUMAN_GATED


def test_scan_rejects_unknown_availability_and_out_of_scope_assets_without_hindsight():
    result = OptionResearchWorkflow(clock=lambda: DECISION).scan(
        "crypto",
        [_snapshot(underlying="SOL"), _snapshot(available_at=None)],
        decision_time=DECISION,
    )

    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    reasons = {item["reason"] for item in result.payload["rejected_inputs"]}
    assert reasons == {"outside_crypto_scope", "availability_unknown"}


def test_scan_handles_insufficient_volatility_data():
    result = OptionResearchWorkflow(clock=lambda: DECISION).scan(
        "stocks", [_snapshot(underlying="AAPL", realized_volatility=None)], decision_time=DECISION
    )

    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.payload["rejected_inputs"][0]["reason"] == "missing_dimensions"


def test_evaluation_is_statistically_explicit_and_does_not_auto_validate():
    outcomes = [{"forward_return_pct": 2.0} for _ in range(30)]
    result = OptionResearchWorkflow(clock=lambda: DECISION).evaluate(
        "crypto", outcomes, decision_time=DECISION
    )

    assert result.payload["strategy_state"] == StrategyState.EXPERIMENTAL.value
    assert result.payload["metrics"]["sample_size"] == 0
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert "VALIDATED" in result.payload["validation_gate"]


def test_evaluation_with_no_outcomes_is_insufficient_evidence():
    result = OptionResearchWorkflow(clock=lambda: DECISION).evaluate(
        "stocks", [], decision_time=DECISION
    )

    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.payload["strategy_state"] == StrategyState.EXPERIMENTAL.value


def test_outcomes_require_identity_finite_returns_and_later_timestamp():
    from datetime import timedelta
    workflow = OptionResearchWorkflow()
    scan = workflow.scan('crypto', [_snapshot()], decision_time=DECISION)
    outcome = {'strategy': scan.metadata.strategy_name, 'underlying': 'BTC',
               'source_scan_run_id': scan.metadata.run_id, 'decision_time': DECISION.isoformat(),
               'observed_at': (DECISION + timedelta(hours=1)).isoformat(), 'forward_return_pct': 2}
    result = workflow.evaluate('crypto', [outcome], scan_results=[scan], decision_time=DECISION + timedelta(days=1))
    assert result.payload['metrics']['sample_size'] == 1
    assert result.payload['cost_basis'] == 'GROSS_UNCOSTED'
    assert result.payload['strategy_state'] == 'EXPERIMENTAL'
    for change in [{'forward_return_pct': float('inf')}, {'forward_return_pct': float('nan')},
                   {'observed_at': DECISION.isoformat()}, {'underlying': 'ETH'}, {'source_scan_run_id': 'other'}]:
        rejected = workflow.evaluate('crypto', [{**outcome, **change}], scan_results=[scan], decision_time=DECISION + timedelta(days=1))
        assert rejected.payload['metrics']['sample_size'] == 0
        assert rejected.payload['strategy_state'] != 'VALIDATED'
