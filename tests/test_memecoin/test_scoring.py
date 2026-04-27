"""Unit tests for the transparent scoring rubric."""

from __future__ import annotations

from trading.memecoin.data_provider import TokenMarket
from trading.memecoin.safety_check import SafetyReport, SafetyVerdict
from trading.memecoin.scoring import (
    GOOD_THRESHOLD,
    LIQUIDITY_FLOOR_USD,
    Label,
    WATCH_THRESHOLD,
    score_candidate,
)

MINT = "ScoreTestMint11111111111111111111111111111111"


def _market(**overrides) -> TokenMarket:
    base = dict(
        mint=MINT,
        price_usd=0.0001,
        liquidity_usd=200_000.0,
        fdv_usd=1_500_000.0,
        market_cap_usd=1_500_000.0,
        volume_24h_usd=900_000.0,
        pair_address="Pair",
        dex="raydium",
        age_minutes=240,
        price_change_5m_pct=10.0,
        price_change_1h_pct=25.0,
    )
    base.update(overrides)
    return TokenMarket(**base)


def test_strong_market_yields_good_label():
    score = score_candidate(MINT, _market())
    assert score.label == Label.GOOD
    assert score.total >= GOOD_THRESHOLD


def test_zero_market_data_yields_shill():
    # No market at all → all bands zero → SHILL.
    score = score_candidate(MINT, None)
    assert score.label == Label.SHILL
    assert score.total < WATCH_THRESHOLD
    assert score.bands == {} or all(
        band.get("points", 0) == 0 for band in score.bands.values()
    )


def test_below_floor_liquidity_zeros_band():
    # Liquidity sub-floor scores 0 even if everything else is healthy.
    score = score_candidate(MINT, _market(liquidity_usd=LIQUIDITY_FLOOR_USD - 1))
    liq_band = score.bands["liquidity"]
    assert liq_band["points"] == 0
    assert any("below floor" in r for r in score.rationale)


def test_too_low_fdv_penalised():
    score = score_candidate(MINT, _market(fdv_usd=10_000.0, market_cap_usd=10_000.0))
    fdv_band = score.bands["fdv"]
    assert fdv_band["points"] <= 5  # rug-bait band caps low


def test_too_high_fdv_penalised():
    score = score_candidate(
        MINT, _market(fdv_usd=200_000_000.0, market_cap_usd=200_000_000.0)
    )
    fdv_band = score.bands["fdv"]
    assert fdv_band["points"] <= 4


def test_parabolic_momentum_does_not_max_band():
    # 5m=+200% / 1h=+500% should NOT score a full band — exhaustion risk.
    score = score_candidate(
        MINT,
        _market(price_change_5m_pct=200.0, price_change_1h_pct=500.0),
    )
    mom_band = score.bands["momentum"]
    assert mom_band["points"] < mom_band["max"]


def test_safety_fail_clamps_to_shill():
    fake_safety = SafetyReport(
        mint=MINT,
        verdict=SafetyVerdict.FAIL,
        rug_score=70,
        checks={},
        dev_wallets=[],
        honeypot_flags=["no_sell_route_via_jupiter"],
        raw={},
    )
    score = score_candidate(MINT, _market(), safety=fake_safety)
    assert score.label == Label.SHILL
    assert score.total < WATCH_THRESHOLD
    assert any("FAIL" in r for r in score.rationale)


def test_to_dict_shape():
    score = score_candidate(MINT, _market())
    payload = score.to_dict()
    assert payload["mint"] == MINT
    assert payload["label"] in {"GOOD", "WATCH", "SHILL"}
    assert "total" in payload
    assert "bands" in payload
    assert "rationale" in payload
