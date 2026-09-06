import json
from datetime import UTC, datetime, timedelta

import pytest

from research.nave.prospective_collection import (
    HoldoutLocked,
    ProspectiveCollector,
    holdout_lock_path,
    operational_status,
    parse_provider_timestamp,
    require_holdout_unlock,
)


CONTRACT = "research/nave/experiments/closed-day-participant-history-v1.json"
T0 = datetime(2026, 9, 7, 0, 1, tzinfo=UTC)


def _event(action="create", *, mint="MintA", pool="PoolA", timestamp=None, **extra):
    return {
        "action": action,
        "mint": mint,
        "poolId": pool,
        "pool": "pump",
        "signature": f"sig-{action}-{mint}-{timestamp}",
        "timestamp": int((timestamp or T0).timestamp() * 1000),
        "quoteAmount": 1.0,
        **extra,
    }


def _collector(tmp_path):
    return ProspectiveCollector(
        repo_root=tmp_path,
        data_root=tmp_path / "prospective",
        contract_path=__import__("pathlib").Path(CONTRACT),
        clock=lambda: T0,
        source_commit="test-commit",
    )


def test_launch_has_required_identity_clocks_and_two_outcome_jobs(tmp_path):
    collector = _collector(tmp_path)
    raw = _event(breakdown=[{"action": "buy", "trader": "TraderA", "tokenAmount": 10, "quoteAmount": 1}])
    collector.process_message(json.dumps(raw), T0 + timedelta(seconds=2))
    collector.flush()
    collector._db.close()

    day = tmp_path / "prospective" / "validation" / "date=2026-09-07"
    launch = json.loads((day / "launches.jsonl").read_text().splitlines()[0])
    event = json.loads(next((day / "capture_date=2026-09-07").rglob("events.jsonl")).read_text().splitlines()[0])
    assert launch["chain_id"] == "solana:mainnet"
    assert launch["contract_address"] == "MintA"
    assert launch["pool_address"] == "PoolA"
    assert launch["launch_time"] == "2026-09-07T00:01:00Z"
    assert launch["decision_time"] == "2026-09-07T00:06:00Z"
    assert event["launch_time"] == launch["launch_time"]
    assert event["decision_time"] == launch["decision_time"]
    assert event["observed_at"] == event["available_at"]
    assert event["retrieved_at"] is not None
    assert len((day / "outcome-jobs.jsonl").read_text().splitlines()) == 2
    participant_path = day / "participants.jsonl"
    assert not participant_path.exists(), "create breakdown is not a prior-history row"

    status = json.loads((day / "checkpoint.json").read_text())
    assert status["unique_launches"] == 1
    assert status["outcome_jobs"] == 2
    assert status["status"] == "OPEN"


def test_outcome_jobs_capture_causal_same_pool_raw_state(tmp_path):
    collector = _collector(tmp_path)
    collector.process_message(json.dumps(_event()), T0)
    before_entry = T0 + timedelta(minutes=5, seconds=29)
    collector.process_message(
        json.dumps(_event("buy", timestamp=before_entry, price=2.0, quoteInPool=50.0)),
        T0 + timedelta(minutes=5, seconds=30),
    )
    before_exit = T0 + timedelta(hours=1, minutes=4, seconds=59)
    collector.process_message(
        json.dumps(_event("buy", timestamp=before_exit, price=3.0, quoteInPool=75.0)),
        T0 + timedelta(hours=1, minutes=5, seconds=1),
    )
    collector.flush()
    collector._db.close()

    day = tmp_path / "prospective" / "validation" / "date=2026-09-07"
    snapshots = [
        json.loads(line)
        for line in (day / "outcome-snapshots.jsonl").read_text().splitlines()
    ]
    assert {row["horizon"] for row in snapshots} == {"30s", "60m"}
    assert all(row["pool_address"] == "PoolA" for row in snapshots)
    assert all(row["same_pool_required"] for row in snapshots)
    assert all(row["analysis_status"] == "NOT_ANALYZED" for row in snapshots)


def test_restart_and_duplicate_launch_are_idempotent(tmp_path):
    raw = _event()
    first = _collector(tmp_path)
    first.process_message(json.dumps(raw), T0)
    first.flush()
    first._db.close()
    second = _collector(tmp_path)
    second.process_message(json.dumps(raw), T0 + timedelta(seconds=1))
    second.flush()
    second._db.close()

    day = tmp_path / "prospective" / "validation" / "date=2026-09-07"
    assert len((day / "launches.jsonl").read_text().splitlines()) == 1
    checkpoint = json.loads((day / "checkpoint.json").read_text())
    assert checkpoint["duplicate_events"] == 1


def test_missing_pool_and_participant_remain_unknown(tmp_path):
    collector = _collector(tmp_path)
    collector.process_message(
        json.dumps(_event(pool=None, mint="MintNoPool")), T0
    )
    trade = _event("buy", mint="MintNoPool", pool=None, timestamp=T0 + timedelta(seconds=10))
    trade.pop("breakdown", None)
    collector.process_message(json.dumps(trade), T0 + timedelta(seconds=11))
    collector.flush()
    collector._db.close()

    day = tmp_path / "prospective" / "validation" / "date=2026-09-07"
    launch = json.loads((day / "launches.jsonl").read_text().splitlines()[0])
    assert launch["pool_address"] is None
    participant = json.loads((day / "participants.jsonl").read_text().splitlines()[0])
    assert participant["participant_id"] is None
    assert participant["participant_identity_status"] == "UNKNOWN"


def test_participant_amounts_and_transaction_provenance_are_persisted(tmp_path):
    collector = _collector(tmp_path)
    raw = _event(
        "buy",
        mint="MintA",
        pool="PoolA",
        timestamp=T0 + timedelta(seconds=10),
        breakdown=[
            {"trader": "TraderA", "tokenAmount": 10.0, "quoteAmount": 1.0},
            {"trader": "TraderB", "tokenAmount": 20.0, "quoteAmount": 2.0},
        ],
    )
    collector.process_message(json.dumps(raw), T0 + timedelta(seconds=11))
    collector.flush()
    collector._db.close()

    day = tmp_path / "prospective" / "validation" / "date=2026-09-07"
    participants = [
        json.loads(line)
        for line in (day / "participants.jsonl").read_text().splitlines()
    ]
    assert {row["participant_id"] for row in participants} == {"TraderA", "TraderB"}
    assert {row["participant_quote_amount"] for row in participants} == {1.0, 2.0}
    assert {row["participant_token_amount"] for row in participants} == {10.0, 20.0}
    assert all(row["transaction_signature"] for row in participants)
    assert all(row["slot"] is None for row in participants) is True


def test_invalid_and_delayed_timestamps_are_explicit(tmp_path):
    collector = _collector(tmp_path)
    collector.process_message(json.dumps({"action": "buy", "mint": "Bad", "timestamp": "bad"}), T0)
    delayed = _event("buy", mint="Delayed", timestamp=T0 - timedelta(seconds=10))
    collector.process_message(json.dumps(delayed), T0)
    collector.flush()
    collector._db.close()

    quarantine = tmp_path / "prospective" / "quarantine" / "date=2026-09-07"
    bad = json.loads(next(quarantine.rglob("events.jsonl")).read_text().splitlines()[0])
    assert "INVALID_EVENT_TIMESTAMP" in bad["quality_flags"]
    validation = tmp_path / "prospective" / "validation" / "date=2026-09-07"
    delayed_row = json.loads(next(validation.rglob("events.jsonl")).read_text().splitlines()[0])
    assert "PROVIDER_EVENT_DELAYED_BEFORE_LOCAL_RECEIPT" in delayed_row["quality_flags"]
    assert delayed_row["available_at"] == "2026-09-07T00:01:00Z"


def test_holdout_lock_fails_closed_and_status_is_operational_only(tmp_path):
    collector = _collector(tmp_path)
    with pytest.raises(HoldoutLocked):
        require_holdout_unlock(tmp_path / "prospective", collector.contract_sha256)
    collector.flush()
    status = operational_status(tmp_path / "prospective")
    assert status["validation_holdout_analysis"] == "HOLDOUT_LOCKED"
    assert "gross_return" not in json.dumps(status)
    assert holdout_lock_path(tmp_path / "prospective").exists()
    collector._db.close()


def test_timestamp_parser_does_not_impute_invalid_values():
    assert parse_provider_timestamp("not-a-time") is None
    assert parse_provider_timestamp(None) is None
    assert parse_provider_timestamp(int(T0.timestamp() * 1000)) == T0


def test_silent_connected_stream_records_failure_and_preserves_incomplete_day(tmp_path, monkeypatch):
    import asyncio
    from research.nave import prospective_collection as module

    collector = _collector(tmp_path)
    collector.receive_timeout_seconds = 0.01
    collector.process_message(json.dumps(_event()), T0)

    class SilentConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            collector.request_stop()

        async def recv(self):
            await asyncio.Future()

    monkeypatch.setattr(module.websockets, "connect", lambda *a, **kw: SilentConnection())
    asyncio.run(collector.run(stop_at=T0 + timedelta(hours=1), reconnect_max_seconds=0))
    assert collector.manifest["connections"][-1]["status"] == "FAILED"
    assert len(collector.manifest["provider_failures"]) == 1
    day = tmp_path / "prospective" / "validation" / "date=2026-09-07"
    checkpoint = json.loads((day / "checkpoint.json").read_text())
    assert checkpoint["status"] == "INCOMPLETE"
    assert checkpoint["provider_failures"] == 1
    assert holdout_lock_path(tmp_path / "prospective").exists()
    collector._db.close()
