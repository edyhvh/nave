from datetime import UTC, datetime, timedelta

import pytest

from research.core.context import context_is_usable


NOW = datetime(2026, 9, 4, tzinfo=UTC)


def context():
    return {"validated": True, "evidence_quality": "VALIDATED", "corroboration_status": "VALIDATED",
            "published_at": (NOW - timedelta(hours=2)).isoformat(), "validated_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(days=1)).isoformat()}


@pytest.mark.parametrize("override", [{"corroboration_status": "PARTIAL"}, {"contradictions": ["x"]},
    {"published_at": (NOW - timedelta(days=4)).isoformat()}, {"validated_at": "bad"},
    {"expires_at": NOW.isoformat()}, {"warnings": ["provider unavailable"]},
    {"validated_at": (NOW + timedelta(seconds=1)).isoformat()}])
def test_context_requires_complete_and_current_evidence(override):
    assert context_is_usable(context(), now=NOW)
    assert not context_is_usable(context() | override, now=NOW)
    assert not context_is_usable({"validated": True}, now=NOW)
