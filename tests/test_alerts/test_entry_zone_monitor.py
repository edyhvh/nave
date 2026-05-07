from __future__ import annotations

from datetime import datetime, timezone

from trading.alerts.entry_zone_monitor import (
    EntryZoneMonitor,
    build_zone_watch_candidates,
)
from trading.alerts.zone_watch_state import ZoneWatchStateStore


def _scan_payload() -> dict:
    return {
        "summary": {"effective_score_threshold": 75},
        "results": {
            "BTCUSDT": {
                "plans": [
                    {
                        "side": "long",
                        "confidence_score": 84,
                        "entry_zone": [81112.86, 82479.0],
                        "invalidation": 81052.5,
                        "rr_estimated": 4.63,
                        "setup_status": "pending",
                    },
                    {
                        "side": "short",
                        "confidence_score": 36,
                        "entry_zone": [77530.75, 78781.25],
                        "invalidation": 84146.94,
                        "rr_estimated": 2.81,
                        "setup_status": "invalid",
                    },
                ]
            }
        },
    }


def test_build_zone_watch_candidates_filters_by_score() -> None:
    candidates = build_zone_watch_candidates(_scan_payload())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.symbol == "BTCUSDT"
    assert candidate.side == "long"
    assert candidate.confidence_score == 84


def test_entry_zone_monitor_alerts_once_per_zone(tmp_path) -> None:
    state = ZoneWatchStateStore(path=tmp_path / "state.json")
    monitor = EntryZoneMonitor(state)
    candidates = build_zone_watch_candidates(_scan_payload())
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)

    first = monitor.evaluate(
        candidates,
        price_lookup=lambda symbol: 82000.0,
        now=now,
    )
    second = monitor.evaluate(
        candidates,
        price_lookup=lambda symbol: 82100.0,
        now=now,
    )

    assert first["alert_count"] == 1
    assert second["alert_count"] == 0


def test_entry_zone_monitor_skips_alert_when_invalidated(tmp_path) -> None:
    state = ZoneWatchStateStore(path=tmp_path / "state.json")
    monitor = EntryZoneMonitor(state)
    candidates = build_zone_watch_candidates(_scan_payload())

    result = monitor.evaluate(
        candidates,
        price_lookup=lambda symbol: 80900.0,
        now=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
    )

    assert result["alert_count"] == 0
    stored = state.get(candidates[0].key)
    assert stored is not None
    assert stored.get("invalidated_at") is not None
