from datetime import UTC, datetime
import json

import pytest

from research.nave.raw_capture_spool import RawCaptureSpool, SpoolIncomplete, replay_segment


def test_lossless_clock_and_restart_replay_with_exclusive_writer(tmp_path):
    clock = datetime(2026, 9, 6, tzinfo=UTC)
    raw = json.dumps({'timestamp': 1788652800, 'slot': 123, 'signature': 'fixture',
                      'mint': 'fixture-mint', 'pool': 'fixture-pool', 'creator': 'fixture',
                      'breakdown': [{'trader': 'fixture', 'quoteAmount': 1.25}]}).encode()
    spool = RawCaptureSpool(tmp_path, max_bytes=10000, reserve_bytes=0)
    with pytest.raises(BlockingIOError):
        RawCaptureSpool(tmp_path, max_bytes=10000, reserve_bytes=0)
    receipts = spool.append_batch([(raw, clock), (raw, clock)])
    spool.close()
    assert receipts[0]['event_id'] == receipts[1]['event_id']
    path = tmp_path / receipts[0]['segment']
    rows = list(replay_segment(path))
    assert [r[:2] for r in rows] == [(raw, clock), (raw, clock)]
    assert len(list(replay_segment(path, offset=receipts[0]['next_offset']))) == 1
    next_spool = RawCaptureSpool(tmp_path, max_bytes=10000, reserve_bytes=0)
    assert next_spool.append_batch([(raw, clock)])[0]['segment'] != path.name
    next_spool.close()


def test_limits_and_corruption_fail_without_deleting_evidence(tmp_path):
    spool = RawCaptureSpool(tmp_path, max_bytes=1, reserve_bytes=0)
    with pytest.raises(SpoolIncomplete, match='DISK_LIMIT'):
        spool.append_batch([(b'{}', datetime.now(UTC))])
    spool.close()
    path = tmp_path / 'segment-000000000000.jsonl'
    path.write_bytes(b'{"partial":')
    with pytest.raises(SpoolIncomplete, match='PARTIAL_CAPTURE_TAIL'):
        list(replay_segment(path))
    assert path.read_bytes() == b'{"partial":'


def test_fsync_failure_never_acknowledges_or_continues(tmp_path, monkeypatch):
    from research.nave import raw_capture_spool as module
    spool = RawCaptureSpool(tmp_path, max_bytes=10000, reserve_bytes=0)
    def fail(_fd):
        raise OSError('synthetic fsync failure')
    monkeypatch.setattr(module.os, 'fsync', fail)
    with pytest.raises(OSError, match='synthetic'):
        spool.append_batch([(b'{}', datetime.now(UTC))])
    with pytest.raises(SpoolIncomplete, match='FAILED_WRITER'):
        spool.append_batch([(b'{}', datetime.now(UTC))])
    spool.close()
