import asyncio
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import time

from research.nave.prospective_collection import ProspectiveCollector, operational_status
from research.nave.prospective_runtime import CONTRACT_PATH, Pipeline, health_reasons
from research.nave.collector_health_gate import read_sample, sha, summarize

T0 = datetime(2026, 9, 7, 0, 1, tzinfo=UTC)


def collector(tmp_path):
    return ProspectiveCollector(repo_root=Path.cwd(), data_root=tmp_path / 'data',
        contract_path=Path('research/nave/experiments/closed-day-participant-history-v1.json'),
        clock=lambda: T0, source_commit='fixture')


def frame(index=0):
    return json.dumps({'action': 'buy', 'mint': 'synthetic', 'poolId': 'synthetic-pool',
        'signature': 'sig-' + str(index), 'timestamp': T0.timestamp()*1000,
        'slot': 123, 'breakdown': [{'trader': 'synthetic-wallet', 'quoteAmount': 2, 'tokenAmount': 3}]})


def test_batch_committed_dedupe_and_participant_fields_survive_restart(tmp_path):
    c = collector(tmp_path)
    frames = [(frame(i), T0) for i in range(20)]
    c.process_batch(frames)
    c.flush()
    assert c._db.execute('PRAGMA synchronous').fetchone()[0] == 2  # FULL unchanged
    assert c._db.execute('PRAGMA cache_size').fetchone()[0] == -131072
    assert all(row[0].endswith('/events.jsonl') for row in
               c._db.execute('SELECT output_path FROM events'))
    c._close_all_segments()
    c._db.close()
    second = collector(tmp_path)
    second.process_batch(frames)
    second.flush()
    assert second._db.execute('SELECT count(*) FROM events').fetchone()[0] == 20
    rows = [json.loads(line) for line in
        (second.data_root / 'validation/date=2026-09-07/participants.jsonl').read_text().splitlines()]
    assert len(rows) == 20
    assert all(r['participant_quote_amount'] == 2 and r['participant_token_amount'] == 3
               and r['transaction_signature'] and r['slot'] == 123 for r in rows)
    assert all(r['available_at'] == T0.isoformat().replace('+00:00', 'Z') for r in rows)
    second._db.close()


def test_crash_marker_and_overflow_are_explicit_not_complete(tmp_path):
    c = collector(tmp_path)
    (c.data_root / 'batch-state.json').write_text(json.dumps({'status': 'IN_FLIGHT', 'started_at': T0.isoformat()}))
    p = Pipeline(c)
    p.contract['queue_capacity_bytes'] = 1
    assert not p.put(frame(), T0, time.monotonic())
    assert p.snapshot()['state'] == 'FAILED'
    p.gap('BACKPRESSURE_OVERFLOW_ONE_FRAME_UNPERSISTED')
    p.apply_faults()
    c._mark_finished('STOPPED_BEFORE_WINDOW_END')
    checkpoint = json.loads((c.data_root / 'validation/date=2026-09-07/checkpoint.json').read_text())
    assert checkpoint['status'] == 'INCOMPLETE'
    assert checkpoint['provider_failures'] >= 2
    c._db.close()


def test_receiver_advances_while_worker_is_deliberately_blocked(tmp_path, monkeypatch):
    from research.nave import prospective_runtime as module
    c = collector(tmp_path)
    p = Pipeline(c)
    class Feed:
        count = 0
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def recv(self):
            self.count += 1
            if self.count == 100:
                c.request_stop()
            return frame(self.count)
    monkeypatch.setattr(module.websockets, 'connect', lambda *a, **k: Feed())
    # No persistence worker is scheduled: receiver must still consume bounded frames.
    asyncio.run(p.receive(T0 + timedelta(hours=1), 0))
    assert p.metrics['frames_received'] == 100
    assert p.metrics['frames_processed'] == 0
    assert p.q.qsize() == 100
    assert p.snapshot()['state'] != 'HEALTHY'
    c._db.close()


def test_status_never_opens_outcome_files(tmp_path, monkeypatch):
    c = collector(tmp_path)
    forbidden = c.data_root / 'holdout/date=2026-09-10/outcome-snapshots.jsonl'
    forbidden.write_text('do not read me')
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert path != forbidden
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    assert operational_status(c.data_root)['validation_holdout_analysis'] == 'HOLDOUT_LOCKED'
    c._db.close()


def test_process_worker_drains_ordered_frames_and_preserves_dedupe(tmp_path, monkeypatch):
    from research.nave import prospective_runtime as module
    c = collector(tmp_path)
    class Feed:
        count = 0
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def recv(self):
            self.count += 1
            if self.count == 300:
                c.request_stop()
            return frame(self.count)
    monkeypatch.setattr(module.websockets, 'connect', lambda *a, **k: Feed())
    assert asyncio.run(module.run_pipeline(c, T0+timedelta(hours=1), 0)) == 0
    health = json.loads((c.data_root / 'runtime-health.json').read_text())
    assert health['worker_pid'] != os.getpid()
    assert health['frames_received'] == health['frames_durable'] == 300
    assert health['queue_depth'] == health['queue_bytes'] == 0
    assert health['state'] == 'STOPPED'
    assert c._db.execute('SELECT count(*) FROM events').fetchone()[0] == 300
    assert json.loads((c.data_root / 'runtime-session.json').read_text())['status'] == 'STOPPED'
    c._db.close()


def test_dead_worker_stops_receiver_and_cannot_claim_clean_shutdown(tmp_path, monkeypatch):
    from research.nave import prospective_runtime as module
    c = collector(tmp_path)
    class Feed:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def recv(self):
            await asyncio.sleep(.01)
            return frame()
    def fail(*args):
        os._exit(7)
    monkeypatch.setattr(c, 'process_batch', fail)
    monkeypatch.setattr(module.websockets, 'connect', lambda *a, **k: Feed())
    async def run():
        return await asyncio.wait_for(module.run_pipeline(c, T0+timedelta(hours=1), 0), 10)
    assert asyncio.run(run()) == 1
    health = json.loads((c.data_root / 'runtime-health.json').read_text())
    assert health['state'] == 'FAILED'
    assert health['fatal_error'] == 'WORKER_EXIT_7'
    assert json.loads((c.data_root / 'runtime-session.json').read_text())['status'] == 'ACTIVE'
    c._db.close()


def healthy_metrics(now):
    stamp = now.isoformat()
    return dict(heartbeat_at=stamp, last_local_receive_at=stamp, last_provider_event_at=stamp,
        last_durable_write_at=stamp, last_checkpoint_at=stamp, queue_depth=0,
        oldest_queue_age_seconds=0, receive_to_process_seconds=.1, receive_to_persist_seconds=.2,
        max_receive_to_process_seconds=.1, max_receive_to_persist_seconds=.2,
        max_queue_depth=0, max_queue_age_seconds=0,
        event_loop_delay_seconds=0, state='HEALTHY', connection_state='CONNECTED',
        frames_received=0, frames_processed=0, frames_durable=0, reconnects=0,
        strategy_analysis_performed=False, validation_outcomes_inspected=False, holdout_outcomes_inspected=False)


def test_health_rejects_live_process_with_stale_pipeline():
    contract = json.loads(CONTRACT_PATH.read_text())
    sample = healthy_metrics(T0)
    assert not health_reasons(sample, contract, T0)
    assert health_reasons(sample, contract, T0+timedelta(seconds=60))


def fixture_gate_samples():
    samples = []
    for index in range(181):
        stamp = T0 + timedelta(seconds=index*10)
        metrics = healthy_metrics(stamp)
        metrics.update(frames_received=index*100, frames_processed=index*100, frames_durable=index*100)
        samples.append({'sampled_at': stamp.isoformat(), 'metrics': metrics, 'violations': [],
                        'lock_intact': True})
    pinned = {'run_id': 'fixture', 'started_at': T0.isoformat(), 'health_contract_sha256': 'a'*64,
              'collector_revision': 'fixture', 'collector_pid': 123}
    return samples, pinned


def test_full_interval_required_and_unhealthy_or_overflow_cannot_pass():
    contract = json.loads(CONTRACT_PATH.read_text())
    samples, pinned = fixture_gate_samples()
    assert summarize(samples, contract, pinned, 1800)['status'] == 'PASS'
    assert summarize(samples[:10], contract, pinned, 90)['status'] == 'FAIL'
    samples[30]['violations'] = ['BACKPRESSURE_OVERFLOW']
    assert summarize(samples, contract, pinned, 1800)['status'] == 'FAIL'
    samples[30]['violations'] = []
    for index in range(40, 44):
        samples[index]['violations'] = ['queue_depth_EXCEEDED_OR_MISSING']
    assert 'CONSECUTIVE_UNHEALTHY_SAMPLES' in summarize(samples, contract, pinned, 1800)['failure_reasons']


def test_validator_detects_lock_and_revision_change(tmp_path):
    import os
    c = collector(tmp_path)
    metrics = healthy_metrics(datetime.now(UTC))
    metrics.update(collector_pid=os.getpid(), collector_revision='fixture', health_contract_sha256=sha(CONTRACT_PATH))
    (c.data_root / 'runtime-health.json').write_text(json.dumps(metrics))
    pinned = dict(lock_sha256=sha(c.data_root / 'holdout-lock.json'), scientific_contracts={},
        health_contract_path=str(CONTRACT_PATH), health_contract_sha256=sha(CONTRACT_PATH),
        collector_revision='fixture', collector_pid=os.getpid())
    assert not read_sample(c.data_root, json.loads(CONTRACT_PATH.read_text()), pinned)['violations']
    (c.data_root / 'holdout-unlock.json').write_text('{}')
    pinned['collector_revision'] = 'different'
    reasons = read_sample(c.data_root, json.loads(CONTRACT_PATH.read_text()), pinned)['violations']
    assert 'HOLDOUT_LOCK_CHANGED' in reasons and 'COLLECTOR_REVISION_CHANGED' in reasons
    c._db.close()
