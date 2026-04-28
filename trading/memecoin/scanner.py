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
from datetime import datetime, timezone
from typing import Any

from trading.memecoin.archive import mint_history, persist_scan_snapshot
from trading.memecoin.data_provider import (
    MemecoinDataProvider,
    PumpFunClient,
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
from trading.memecoin.timing import EntryTiming, classify_entry_timing

# Re-export sort constants for CLI / MCP layers.
SORT_FRESH = PumpFunClient.SORT_FRESH
SORT_ACTIVE = PumpFunClient.SORT_ACTIVE
SORT_TOP_MCAP = PumpFunClient.SORT_TOP_MCAP

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
    entry_timing: EntryTiming | None = field(default=None)
    seen_count_24h: int = field(default=0)
    first_seen_at: str | None = field(default=None)
    last_seen_at: str | None = field(default=None)

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
            "entry_timing": self.entry_timing.value if self.entry_timing else None,
            "seen_count_24h": self.seen_count_24h,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class MemecoinScanner:
    """Orchestrates the discover → gate → safety → score pipeline."""

    def __init__(
        self,
        provider: Any | None = None,
        *,
        liquidity_floor_usd: float = LIQUIDITY_FLOOR_USD,
    ):
        self.provider = provider or MemecoinDataProvider()
        self.liquidity_floor_usd = liquidity_floor_usd

    def scan(
        self,
        *,
        limit: int = 50,
        sort: str = SORT_ACTIVE,
        keep_skipped: bool = False,
        top_n: int | None = None,
    ) -> list[MemecoinCandidate]:
        """Run a full scan.

        Args:
            limit:        How many recent Pump.fun rows to pull.
            sort:         Pump.fun sort mode. ``SORT_ACTIVE`` (default,
                          ``last_trade_timestamp``) surfaces both fresh
                          and graduated tokens that are currently moving.
                          ``SORT_FRESH`` (``created_timestamp``) returns
                          just-minted tokens — almost all fail the
                          liquidity gate. ``SORT_TOP_MCAP`` rotates the
                          top-mcap rows on Pump.fun's active list.
            keep_skipped: If True, returns liquidity-floor rejections too
                          (with ``passed=False`` and ``skipped_reason``).
                          Useful for observability.
            top_n:        If set, truncates the output to the top-N
                          *passing* candidates by score.
        """
        launches = self.provider.new_launches(limit=limit, sort=sort)
        if not launches:
            logger.info("scanner: no new launches returned by Pump.fun")
            return []

        scanned_at = _now_utc()
        prior_history = mint_history(hours=24, now=scanned_at)
        candidates: list[MemecoinCandidate] = []
        for launch in launches:
            market = self.provider.market(launch.mint)
            prior = prior_history.get(launch.mint)
            seen_count_24h = (prior.seen_count if prior else 0) + 1
            first_seen_at = prior.first_seen_at if prior else _iso(scanned_at)
            last_seen_at = _iso(scanned_at)
            entry_timing = classify_entry_timing(
                market=market,
                seen_count=seen_count_24h,
                first_seen_at=first_seen_at,
                now=scanned_at,
            )
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
                        entry_timing=entry_timing,
                        seen_count_24h=seen_count_24h,
                        first_seen_at=first_seen_at,
                        last_seen_at=last_seen_at,
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
                    entry_timing=entry_timing,
                    seen_count_24h=seen_count_24h,
                    first_seen_at=first_seen_at,
                    last_seen_at=last_seen_at,
                )
            )

        passing = [c for c in candidates if c.passed]
        passing.sort(key=lambda c: c.score.total, reverse=True)
        if top_n is not None:
            passing = passing[:top_n]

        try:
            persist_scan_snapshot(
                candidates=[candidate.to_dict() for candidate in candidates],
                params={
                    "limit": limit,
                    "sort": sort,
                    "keep_skipped": keep_skipped,
                    "top_n": top_n,
                },
                scanned_at=scanned_at,
            )
        except OSError as exc:
            logger.warning("scanner: failed to persist scan archive: %s", exc)

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
        scanned_at = _now_utc()
        prior = mint_history(hours=24, now=scanned_at).get(mint)
        seen_count_24h = (prior.seen_count if prior else 0) + 1
        first_seen_at = prior.first_seen_at if prior else _iso(scanned_at)
        last_seen_at = _iso(scanned_at)
        entry_timing = classify_entry_timing(
            market=market,
            seen_count=seen_count_24h,
            first_seen_at=first_seen_at,
            now=scanned_at,
        )
        liquidity = (market.liquidity_usd if market else None) or 0.0
        skipped = None
        if liquidity < self.liquidity_floor_usd:
            skipped = (
                f"liquidity ${liquidity:,.0f} below floor "
                f"${self.liquidity_floor_usd:,.0f}"
            )
        metadata = self.provider.metadata(mint)
        return MemecoinCandidate(
            mint=mint,
            name=(launch.name if launch else None) or (metadata.name if metadata else None),
            symbol=(launch.symbol if launch else None),
            market=market,
            safety=safety,
            score=score,
            discovered_via="manual",
            launch=launch,
            skipped_reason=skipped,
            entry_timing=entry_timing,
            seen_count_24h=seen_count_24h,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
        )

    # ── Internals ----------------------------------------------------

    def _rejected_candidate(
        self,
        *,
        launch: PumpFunLaunch,
        market: TokenMarket | None,
        reason: str,
        entry_timing: EntryTiming,
        seen_count_24h: int,
        first_seen_at: str,
        last_seen_at: str,
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
            entry_timing=entry_timing,
            seen_count_24h=seen_count_24h,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
        )
