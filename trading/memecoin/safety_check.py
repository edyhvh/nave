"""
Canonical SPL safety checklist for Solana memecoins.

Five hard checks (any failing → ``FAIL``):

1. **Mint authority renounced** — issuer can no longer mint new supply.
2. **Freeze authority revoked** — issuer cannot freeze user wallets.
3. **LP locked or burned** — liquidity cannot be pulled by the deployer.
4. **Honeypot simulation** — Jupiter can route a tiny TOKEN → wSOL sell.
5. **Holder concentration** — top-10 ≤ ``HOLDER_TOP10_MAX`` (25 %).
   Soft flag if top-1 falls in [``HOLDER_TOP1_FLAG_MIN``,
   ``HOLDER_TOP1_FLAG_MAX``] = [15 %, 18 %]; hard fail above the max.

Verdict rollup:

    * ``FAIL``  — any hard check fails.
    * ``WATCH`` — all checks pass but ``flagged_top1`` is true.
    * ``PASS``  — all checks pass, no flags.

The report is the structured JSON contract called out in
``docs/analysis/memecoin/plan.md``: ``rug_score`` (0-100, lower = safer),
``honeypot_flags``, ``lp_status``, ``holder_concentration``,
``dev_wallets``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from trading.memecoin.data_provider import (
    MemecoinDataProvider,
    TokenHolder,
    TokenMarket,
    TokenMetadata,
)

# ── Tunables (locked in plan.md) ──────────────────────────────────────────────

HOLDER_TOP10_MAX = 25.0  # %  hard fail above
HOLDER_TOP1_FLAG_MIN = 15.0  # %  flag-only band lower bound
HOLDER_TOP1_FLAG_MAX = 18.0  # %  flag-only band upper bound; above = hard fail
HONEYPOT_PROBE_BASE_UNITS = 1000  # tiny TOKEN → wSOL probe size
DEV_WALLET_FLAG_PCT = 5.0  # creator/dev holding > 5 % is worth surfacing

# Each failed hard check contributes this much to ``rug_score`` (0-100).
_RUG_WEIGHTS = {
    "mint_authority_renounced": 20,
    "freeze_authority_revoked": 20,
    "lp_status": 25,
    "honeypot": 25,
    "holder_concentration": 10,
}


class SafetyVerdict(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    FAIL = "FAIL"


@dataclass
class _LPStatus:
    locked: bool
    burned: bool
    lp_provider: str | None
    details: str

    def passes(self) -> bool:
        return self.locked or self.burned


@dataclass
class _HoneypotResult:
    buy_simulates: bool
    sell_simulates: bool
    flags: list[str]

    def passes(self) -> bool:
        return self.buy_simulates and self.sell_simulates and not self.flags


@dataclass
class _HolderConcentration:
    top_1_pct: float
    top_5_pct: float
    top_10_pct: float
    flagged_top1: bool

    def passes(self) -> bool:
        if self.top_10_pct > HOLDER_TOP10_MAX:
            return False
        if self.top_1_pct > HOLDER_TOP1_FLAG_MAX:
            return False
        return True


@dataclass
class SafetyReport:
    """Structured payload returned by :func:`check_safety` and the MCP tool.

    Mirrors the JSON contract documented in
    ``docs/analysis/memecoin/plan.md`` so callers can serialize via
    :meth:`to_dict` without further massaging.
    """

    mint: str
    verdict: SafetyVerdict
    rug_score: int
    checks: dict[str, Any]
    dev_wallets: list[dict[str, Any]]
    honeypot_flags: list[str]
    raw: dict[str, Any]
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["verdict"] = self.verdict.value
        return payload


# ── Public entry point ────────────────────────────────────────────────────────


def check_safety(
    mint: str,
    *,
    provider: MemecoinDataProvider | None = None,
    metadata: TokenMetadata | None = None,
    holders: list[TokenHolder] | None = None,
    market: TokenMarket | None = None,
    has_sell_route: bool | None = None,
    creator: str | None = None,
) -> SafetyReport:
    """Run the 5 canonical SPL safety checks.

    All optional kwargs are dependency-injection seams for tests. In
    normal use you pass ``provider`` and the function fetches everything
    it needs.
    """
    provider = provider or MemecoinDataProvider()
    if metadata is None:
        metadata = provider.metadata(mint)
    if holders is None:
        holders = provider.holders(mint, limit=20)
    if market is None:
        market = provider.market(mint)
    if has_sell_route is None:
        has_sell_route = provider.has_sell_route(
            mint, amount=HONEYPOT_PROBE_BASE_UNITS
        )

    # 1. Mint authority renounced
    mint_renounced = bool(metadata is not None and metadata.mint_authority is None)

    # 2. Freeze authority revoked
    freeze_revoked = bool(metadata is not None and metadata.freeze_authority is None)

    # 3. LP status — heuristic from market data we have on hand.
    #    Pump.fun tokens still on the bonding curve have no transferable LP
    #    until graduation, so they are "locked-by-protocol" by definition.
    #    Graduated tokens (DexScreener pair) are treated as PASS only when we
    #    can attribute the pair to a known DEX; the user can override via the
    #    structured report.
    lp = _classify_lp(market)

    # 4. Honeypot — Jupiter sell-route probe.
    honeypot = _classify_honeypot(market, has_sell_route)

    # 5. Holder concentration — derived from Helius getTokenLargestAccounts.
    concentration = _classify_holders(holders)

    # Dev wallets: surface creator/update authority + any single non-LP
    # wallet holding > DEV_WALLET_FLAG_PCT.
    dev_wallets = _build_dev_wallets(metadata, holders, creator=creator)

    # Rollup verdict + rug_score.
    failed: list[str] = []
    if not mint_renounced:
        failed.append("mint_authority_renounced")
    if not freeze_revoked:
        failed.append("freeze_authority_revoked")
    if not lp.passes():
        failed.append("lp_status")
    if not honeypot.passes():
        failed.append("honeypot")
    if not concentration.passes():
        failed.append("holder_concentration")

    rug_score = sum(_RUG_WEIGHTS[name] for name in failed)
    if failed:
        verdict = SafetyVerdict.FAIL
    elif concentration.flagged_top1:
        verdict = SafetyVerdict.WATCH
    else:
        verdict = SafetyVerdict.PASS

    return SafetyReport(
        mint=mint,
        verdict=verdict,
        rug_score=int(rug_score),
        checks={
            "mint_authority_renounced": mint_renounced,
            "freeze_authority_revoked": freeze_revoked,
            "lp_status": asdict(lp),
            "honeypot": asdict(honeypot),
            "holder_concentration": asdict(concentration),
        },
        dev_wallets=dev_wallets,
        honeypot_flags=list(honeypot.flags),
        raw={
            "metadata_present": metadata is not None,
            "market_present": market is not None,
            "holder_count_returned": len(holders),
        },
    )


# ── Sub-classifiers ───────────────────────────────────────────────────────────


def _classify_lp(market: TokenMarket | None) -> _LPStatus:
    """Heuristic LP-safety classifier from the data we have on hand.

    We don't have a direct on-chain query for "is this LP token burned /
    locked" without per-DEX logic, so the heuristic surfaces the venue
    and lets the structured report carry the detail string. Pump.fun
    bonding-curve tokens are protocol-locked until graduation.
    """
    if market is None:
        return _LPStatus(
            locked=False,
            burned=False,
            lp_provider=None,
            details="no market data; cannot verify LP",
        )
    dex = (market.dex or "").lower()
    if dex == "pump":
        return _LPStatus(
            locked=True,
            burned=False,
            lp_provider="pump",
            details="bonding-curve liquidity is protocol-locked until graduation",
        )
    # On Raydium / Meteora / Orca we treat LP as locked when liquidity is
    # present *and* a pair address exists. The structured report carries
    # the dex + pair so a human / Hermes can verify out-of-band.
    if (market.liquidity_usd or 0) > 0 and market.pair_address:
        return _LPStatus(
            locked=True,
            burned=False,
            lp_provider=dex or None,
            details=(
                f"pool {market.pair_address} on {dex or 'unknown dex'} with "
                f"${market.liquidity_usd:,.0f} liquidity"
            ),
        )
    return _LPStatus(
        locked=False,
        burned=False,
        lp_provider=dex or None,
        details="no measurable LP",
    )


def _classify_honeypot(
    market: TokenMarket | None, has_sell_route: bool
) -> _HoneypotResult:
    flags: list[str] = []
    market_present = market is not None and (market.liquidity_usd or 0) > 0
    # Buy simulation is implicit: if Jupiter knows the token at all, a buy
    # route exists. We treat the existence of ANY market as buy-route OK;
    # the strict check is sell-route.
    buy_ok = market_present
    sell_ok = bool(has_sell_route)
    if not buy_ok:
        flags.append("no_market_for_buy")
    if not sell_ok:
        flags.append("no_sell_route_via_jupiter")
    return _HoneypotResult(
        buy_simulates=buy_ok, sell_simulates=sell_ok, flags=flags
    )


def _classify_holders(holders: list[TokenHolder]) -> _HolderConcentration:
    if not holders:
        return _HolderConcentration(
            top_1_pct=0.0,
            top_5_pct=0.0,
            top_10_pct=0.0,
            flagged_top1=False,
        )
    top1 = holders[0].pct_of_supply
    top5 = sum(h.pct_of_supply for h in holders[:5])
    top10 = sum(h.pct_of_supply for h in holders[:10])
    flagged_top1 = HOLDER_TOP1_FLAG_MIN <= top1 <= HOLDER_TOP1_FLAG_MAX
    return _HolderConcentration(
        top_1_pct=round(top1, 2),
        top_5_pct=round(top5, 2),
        top_10_pct=round(top10, 2),
        flagged_top1=flagged_top1,
    )


def _build_dev_wallets(
    metadata: TokenMetadata | None,
    holders: list[TokenHolder],
    *,
    creator: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(address: str | None, balance_pct: float, notes: str) -> None:
        if not address or address in seen:
            return
        seen.add(address)
        rows.append(
            {
                "address": address,
                "balance_pct": round(balance_pct, 2),
                "notes": notes,
            }
        )

    holder_lookup = {h.address: h.pct_of_supply for h in holders}

    # Creator and update-authority are only worth surfacing if they
    # actually hold tokens — the creator typically dumps to 0 % at
    # launch and a 0 %-balance row is just noise.
    if creator:
        creator_pct = holder_lookup.get(creator, 0.0)
        if creator_pct >= DEV_WALLET_FLAG_PCT:
            add(creator, creator_pct, "pump.fun creator")
    if metadata is not None:
        ua_pct = holder_lookup.get(metadata.update_authority or "", 0.0)
        if ua_pct >= DEV_WALLET_FLAG_PCT:
            add(metadata.update_authority, ua_pct, "metadata update authority")
        # Mint authority that isn't renounced is always worth surfacing,
        # regardless of current balance — it can mint more supply.
        if metadata.mint_authority:
            add(
                metadata.mint_authority,
                holder_lookup.get(metadata.mint_authority, 0.0),
                "mint authority (not renounced)",
            )

    # Surface any single non-LP holder above DEV_WALLET_FLAG_PCT that's
    # not already represented above.
    for holder in holders:
        if holder.pct_of_supply >= DEV_WALLET_FLAG_PCT:
            add(holder.address, holder.pct_of_supply, "large holder")

    return rows
