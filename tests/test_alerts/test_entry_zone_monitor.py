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


def _scan_payload_with_zone(*, entry_zone: list[float], invalidation: float) -> dict:
    return {
        "summary": {"effective_score_threshold": 75},
        "results": {
            "BTCUSDT": {
                "plans": [
                    {
                        "side": "long",
                        "confidence_score": 84,
                        "entry_zone": entry_zone,
                        "invalidation": invalidation,
                        "rr_estimated": 4.63,
                        "setup_status": "pending",
                    }
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


def test_entry_zone_monitor_keeps_armed_zone_when_fresh_scan_drifts(tmp_path) -> None:
    state = ZoneWatchStateStore(path=tmp_path / "state.json")
    monitor = EntryZoneMonitor(state)
    initial_candidates = build_zone_watch_candidates(
        _scan_payload_with_zone(
            entry_zone=[81112.86, 82479.0], invalidation=81052.5)
    )
    shifted_candidates = build_zone_watch_candidates(
        _scan_payload_with_zone(
            entry_zone=[82550.0, 83800.0], invalidation=82480.0)
    )

    first = monitor.evaluate(
        initial_candidates,
        price_lookup=lambda symbol: 81080.0,
        now=datetime(2026, 5, 6, 9, 0, tzinfo=timezone.utc),
    )
    second = monitor.evaluate(
        shifted_candidates,
        price_lookup=lambda symbol: 82300.0,
        now=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
    )

    assert first["alert_count"] == 0
    assert second["alert_count"] == 1
    assert second["alerts"][0]["entry_zone"] == [81112.86, 82479.0]
    assert second["alerts"][0]["watch_status"] == "holding_previous"
    assert second["watch_states"][0]["entry_zone"] == [81112.86, 82479.0]
    assert second["watch_states"][0]["scan_entry_zone"] == [82550.0, 83800.0]
    assert second["watch_states"][0]["watch_status"] == "holding_previous"


def test_entry_zone_monitor_rearms_after_invalidation(tmp_path) -> None:
    state = ZoneWatchStateStore(path=tmp_path / "state.json")
    monitor = EntryZoneMonitor(state)
    initial_candidates = build_zone_watch_candidates(
        _scan_payload_with_zone(
            entry_zone=[81112.86, 82479.0], invalidation=81052.5)
    )
    replacement_candidates = build_zone_watch_candidates(
        _scan_payload_with_zone(
            entry_zone=[82550.0, 83800.0], invalidation=82480.0)
    )

    invalidated = monitor.evaluate(
        initial_candidates,
        price_lookup=lambda symbol: 81000.0,
        now=datetime(2026, 5, 6, 9, 0, tzinfo=timezone.utc),
    )
    rearmed = monitor.evaluate(
        replacement_candidates,
        price_lookup=lambda symbol: 83000.0,
        now=datetime(2026, 5, 6, 16, 0, tzinfo=timezone.utc),
    )

    assert invalidated["watch_states"][0]["invalidated"] is True
    assert rearmed["alert_count"] == 1
    assert rearmed["alerts"][0]["entry_zone"] == [82550.0, 83800.0]
    assert rearmed["alerts"][0]["watch_status"] == "rearmed_after_invalidation"
