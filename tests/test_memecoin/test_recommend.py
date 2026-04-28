"""Tests for memecoin recommendation and timing gates."""

from __future__ import annotations

from trading.memecoin.recommend import recommend_for_candidate
from trading.memecoin.safety_check import SafetyReport, SafetyVerdict
from trading.memecoin.scanner import MemecoinCandidate
from trading.memecoin.scoring import Label, ScoreBreakdown
from trading.memecoin.timing import EntryTiming



def _candidate(*, mint: str, timing: EntryTiming, passed: bool = True) -> MemecoinCandidate:
    safety = SafetyReport(
        mint=mint,
        verdict=SafetyVerdict.PASS if passed else SafetyVerdict.FAIL,
        rug_score=0 if passed else 50,
        checks={},
        dev_wallets=[],
        honeypot_flags=[],
        raw={},
    )
    score = ScoreBreakdown(
        mint=mint,
        total=80 if passed else 10,
        label=Label.GOOD if passed else Label.SHILL,
        bands={},
        rationale=[],
    )
    return MemecoinCandidate(
        mint=mint,
        name="Token",
        symbol="TOK",
        market=None,
        safety=safety,
        score=score,
        discovered_via="test",
        skipped_reason=None if passed else "failed checks",
        entry_timing=timing,
        seen_count_24h=1,
        first_seen_at="2026-04-28T11:55:00+00:00",
        last_seen_at="2026-04-28T12:00:00+00:00",
    )



def test_recommend_enter_now_for_early_candidate():
    candidate = _candidate(mint="AAA", timing=EntryTiming.EARLY, passed=True)

    result = recommend_for_candidate(
        candidate,
        capital_usd=10_000,
        memecoin_exposure_usd=0,
        history={},
    )

    assert result.enter_now is True
    assert result.entry_timing == EntryTiming.EARLY
    assert result.position_size_usd == 25.0



def test_recommend_skips_extended_candidate():
    candidate = _candidate(mint="AAA", timing=EntryTiming.EXTENDED, passed=True)

    result = recommend_for_candidate(
        candidate,
        capital_usd=10_000,
        memecoin_exposure_usd=0,
        history={},
    )

    assert result.enter_now is False
    assert result.position_size_usd == 0.0
    assert "EXTENDED" in result.reason



def test_recommend_skips_when_class_cap_reached():
    candidate = _candidate(mint="AAA", timing=EntryTiming.EARLY, passed=True)

    result = recommend_for_candidate(
        candidate,
        capital_usd=10_000,
        memecoin_exposure_usd=500,
        history={},
    )

    assert result.enter_now is False
    assert result.position_size_usd == 0.0
    assert "class-cap" in result.reason
