"""Detect entry-zone touches and emit de-duplicated alert events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from trading.alerts.zone_watch_state import ZoneWatchStateStore


@dataclass(frozen=True)
class ZoneWatchCandidate:
    key: str
    symbol: str
    side: str
    entry_zone: tuple[float, float]
    invalidation: float
    confidence_score: int
    rr_estimated: float
    setup_status: str


def build_zone_watch_candidates(
    payload: dict[str, Any],
    *,
    min_score: int | None = None,
) -> list[ZoneWatchCandidate]:
    raw_summary = payload.get("summary")
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    threshold = min_score if min_score is not None else int(
        summary.get("effective_score_threshold") or summary.get("score_threshold") or 75
    )

    raw_results = payload.get("results")
    results: dict[str, Any] = raw_results if isinstance(raw_results, dict) else {}
    candidates: list[ZoneWatchCandidate] = []
    for symbol, entry in results.items():
        if not isinstance(entry, dict):
            continue
        plans = entry.get("plans")
        if not isinstance(plans, list):
            continue

        for plan in plans:
            if not isinstance(plan, dict):
                continue
            score = _safe_int(plan.get("confidence_score"))
            if score < threshold:
                continue
            side = str(plan.get("side") or "").lower()
            if side not in {"long", "short"}:
                continue
            zone = plan.get("entry_zone")
            if not isinstance(zone, list) or len(zone) < 2:
                continue
            invalidation_raw = plan.get("invalidation")
            if invalidation_raw is None:
                continue
            try:
                z0 = float(zone[0])
                z1 = float(zone[1])
                invalidation = float(invalidation_raw)
                rr_estimated = float(plan.get("rr_estimated") or 0.0)
            except (TypeError, ValueError):
                continue

            low = min(z0, z1)
            high = max(z0, z1)
            key = f"{symbol}:{side}:{low:.6f}:{high:.6f}:{invalidation:.6f}"
            candidates.append(
                ZoneWatchCandidate(
                    key=key,
                    symbol=str(symbol),
                    side=side,
                    entry_zone=(low, high),
                    invalidation=invalidation,
                    confidence_score=score,
                    rr_estimated=rr_estimated,
                    setup_status=str(plan.get("setup_status") or "unknown"),
                )
            )

    candidates.sort(key=lambda item: (-item.confidence_score, item.symbol, item.side))
    return candidates


class EntryZoneMonitor:
    """Evaluate entry-zone candidates and emit deduplicated touch events."""

    def __init__(self, state: ZoneWatchStateStore | None = None):
        self.state = state or ZoneWatchStateStore()

    def evaluate(
        self,
        candidates: list[ZoneWatchCandidate],
        *,
        price_lookup: Callable[[str], float],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        now_iso = now.isoformat()
        active_keys = {candidate.key for candidate in candidates}

        events: list[dict[str, Any]] = []
        for candidate in candidates:
            price = float(price_lookup(candidate.symbol))
            inside = candidate.entry_zone[0] <= price <= candidate.entry_zone[1]
            invalidated = _is_invalidated(candidate, price)

            current = self.state.get(candidate.key) or {}
            event = {
                "symbol": candidate.symbol,
                "side": candidate.side,
                "entry_zone": [candidate.entry_zone[0], candidate.entry_zone[1]],
                "invalidation": candidate.invalidation,
                "price": price,
                "confidence_score": candidate.confidence_score,
                "rr_estimated": candidate.rr_estimated,
                "setup_status": candidate.setup_status,
                "event_at": now_iso,
            }

            next_state = {
                **current,
                "symbol": candidate.symbol,
                "side": candidate.side,
                "entry_zone": [candidate.entry_zone[0], candidate.entry_zone[1]],
                "invalidation": candidate.invalidation,
                "confidence_score": candidate.confidence_score,
                "rr_estimated": candidate.rr_estimated,
                "setup_status": candidate.setup_status,
                "last_price": price,
                "last_checked_at": now_iso,
                "expired_at": None,
            }

            if inside and not current.get("entry_touched_at"):
                next_state["entry_touched_at"] = now_iso

            if invalidated and not current.get("invalidated_at"):
                next_state["invalidated_at"] = now_iso

            should_alert = bool(inside and not invalidated and not current.get("alert_sent_at"))
            if should_alert:
                next_state["alert_sent_at"] = now_iso
                events.append(event)

            if not current.get("first_seen_at"):
                next_state["first_seen_at"] = now_iso

            self.state.upsert(candidate.key, next_state)

        self.state.mark_missing_as_expired(active_keys, now_iso=now_iso)
        self.state.payload["generated_at"] = now_iso
        self.state.save()

        return {
            "generated_at": now_iso,
            "candidates": len(candidates),
            "alerts": events,
            "alert_count": len(events),
        }


def _is_invalidated(candidate: ZoneWatchCandidate, price: float) -> bool:
    if candidate.side == "long":
        return price <= candidate.invalidation
    return price >= candidate.invalidation


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
