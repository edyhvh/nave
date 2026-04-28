"""Pipeline tests for MemecoinScanner with a fake provider."""

from __future__ import annotations

from dataclasses import dataclass, field

from trading.memecoin.data_provider import (
    PumpFunLaunch,
    TokenHolder,
    TokenMarket,
    TokenMetadata,
)
from trading.memecoin.safety_check import SafetyVerdict
from trading.memecoin.scanner import MemecoinScanner
from trading.memecoin.scoring import Label


@dataclass
class _FakePumpFun:
    launches: list[PumpFunLaunch]

    def list_new_launches(
        self, limit: int = 50, *, sort: str = "last_trade_timestamp"
    ) -> list[PumpFunLaunch]:
        return self.launches[:limit]

    def get_launch(self, mint: str) -> PumpFunLaunch | None:
        return next((lx for lx in self.launches if lx.mint == mint), None)


@dataclass
class _FakeProvider:
    """Stand-in for MemecoinDataProvider — same surface, no network."""

    launches: list[PumpFunLaunch]
    metadata_by_mint: dict[str, TokenMetadata]
    holders_by_mint: dict[str, list[TokenHolder]]
    markets_by_mint: dict[str, TokenMarket]
    sell_route_ok: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self):
        self.pumpfun = _FakePumpFun(self.launches)

    def metadata(self, mint: str) -> TokenMetadata | None:
        return self.metadata_by_mint.get(mint)

    def holders(self, mint: str, limit: int = 20) -> list[TokenHolder]:
        return self.holders_by_mint.get(mint, [])[:limit]

    def market(self, mint: str) -> TokenMarket | None:
        return self.markets_by_mint.get(mint)

    def new_launches(
        self, limit: int = 50, *, sort: str = "last_trade_timestamp"
    ) -> list[PumpFunLaunch]:
        return self.launches[:limit]

    def has_sell_route(self, mint: str, *, amount: int = 1000) -> bool:
        return self.sell_route_ok.get(mint, True)


def _holders(top1: float, n_extra: int = 5) -> list[TokenHolder]:
    extras = [
        TokenHolder(address=f"H{i}", amount=1.0, pct_of_supply=1.0)
        for i in range(n_extra)
    ]
    head = TokenHolder(address="H0", amount=top1, pct_of_supply=top1)
    return [head] + extras


def _market(mint: str, *, liquidity: float = 80_000.0, fdv: float = 1_200_000.0) -> TokenMarket:
    return TokenMarket(
        mint=mint,
        price_usd=0.001,
        liquidity_usd=liquidity,
        fdv_usd=fdv,
        market_cap_usd=fdv,
        volume_24h_usd=fdv * 0.5,
        pair_address="Pair",
        dex="raydium",
        age_minutes=180,
        price_change_5m_pct=8.0,
        price_change_1h_pct=18.0,
    )


def _metadata(mint: str) -> TokenMetadata:
    return TokenMetadata(
        mint=mint,
        name=mint[:6],
        symbol=mint[:3],
        decimals=6,
        supply=1_000_000_000.0,
        mint_authority=None,
        freeze_authority=None,
        update_authority="UpdateAuth",
    )


def test_scanner_passes_clean_token_and_drops_rug():
    clean = "CleanMint1111111111111111111111111111111111"
    rug = "RugMint11111111111111111111111111111111111111"

    launches = [
        PumpFunLaunch(
            mint=clean,
            name="Clean",
            symbol="CLN",
            creator="Dev1",
            created_at="2026-04-27T00:00:00Z",
            bonding_curve_progress=100.0,
            market_cap_usd=1_200_000.0,
            liquidity_usd=80_000.0,
        ),
        PumpFunLaunch(
            mint=rug,
            name="Rug",
            symbol="RUG",
            creator="Dev2",
            created_at="2026-04-27T00:00:00Z",
            bonding_curve_progress=100.0,
            market_cap_usd=1_200_000.0,
            liquidity_usd=80_000.0,
        ),
    ]
    provider = _FakeProvider(
        launches=launches,
        metadata_by_mint={
            clean: _metadata(clean),
            # Rug still has mint authority → safety FAIL
            rug: TokenMetadata(
                mint=rug,
                name="Rug",
                symbol="RUG",
                decimals=6,
                supply=1_000_000_000.0,
                mint_authority="DevStillHasMint",
                freeze_authority=None,
                update_authority="UpdateAuth",
            ),
        },
        holders_by_mint={
            clean: _holders(8.0),
            rug: _holders(8.0),
        },
        markets_by_mint={
            clean: _market(clean),
            rug: _market(rug),
        },
        sell_route_ok={clean: True, rug: True},
    )

    scanner = MemecoinScanner(provider=provider)
    candidates = scanner.scan(limit=10, top_n=10)

    assert len(candidates) == 1
    assert candidates[0].mint == clean
    assert candidates[0].safety.verdict == SafetyVerdict.PASS
    assert candidates[0].score.label != Label.SHILL
    assert candidates[0].passed is True


def test_scanner_drops_below_liquidity_floor():
    low_liq = "LowLiqMint11111111111111111111111111111111111"
    launches = [
        PumpFunLaunch(
            mint=low_liq,
            name="Lo",
            symbol="LO",
            creator="Dev",
            created_at="2026-04-27T00:00:00Z",
            bonding_curve_progress=100.0,
            market_cap_usd=200_000.0,
            liquidity_usd=10_000.0,
        ),
    ]
    provider = _FakeProvider(
        launches=launches,
        metadata_by_mint={low_liq: _metadata(low_liq)},
        holders_by_mint={low_liq: _holders(8.0)},
        markets_by_mint={
            low_liq: _market(low_liq, liquidity=10_000.0),
        },
        sell_route_ok={low_liq: True},
    )
    scanner = MemecoinScanner(provider=provider)
    passing = scanner.scan(limit=10, top_n=10)
    assert passing == []  # filtered out by liquidity gate


def test_scanner_keep_skipped_surfaces_rejects():
    low_liq = "LowLiqMint11111111111111111111111111111111111"
    launches = [
        PumpFunLaunch(
            mint=low_liq,
            name="Lo",
            symbol="LO",
            creator="Dev",
            created_at="2026-04-27T00:00:00Z",
            bonding_curve_progress=100.0,
            market_cap_usd=200_000.0,
            liquidity_usd=10_000.0,
        ),
    ]
    provider = _FakeProvider(
        launches=launches,
        metadata_by_mint={low_liq: _metadata(low_liq)},
        holders_by_mint={low_liq: _holders(8.0)},
        markets_by_mint={low_liq: _market(low_liq, liquidity=10_000.0)},
        sell_route_ok={low_liq: True},
    )
    scanner = MemecoinScanner(provider=provider)
    all_seen = scanner.scan(limit=10, top_n=10, keep_skipped=True)
    assert len(all_seen) == 1
    only = all_seen[0]
    assert only.passed is False
    assert "below floor" in (only.skipped_reason or "")


def test_scanner_check_single_mint_returns_full_candidate():
    mint = "CheckMint1111111111111111111111111111111111"
    launches = [
        PumpFunLaunch(
            mint=mint,
            name="Check",
            symbol="CHK",
            creator="Dev",
            created_at="2026-04-27T00:00:00Z",
            bonding_curve_progress=100.0,
            market_cap_usd=900_000.0,
            liquidity_usd=60_000.0,
        ),
    ]
    provider = _FakeProvider(
        launches=launches,
        metadata_by_mint={mint: _metadata(mint)},
        holders_by_mint={mint: _holders(7.0)},
        markets_by_mint={mint: _market(mint)},
        sell_route_ok={mint: True},
    )
    scanner = MemecoinScanner(provider=provider)
    cand = scanner.check(mint)
    assert cand.mint == mint
    assert cand.discovered_via == "manual"
    payload = cand.to_dict()
    assert payload["safety"]["verdict"] in {"PASS", "WATCH"}
    assert payload["score"]["label"] in {"GOOD", "WATCH", "SHILL"}
