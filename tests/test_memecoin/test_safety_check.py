"""Unit tests for the canonical SPL safety checklist."""

from __future__ import annotations

from trading.memecoin.data_provider import (
    PumpFunLaunch,
    TokenHolder,
    TokenMarket,
    TokenMetadata,
)
from trading.memecoin.safety_check import (
    HOLDER_TOP10_MAX,
    HOLDER_TOP1_FLAG_MAX,
    HOLDER_TOP1_FLAG_MIN,
    SafetyVerdict,
    check_safety,
)

CLEAN_MINT = "CleanMintAddress11111111111111111111111111111"


def _make_metadata(*, mint_authority: str | None, freeze_authority: str | None) -> TokenMetadata:
    return TokenMetadata(
        mint=CLEAN_MINT,
        name="Clean",
        symbol="CLN",
        decimals=6,
        supply=1_000_000_000.0,
        mint_authority=mint_authority,
        freeze_authority=freeze_authority,
        update_authority="UpdateAuthorityAddr",
    )


def _make_market(*, dex: str = "raydium", liquidity_usd: float = 75_000.0) -> TokenMarket:
    return TokenMarket(
        mint=CLEAN_MINT,
        price_usd=0.0001,
        liquidity_usd=liquidity_usd,
        fdv_usd=500_000.0,
        market_cap_usd=500_000.0,
        volume_24h_usd=200_000.0,
        pair_address="PairAddr",
        dex=dex,
        age_minutes=120,
    )


def _holders(top1: float, others: list[float]) -> list[TokenHolder]:
    pcts = [top1] + others
    return [TokenHolder(address=f"H{i}", amount=pct, pct_of_supply=pct) for i, pct in enumerate(pcts)]


def test_clean_token_passes_all_checks():
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority=None, freeze_authority=None),
        holders=_holders(8.0, [4.0, 3.0, 2.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0]),
        market=_make_market(),
        has_sell_route=True,
    )
    assert report.verdict == SafetyVerdict.PASS
    assert report.rug_score == 0
    assert report.checks["mint_authority_renounced"] is True
    assert report.checks["freeze_authority_revoked"] is True
    assert report.checks["lp_status"]["locked"] is True
    assert report.checks["honeypot"]["sell_simulates"] is True
    assert report.checks["holder_concentration"]["top_10_pct"] <= HOLDER_TOP10_MAX


def test_unrenounced_mint_authority_fails():
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority="DeployerStillHasMint", freeze_authority=None),
        holders=_holders(8.0, [4.0]),
        market=_make_market(),
        has_sell_route=True,
    )
    assert report.verdict == SafetyVerdict.FAIL
    assert report.checks["mint_authority_renounced"] is False
    assert report.rug_score >= 20


def test_freeze_authority_present_fails():
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority=None, freeze_authority="FreezeAuthority"),
        holders=_holders(5.0, [3.0]),
        market=_make_market(),
        has_sell_route=True,
    )
    assert report.verdict == SafetyVerdict.FAIL
    assert report.checks["freeze_authority_revoked"] is False


def test_no_sell_route_flags_honeypot():
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority=None, freeze_authority=None),
        holders=_holders(5.0, [3.0]),
        market=_make_market(),
        has_sell_route=False,
    )
    assert report.verdict == SafetyVerdict.FAIL
    assert "no_sell_route_via_jupiter" in report.honeypot_flags
    assert report.checks["honeypot"]["sell_simulates"] is False


def test_lp_status_pass_for_pumpfun_bonding_curve():
    market = _make_market(dex="pump", liquidity_usd=30_000.0)
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority=None, freeze_authority=None),
        holders=_holders(5.0, [3.0]),
        market=market,
        has_sell_route=True,
    )
    lp = report.checks["lp_status"]
    assert lp["locked"] is True
    assert lp["lp_provider"] == "pump"


def test_top10_above_25pct_hard_fails():
    # Top-10 sum > 25% even though top-1 is benign.
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority=None, freeze_authority=None),
        holders=_holders(4.0, [4.0, 4.0, 4.0, 4.0, 4.0, 1.0, 1.0, 1.0, 1.0]),
        market=_make_market(),
        has_sell_route=True,
    )
    assert report.verdict == SafetyVerdict.FAIL
    assert report.checks["holder_concentration"]["top_10_pct"] > HOLDER_TOP10_MAX


def test_top1_in_flag_band_yields_watch_not_fail():
    # Top-1 inside [15, 18] band, top-10 below max → WATCH.
    pcts_after = [1.0] * 9  # remaining 9 each holding 1%
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority=None, freeze_authority=None),
        holders=_holders(HOLDER_TOP1_FLAG_MIN + 0.5, pcts_after),
        market=_make_market(),
        has_sell_route=True,
    )
    assert report.verdict == SafetyVerdict.WATCH
    assert report.checks["holder_concentration"]["flagged_top1"] is True
    assert report.rug_score == 0  # flag-only, no hard fail


def test_top1_above_flag_band_hard_fails():
    pcts_after = [0.5] * 9
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority=None, freeze_authority=None),
        holders=_holders(HOLDER_TOP1_FLAG_MAX + 1.0, pcts_after),
        market=_make_market(),
        has_sell_route=True,
    )
    assert report.verdict == SafetyVerdict.FAIL


def test_dev_wallets_surface_creator_and_large_holders():
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority=None, freeze_authority=None),
        holders=[
            TokenHolder(address="LargeHolder1", amount=8.0, pct_of_supply=8.0),
            TokenHolder(address="DevWallet", amount=6.0, pct_of_supply=6.0),
        ],
        market=_make_market(),
        has_sell_route=True,
        creator="DevWallet",
    )
    addresses = {row["address"] for row in report.dev_wallets}
    assert "DevWallet" in addresses
    assert "LargeHolder1" in addresses
    # Creator note must be set
    notes = {row["address"]: row["notes"] for row in report.dev_wallets}
    assert notes["DevWallet"] == "pump.fun creator"


def test_dev_wallets_skip_zero_balance_creator():
    """Creator with 0 % current balance is noise — drop it."""
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority=None, freeze_authority=None),
        holders=[
            TokenHolder(address="WhaleX", amount=7.0, pct_of_supply=7.0),
        ],
        market=_make_market(),
        has_sell_route=True,
        creator="DevWalletWhoDumpedAtLaunch",
    )
    addresses = {row["address"] for row in report.dev_wallets}
    assert "DevWalletWhoDumpedAtLaunch" not in addresses
    assert "WhaleX" in addresses


def test_unrenounced_mint_authority_always_surfaces_in_dev_wallets():
    """A live mint authority is always worth flagging, even with 0 % balance."""
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(
            mint_authority="MintAuthorityStillLive", freeze_authority=None
        ),
        holders=[TokenHolder(address="OtherHolder", amount=2.0, pct_of_supply=2.0)],
        market=_make_market(),
        has_sell_route=True,
    )
    addresses = {row["address"] for row in report.dev_wallets}
    assert "MintAuthorityStillLive" in addresses
    notes = {row["address"]: row["notes"] for row in report.dev_wallets}
    assert "mint authority" in notes["MintAuthorityStillLive"].lower()


def test_report_to_dict_matches_documented_contract():
    report = check_safety(
        CLEAN_MINT,
        metadata=_make_metadata(mint_authority=None, freeze_authority=None),
        holders=_holders(5.0, [3.0]),
        market=_make_market(),
        has_sell_route=True,
    )
    payload = report.to_dict()
    expected_keys = {
        "mint",
        "verdict",
        "rug_score",
        "checks",
        "dev_wallets",
        "honeypot_flags",
        "raw",
        "fetched_at",
    }
    assert expected_keys.issubset(payload.keys())
    assert payload["verdict"] in {"PASS", "WATCH", "FAIL"}
    expected_check_keys = {
        "mint_authority_renounced",
        "freeze_authority_revoked",
        "lp_status",
        "honeypot",
        "holder_concentration",
    }
    assert expected_check_keys.issubset(payload["checks"].keys())


def test_pumpfun_launch_dataclass_round_trip():
    """Sanity: PumpFunLaunch dataclass survives reconstruction from cache dict."""
    launch = PumpFunLaunch(
        mint=CLEAN_MINT,
        name="Clean",
        symbol="CLN",
        creator="Dev",
        created_at="2026-04-27T00:00:00Z",
        bonding_curve_progress=42.0,
        market_cap_usd=300_000.0,
        liquidity_usd=40_000.0,
    )
    rebuilt = PumpFunLaunch(**{
        "mint": launch.mint,
        "name": launch.name,
        "symbol": launch.symbol,
        "creator": launch.creator,
        "created_at": launch.created_at,
        "bonding_curve_progress": launch.bonding_curve_progress,
        "market_cap_usd": launch.market_cap_usd,
        "liquidity_usd": launch.liquidity_usd,
    })
    assert rebuilt.mint == CLEAN_MINT
