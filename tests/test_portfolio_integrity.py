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
