from datetime import UTC, datetime

import pytest

from research.core.contracts import ResearchStatus
from research.portfolio import PortfolioState, PositionState, check_watch, review_positions

NOW = datetime(2026, 9, 6, tzinfo=UTC)
WATCH = [{"ticker": "CAT", "condition": "ZONE", "zone": [767, 799]}]


def test_zone_alert_clears_and_rearms_without_repeating():
    assert check_watch(WATCH, {"CAT": 781}, now=NOW).payload["events"]
    assert not check_watch(WATCH, {"CAT": 782}, previous_prices={"CAT": 781}, now=NOW).payload["events"]
    assert not check_watch(WATCH, {"CAT": 810}, previous_prices={"CAT": 782}, now=NOW).payload["events"]
    assert check_watch(WATCH, {"CAT": 781}, previous_prices={"CAT": 810}, now=NOW).payload["events"]


@pytest.mark.parametrize("price", [None, "bad", float("nan"), float("inf"), -1, True])
def test_invalid_prices_never_become_no_setup(price):
    result = check_watch(WATCH, {"CAT": price}, now=NOW)
    assert result.status is ResearchStatus.DATA_UNAVAILABLE
    assert result.payload["events"] == []


def test_stale_prices_and_incomplete_review_fail_closed():
    assert check_watch(WATCH, {"CAT": 781}, price_timestamps={"CAT": "2026-08-01T00:00:00Z"}, now=NOW).status is ResearchStatus.DATA_UNAVAILABLE
    state = PortfolioState(positions=(PositionState("CAT"),))
    decision = review_positions(state, {"CAT": {"macro_regime": "neutral", "technical_condition": "healthy"}}, now=NOW).payload["positions"][0]
    assert decision["action"] == "REVIEW_REQUIRED"
    assert "price_missing_stale_or_invalid" in decision["reasons"]


def test_cross_missing_previous_is_insufficient():
    result = check_watch([{'ticker': 'CAT', 'condition': 'CROSS_ABOVE', 'threshold': 780}], {'CAT': 781}, now=NOW)
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.payload['missing_previous'] == ['CAT']


def test_same_observation_preserves_rules_in_one_notification():
    result = check_watch(WATCH + [{'ticker': 'CAT', 'condition': 'BELOW', 'threshold': 800}], {'CAT': 781}, now=NOW)
    assert len(result.payload['events']) == 1
    assert len(result.payload['events'][0]['matched_rules']) == 2


def test_watch_result_and_state_survive_failure_after_commit(tmp_path, monkeypatch):
    import json
    from typer.testing import CliRunner
    from cli.main import app
    from cli.commands import portfolio
    from research.core.store import ResearchStore
    now = datetime.now(UTC).isoformat()
    watches = tmp_path / 'watches.json'
    prices = tmp_path / 'prices.json'
    watches.write_text(json.dumps({'watches': WATCH}))
    prices.write_text(json.dumps({'prices': {'CAT': 781}, 'observed_at': {'CAT': now}}))
    command = ['portfolio', 'watch', '--watch-file', str(watches), '--prices-file', str(prices), '--state-dir', str(tmp_path / 'state'), '--json']
    emit = portfolio._emit
    monkeypatch.setattr(portfolio, '_emit', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('crash after commit')))
    assert CliRunner().invoke(app, command).exit_code != 0
    assert ResearchStore(tmp_path / 'state').load_result('portfolio.watch').payload['observation_state']['CAT'] == 781
    monkeypatch.setattr(portfolio, '_emit', emit)
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0
    assert json.loads(result.stdout)['payload']['events'] == []
