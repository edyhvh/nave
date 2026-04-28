"""Tests for persistent memecoin scan archive history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading.memecoin.archive import mint_history, persist_scan_snapshot, scan_history_payload



def test_mint_history_counts_repeated_appearances(tmp_path):
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)

    persist_scan_snapshot(
        candidates=[{"mint": "AAA"}, {"mint": "BBB"}],
        params={"limit": 10},
        scan_dir=tmp_path,
        scanned_at=now - timedelta(hours=2),
    )
    persist_scan_snapshot(
        candidates=[{"mint": "AAA"}, {"mint": "CCC"}],
        params={"limit": 10},
        scan_dir=tmp_path,
        scanned_at=now - timedelta(minutes=30),
    )

    hist = mint_history(hours=24, scan_dir=tmp_path, now=now)

    assert hist["AAA"].seen_count == 2
    assert hist["BBB"].seen_count == 1
    assert hist["CCC"].seen_count == 1



def test_scan_history_payload_shapes_rows(tmp_path):
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    persist_scan_snapshot(
        candidates=[{"mint": "AAA"}],
        params={"limit": 10},
        scan_dir=tmp_path,
        scanned_at=now - timedelta(minutes=5),
    )

    payload = scan_history_payload(hours=24, scan_dir=tmp_path, now=now)

    assert payload["tool"] == "memecoin_scan_history"
    assert payload["count"] == 1
    assert payload["tokens"][0]["mint"] == "AAA"
    assert payload["tokens"][0]["seen_count"] == 1
