"""
End-to-end memecoin discovery pipeline.

Steps:
    1. Pull the last N new launches from Pump.fun.
    2. Drop everything below ``LIQUIDITY_FLOOR_USD`` ($25k).
    3. Run the canonical SPL safety check on each survivor.
    4. Score the survivors with the transparent rubric.
    5. Return a ranked list of :class:`MemecoinCandidate`, sorted by total
       score descending. Each candidate carries the full safety report
       and score breakdown so the caller can render or persist them.

Read-only: nothing here mutates wallets or places orders. The structured
payload is what the MCP tools and CLI consume.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from trading.memecoin.data_provider import (
    MemecoinDataProvider,
    PumpFunLaunch,
    TokenMarket,
)
from trading.memecoin.safety_check import SafetyReport, SafetyVerdict, check_safety
from trading.memecoin.scoring import (
    LIQUIDITY_FLOOR_USD,
    Label,
    ScoreBreakdown,
    score_candidate,
)

logger = logging.getLogger(__name__)


@dataclass
class MemecoinCandidate:
    mint: str
    name: str | None
    symbol: str | None
    market: TokenMarket | None
    safety: SafetyReport
    score: ScoreBreakdown
    discovered_via: str  # e.g. "pumpfun_new_launches"
    launch: PumpFunLaunch | None = None
    skipped_reason: str | None = field(default=None)

    @property
    def passed(self) -> bool:
        return (
            self.safety.verdict in {SafetyVerdict.PASS, SafetyVerdict.WATCH}
            and self.score.label != Label.SHILL
            and self.skipped_reason is None
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mint": self.mint,
            "name": self.name,
            "symbol": self.symbol,
            "discovered_via": self.discovered_via,
            "passed": self.passed,
            "skipped_reason": self.skipped_reason,
            "score": self.score.to_dict(),
            "safety": self.safety.to_dict(),
            "market": _market_to_dict(self.market),
        }


def _market_to_dict(market: TokenMarket | None) -> dict[str, Any] | None:
    if market is None:
        return None
    return {
        "price_usd": market.price_usd,
        "liquidity_usd": market.liquidity_usd,
        "fdv_usd": market.fdv_usd,
        "market_cap_usd": market.market_cap_usd,
        "volume_24h_usd": market.volume_24h_usd,
        "dex": market.dex,
        "pair_address": market.pair_address,
        "age_minutes": market.age_minutes,
        "price_change_5m_pct": market.price_change_5m_pct,
        "price_change_1h_pct": market.price_change_1h_pct,
    }


class MemecoinScanner:
    """Orchestrates the discover → gate → safety → score pipeline."""

    def __init__(
        self,
        provider: MemecoinDataProvider | None = None,
        *,
        liquidity_floor_usd: float = LIQUIDITY_FLOOR_USD,
    ):
        self.provider = provider or MemecoinDataProvider()
        self.liquidity_floor_usd = liquidity_floor_usd

    def scan(
        self,
        *,
        limit: int = 50,
        keep_skipped: bool = False,
        top_n: int | None = None,
    ) -> list[MemecoinCandidate]:
        """Run a full scan.

        Args:
            limit:        How many recent Pump.fun launches to pull.
            keep_skipped: If True, returns liquidity-floor rejections too
                          (with ``passed=False`` and ``skipped_reason``).
                          Useful for observability.
            top_n:        If set, truncates the output to the top-N
                          *passing* candidates by score.
        """
        launches = self.provider.new_launches(limit=limit)
        if not launches:
            logger.info("scanner: no new launches returned by Pump.fun")
            return []

        candidates: list[MemecoinCandidate] = []
        for launch in launches:
            market = self.provider.market(launch.mint)
            liquidity = (market.liquidity_usd if market else None) or (
                launch.liquidity_usd or 0.0
            )
            if liquidity < self.liquidity_floor_usd:
                if not keep_skipped:
                    continue
                # Build a placeholder safety/score for surfaced rejects so
                # the caller has a uniform shape. We don't pay for the
                # full safety probes since we already know they're out.
                candidates.append(
                    self._rejected_candidate(
                        launch=launch,
                        market=market,
                        reason=(
                            f"liquidity ${liquidity:,.0f} below floor "
                            f"${self.liquidity_floor_usd:,.0f}"
                        ),
                    )
                )
                continue

            safety = check_safety(
                launch.mint,
                provider=self.provider,
                market=market,
                creator=launch.creator,
            )
            score = score_candidate(launch.mint, market, safety=safety)
            candidates.append(
                MemecoinCandidate(
                    mint=launch.mint,
                    name=launch.name,
                    symbol=launch.symbol,
                    market=market,
                    safety=safety,
                    score=score,
                    discovered_via="pumpfun_new_launches",
                    launch=launch,
                )
            )

        passing = [c for c in candidates if c.passed]
        passing.sort(key=lambda c: c.score.total, reverse=True)
        if top_n is not None:
            passing = passing[:top_n]

        if keep_skipped:
            non_passing = [c for c in candidates if not c.passed]
            return passing + non_passing
        return passing

    def check(self, mint: str) -> MemecoinCandidate:
        """Single-token check. Useful for ``nave memecoin check <mint>``."""
        launch = self.provider.pumpfun.get_launch(mint)
        market = self.provider.market(mint)
        safety = check_safety(
            mint,
            provider=self.provider,
            market=market,
            creator=launch.creator if launch else None,
        )
        score = score_candidate(mint, market, safety=safety)
        liquidity = (market.liquidity_usd if market else None) or 0.0
        skipped = None
        if liquidity < self.liquidity_floor_usd:
            skipped = (
                f"liquidity ${liquidity:,.0f} below floor "
                f"${self.liquidity_floor_usd:,.0f}"
            )
        return MemecoinCandidate(
            mint=mint,
            name=(launch.name if launch else None) or (
                self.provider.metadata(mint).name
                if self.provider.metadata(mint)
                else None
            ),
            symbol=(launch.symbol if launch else None),
            market=market,
            safety=safety,
            score=score,
            discovered_via="manual",
            launch=launch,
            skipped_reason=skipped,
        )

    # ── Internals ----------------------------------------------------

    def _rejected_candidate(
        self,
        *,
        launch: PumpFunLaunch,
        market: TokenMarket | None,
        reason: str,
    ) -> MemecoinCandidate:
        # Synthesize an empty SafetyReport / ScoreBreakdown so the shape
        # is uniform without paying for real probes on a rejected token.
        safety = SafetyReport(
            mint=launch.mint,
            verdict=SafetyVerdict.FAIL,
            rug_score=0,
            checks={},
            dev_wallets=[],
            honeypot_flags=[],
            raw={"reason": reason},
        )
        score = ScoreBreakdown(
            mint=launch.mint,
            total=0,
            label=Label.SHILL,
            bands={},
            rationale=[reason],
        )
        return MemecoinCandidate(
            mint=launch.mint,
            name=launch.name,
            symbol=launch.symbol,
            market=market,
            safety=safety,
            score=score,
            discovered_via="pumpfun_new_launches",
            launch=launch,
            skipped_reason=reason,
        )
