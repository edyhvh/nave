"""Recommendation layer for memecoin scanner candidates.

Composes:
- latest scan candidates
- 24h first-seen/repeat context
- locked sizing policy (0.25R per trade, 5% class cap)

This module intentionally does not provide hold-time or exit guidance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from trading.memecoin.archive import MintHistory, mint_history
from trading.memecoin.scanner import MemecoinCandidate, MemecoinScanner
from trading.memecoin.timing import EntryTiming

BASE_RISK_PCT = 0.01
TRADE_R_MULTIPLIER = 0.25
MEMECOIN_CLASS_CAP_PCT = 0.05


@dataclass
class MemecoinRecommendation:
    mint: str
    symbol: str | None
    enter_now: bool
    entry_timing: EntryTiming
    position_size_usd: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mint": self.mint,
            "symbol": self.symbol,
            "enter_now": self.enter_now,
            "entry_timing": self.entry_timing.value,
            "position_size_usd": round(self.position_size_usd, 2),
            "reason": self.reason,
        }



def _position_size_usd(
    *,
    capital_usd: float,
    memecoin_exposure_usd: float,
) -> float:
    if capital_usd <= 0:
        raise ValueError("capital_usd must be > 0")
    if memecoin_exposure_usd < 0:
        raise ValueError("memecoin_exposure_usd must be >= 0")

    trade_risk_usd = capital_usd * BASE_RISK_PCT * TRADE_R_MULTIPLIER
    class_cap_usd = capital_usd * MEMECOIN_CLASS_CAP_PCT
    class_headroom_usd = max(0.0, class_cap_usd - memecoin_exposure_usd)
    return max(0.0, min(trade_risk_usd, class_headroom_usd))



def _history_for_mint(
    mint: str,
    *,
    history: dict[str, MintHistory],
) -> MintHistory | None:
    return history.get(mint)



def recommend_for_candidate(
    candidate: MemecoinCandidate,
    *,
    capital_usd: float,
    memecoin_exposure_usd: float,
    history: dict[str, MintHistory],
) -> MemecoinRecommendation:
    h = _history_for_mint(candidate.mint, history=history)
    seen_count = h.seen_count if h else 1

    timing = candidate.entry_timing
    if timing is None:
        timing = EntryTiming.MID

    size = _position_size_usd(
        capital_usd=capital_usd,
        memecoin_exposure_usd=memecoin_exposure_usd,
    )

    if timing == EntryTiming.EXTENDED:
        return MemecoinRecommendation(
            mint=candidate.mint,
            symbol=candidate.symbol,
            enter_now=False,
            entry_timing=timing,
            position_size_usd=0.0,
            reason=(
                "skip: entry_timing=EXTENDED (already overextended vs sane chase point)"
            ),
        )

    if not candidate.passed:
        return MemecoinRecommendation(
            mint=candidate.mint,
            symbol=candidate.symbol,
            enter_now=False,
            entry_timing=timing,
            position_size_usd=0.0,
            reason=f"skip: scanner rejected candidate ({candidate.skipped_reason or 'failed checks'})",
        )

    if size <= 0:
        return MemecoinRecommendation(
            mint=candidate.mint,
            symbol=candidate.symbol,
            enter_now=False,
            entry_timing=timing,
            position_size_usd=0.0,
            reason="skip: no class-cap headroom left (5% memecoin cap reached)",
        )

    if timing == EntryTiming.LATE:
        return MemecoinRecommendation(
            mint=candidate.mint,
            symbol=candidate.symbol,
            enter_now=False,
            entry_timing=timing,
            position_size_usd=0.0,
            reason=(
                "skip: entry_timing=LATE; momentum window likely degraded "
                f"(seen_count_24h={seen_count})"
            ),
        )

    return MemecoinRecommendation(
        mint=candidate.mint,
        symbol=candidate.symbol,
        enter_now=True,
        entry_timing=timing,
        position_size_usd=size,
        reason=(
            f"recommend: safety+score passed, entry_timing={timing.value}, "
            f"seen_count_24h={seen_count}, sizing=0.25R capped by 5% class limit"
        ),
    )



def memecoin_recommend_payload(
    *,
    limit: int = 50,
    top_n: int = 10,
    keep_skipped: bool = False,
    history_hours: int = 24,
    capital_usd: float = 10_000.0,
    memecoin_exposure_usd: float = 0.0,
    scanner: MemecoinScanner | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run scan + history and emit per-candidate enter/skip recommendation."""
    now_dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    scanner_obj = scanner or MemecoinScanner()
    candidates = scanner_obj.scan(
        limit=limit,
        top_n=top_n,
        keep_skipped=keep_skipped,
    )

    history = mint_history(hours=history_hours, now=now_dt)
    recommendations = [
        recommend_for_candidate(
            candidate,
            capital_usd=capital_usd,
            memecoin_exposure_usd=memecoin_exposure_usd,
            history=history,
        ).to_dict()
        for candidate in candidates
    ]

    return {
        "tool": "memecoin_recommend",
        "generated_at": now_dt.isoformat(),
        "params": {
            "limit": limit,
            "top_n": top_n,
            "keep_skipped": keep_skipped,
            "history_hours": history_hours,
            "capital_usd": capital_usd,
            "memecoin_exposure_usd": memecoin_exposure_usd,
            "sizing": {
                "base_risk_pct": BASE_RISK_PCT,
                "trade_r_multiplier": TRADE_R_MULTIPLIER,
                "class_cap_pct": MEMECOIN_CLASS_CAP_PCT,
            },
        },
        "count": len(recommendations),
        "recommendations": recommendations,
    }
