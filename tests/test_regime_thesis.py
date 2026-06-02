from __future__ import annotations

from unittest.mock import MagicMock

from trading.crypto.analysis.regime import RegimeAssessment
from trading.crypto.analysis.regime_thesis import (
    RegimeThesisStore,
    apply_thesis_to_recommendation,
    reconcile_regime_thesis,
)


def test_reconcile_arms_bearish_thesis(tmp_path):
    store = RegimeThesisStore(path=tmp_path / "regime_theses.json")
    regime = RegimeAssessment(
        phase="leg_down",
        bias="bearish",
        confidence=0.7,
        playbook="bear leg",
        supply_zone=[69000.0, 71000.0],
        continuation_trigger="breakdown",
        metrics={"drawdown_from_28d_high_pct": 12.0},
    )
    overlay = reconcile_regime_thesis(
        coin="BTC",
        regime=regime,
        cot_bias_label="bearish",
        price=68000.0,
        invalidation=72000.0,
        store=store,
        max_age_hours=336,
    )
    assert overlay["thesis_state"] == "active"
    assert overlay["thesis_status"] == "armed"
    assert overlay["thesis_direction"] == "short"


def test_apply_thesis_elevates_stand_aside_to_watch():
    rec = {
        "coin": "ETH",
        "action": "stand_aside",
        "direction": None,
        "confidence": 0.0,
        "primary_source": "none",
        "reasons": [],
        "blockers": [],
    }
    overlay = {
        "thesis_state": "active",
        "thesis_status": "armed",
        "thesis_phase": "leg_down",
        "thesis_playbook": "Active bear",
        "thesis_supply_zone": [3000.0, 3200.0],
        "thesis_direction": "short",
        "thesis_created_at": "2026-06-01T00:00:00+00:00",
    }
    out = apply_thesis_to_recommendation(rec, overlay)
    assert out["action"] == "watch"
    assert out["direction"] == "short"
    assert out["primary_source"] == "regime_thesis"