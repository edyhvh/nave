"""Bounded receiver/serialized durable worker and operational telemetry only."""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import queue
import resource
import threading
import time

import websockets

from research.nave.prospective_collection import iso, parse_provider_timestamp, _atomic_json

CONTRACT_PATH = Path(__file__).parent / 'experiments/collector-health-gate-v1.json'


def durable_json(path, payload):
    _atomic_json(path, payload)
    with path.open('rb') as handle:
        os.fsync(handle.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def age(value, now):
    if not value:
        return None
    return max(0, (now - datetime.fromisoformat(value.replace('Z', '+00:00'))).total_seconds())


def health_reasons(sample, contract, now=None):
    now = now or datetime.now(UTC)
    reasons = []
    for field, limit in (
        ('heartbeat_at', 'max_heartbeat_age_seconds'),
        ('last_local_receive_at', 'max_socket_receive_silence_seconds'),
        ('last_provider_event_at', 'max_provider_event_age_seconds'),
        ('last_durable_write_at', 'max_receive_to_persist_seconds'),
        ('last_checkpoint_at', 'max_checkpoint_age_seconds'),
    ):
        elapsed = age(sample.get(field), now)
        if elapsed is None or elapsed > contract[limit]:
            reasons.append(field + '_STALE_OR_MISSING')
    for field, limit in (
        ('queue_depth', 'max_queue_depth'), ('oldest_queue_age_seconds', 'max_queue_age_seconds'),
        ('receive_to_process_seconds', 'max_receive_to_process_seconds'),
        ('receive_to_persist_seconds', 'max_receive_to_persist_seconds'),
        ('event_loop_delay_seconds', 'max_event_loop_delay_seconds'),
    ):
        value = sample.get(field)
        if value is None or value > contract[limit]:
            reasons.append(field + '_EXCEEDED_OR_MISSING')
    if sample.get('overflow_count', 0):
        reasons.append('BACKPRESSURE_OVERFLOW')
    if sample.get('fatal_error'):
        reasons.append('FAILED')
    if sample.get('data_error_count', 0):
        reasons.append('MALFORMED_PROVIDER_FRAMES')
    return reasons


class Pipeline:
    def __init__(self, collector):
        self.c = collector
        self.contract_bytes = CONTRACT_PATH.read_bytes()
        self.contract = json.loads(self.contract_bytes)
        self.q = queue.Queue(self.contract['queue_capacity_frames'])
        self.lock = threading.Lock()
        self.pending_bytes = 0
        self.finished_receiving = threading.Event()
        self.worker_done = threading.Event()
        self.faults = queue.SimpleQueue()
        self.timings = defaultdict(float)
        self.stage_max = defaultdict(float)
        self.latencies = deque(maxlen=4096)
        self.metrics = {
            'schema_version': 'nave.collector-runtime-health.v1',
            'collector_pid': os.getpid(), 'collector_revision': collector.source_commit,
            'health_contract_sha256': hashlib.sha256(self.contract_bytes).hexdigest(),
            'state': 'RECOVERING', 'started_at': iso(collector.clock()),
            'frames_received': 0, 'frames_processed': 0, 'frames_durable': 0,
            'participant_rows': 0, 'reconnects': 0, 'overflow_count': 0,
            'max_queue_depth': 0, 'max_queue_age_seconds': 0,
            'receive_to_process_seconds': 0, 'receive_to_persist_seconds': 0,
            'max_receive_to_process_seconds': 0, 'max_receive_to_persist_seconds': 0,
            'event_loop_delay_seconds': 0, 'socket_timestamp_semantics':
                'WebSocket application-frame receipt; kernel NIC arrival timestamp unavailable',
            'strategy_analysis_performed': False, 'validation_outcomes_inspected': False,
            'holdout_outcomes_inspected': False,
        }
        self.last_rates = (time.monotonic(), 0, 0, 0)
        self.last_manifest = 0
        self.process_worker = False
        self.progress_queue = None
        self.pending_frames = deque()
        self.process_mode = False
        self.health_path = collector.data_root / 'runtime-health.json'
        self.session_path = collector.data_root / 'runtime-session.json'
        self.gap_path = collector.data_root / 'operational-gaps.jsonl'
        # Only operational markers, never event/outcome payloads.
        for path in (collector.data_root / 'batch-state.json', self.session_path):
            if path.exists() and json.loads(path.read_text()).get('status') in ('IN_FLIGHT', 'ACTIVE'):
                previous = json.loads(path.read_text())
                self.gap('UNCLEAN_RESTART_REQUIRES_RECONCILIATION', previous.get('started_at'))
        if collector.previous_manifest:
            self.gap('COLLECTOR_RESTART_GAP', collector.previous_manifest.get('last_updated_at'))
        durable_json(self.session_path, {'status': 'ACTIVE', 'pid': os.getpid(),
                                       'started_at': iso(collector.clock())})
        # Inclusive stage timings; participant timing includes its JSONL writes.
        for name in ('_normalize_record', '_write_participants', '_append_line',
                     '_capture_due_outcomes', '_flush_checkpoints'):
            method = getattr(collector, name)
            def wrapped(*args, _method=method, _name=name, **kwargs):
                start = time.perf_counter()
                try:
                    return _method(*args, **kwargs)
                finally:
                    elapsed = time.perf_counter() - start
                    self.timings[_name] += elapsed
                    self.stage_max[_name] = max(self.stage_max[_name], elapsed)
            setattr(collector, name, wrapped)

    def gap(self, reason, since=None):
        record = {'at': iso(self.c.clock()), 'reason': reason, 'status': 'INCOMPLETE',
                  'since': since or self.metrics.get('last_local_receive_at') or iso(self.c.clock()),
                  'pid': os.getpid(), 'analysis_performed': False}
        with self.gap_path.open('a') as handle:
            handle.write(json.dumps(record) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        if self.process_mode and not self.process_worker:
            # Same ordered pipe as frames: faults precede the shutdown sentinel.
            self.q.put({'fault': record}, timeout=5)
        else:
            self.faults.put(record)

    def put(self, frame, received_at, monotonic):
        self.drain_progress()
        size = len(frame) if isinstance(frame, bytes) else len(frame.encode('utf-8'))
        with self.lock:
            if (self.q.full() or (self.process_mode and len(self.pending_frames) >= self.contract['queue_capacity_frames'])
                    or self.pending_bytes + size > self.contract['queue_capacity_bytes']):
                self.metrics['overflow_count'] += 1
                return False
            try:
                self.q.put_nowait((frame, received_at, monotonic, size))
            except queue.Full:
                self.metrics['overflow_count'] += 1
                return False
            if self.process_mode:
                self.pending_frames.append((monotonic, size))
            self.pending_bytes += size
            depth = len(self.pending_frames) if self.process_mode else self.q.qsize()
            self.metrics['max_queue_depth'] = max(self.metrics['max_queue_depth'], depth)
        return True

    def drain_progress(self):
        if not self.process_mode or self.process_worker:
            return
        while True:
            try:
                update = self.progress_queue.get_nowait()
            except queue.Empty:
                break
            with self.lock:
                completed = update['metrics']['frames_durable'] - self.metrics['frames_durable']
                for _ in range(completed):
                    if self.pending_frames:
                        _, size = self.pending_frames.popleft()
                        self.pending_bytes -= size
                self.metrics.update(update['metrics'])
                self.timings = update['timings']
                self.stage_max = update['stage_max']
                self.latencies.extend(update['latencies'])
            if update['metrics'].get('fatal_error'):
                self.c.request_stop()

    def publish_progress(self, latencies=()):
        if not self.process_worker:
            return
        excluded = {'collector_pid', 'state', 'frames_received', 'reconnects', 'overflow_count',
                    'event_loop_delay_seconds', 'max_queue_depth'}
        values = {key: value for key, value in self.metrics.items() if key not in excluded}
        usage = resource.getrusage(resource.RUSAGE_SELF)
        values.update(worker_pid=os.getpid(), worker_cpu_seconds=usage.ru_utime+usage.ru_stime,
                      worker_max_rss_kib=usage.ru_maxrss)
        self.progress_queue.put({'metrics': values, 'timings': dict(self.timings),
            'stage_max': dict(self.stage_max), 'latencies': list(latencies)}, timeout=5)

    def snapshot(self):
        self.drain_progress()
        now = self.c.clock()
        with self.lock:
            result = dict(self.metrics)
            result['queue_bytes'] = self.pending_bytes
            if self.process_mode:
                result['queue_depth'] = len(self.pending_frames)
                result['oldest_queue_age_seconds'] = (
                    time.monotonic()-self.pending_frames[0][0] if self.pending_frames else 0)
            else:
                with self.q.mutex:
                    result['queue_depth'] = len(self.q.queue)
                    result['oldest_queue_age_seconds'] = (
                        time.monotonic() - self.q.queue[0][2] if self.q.queue else 0)
            result['stage_seconds_inclusive'] = dict(self.timings)
            result['stage_max_seconds'] = dict(self.stage_max)
            values = sorted(self.latencies)
        result['p95_receive_to_persist_seconds'] = values[int(.95*(len(values)-1))] if values else 0
        result['connection_age_seconds'] = age(result.get('connection_started_at'), now)
        reasons = health_reasons(result, self.contract, now)
        if result.get('fatal_error') or result['overflow_count'] or result.get('data_error_count'):
            state = 'FAILED'
        elif any('queue_' in reason or 'receive_to_' in reason for reason in reasons):
            state = 'DEGRADED_BACKLOG'
        elif 'last_local_receive_at_STALE_OR_MISSING' in reasons:
            state = 'PROVIDER_STALLED'
        elif reasons or result.get('connection_state') != 'CONNECTED':
            state = 'RECOVERING'
        else:
            state = 'HEALTHY'
        result.update(state=state, reasons=reasons, observed_at=iso(now))
        return result

    def apply_faults(self):
        while not self.faults.empty():
            record = self.faults.get()
            day = datetime.fromisoformat(record['since'].replace('Z', '+00:00')).date()
            end = datetime.fromisoformat(record['at'].replace('Z', '+00:00')).date()
            while day <= end:
                day_string = day.isoformat()
                partition = ('validation' if day_string in self.c.validation_days else
                             'holdout' if day_string in self.c.holdout_days else 'warmup')
                checkpoint = self.c._checkpoint(partition, day_string)
                checkpoint['status'] = 'INCOMPLETE'
                checkpoint['source_reconciliation'] = 'REQUIRED_BEFORE_COMPLETE_CLOSED_DAY'
                checkpoint['provider_failures'] = checkpoint.get('provider_failures', 0) + 1
                self.c._write_checkpoint(partition, day_string, checkpoint)
                day += timedelta(days=1)

    def worker(self):
        try:
            end_seen = False
            while not end_seen and (self.process_worker or not self.finished_receiving.is_set() or not self.q.empty()):
                batch = []
                deadline = time.monotonic() + self.contract['batch_max_wait_seconds']
                while len(batch) < self.contract['batch_max_frames']:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        item = self.q.get(timeout=remaining)
                        if item is None:
                            end_seen = True
                            break
                        if isinstance(item, dict):
                            self.faults.put(item['fault'])
                            continue
                        batch.append(item)
                    except queue.Empty:
                        break
                self.apply_faults()
                if not batch:
                    continue
                start = time.monotonic()
                before = self.c._counters['participant_rows']
                errors_before = self.c._counters['provider_errors']
                self.c.process_batch([(frame, received) for frame, received, _, _ in batch])
                finished = time.monotonic()
                if self.c._counters['provider_errors'] > errors_before:
                    self.gap('MALFORMED_PROVIDER_FRAMES', iso(batch[0][1]))
                checkpoint_at = max((p.get('last_updated_at', '') for p in self.c._checkpoint_cache.values()), default=None)
                with self.lock:
                    if not self.process_worker:
                        self.pending_bytes -= sum(item[3] for item in batch)
                    self.metrics['frames_processed'] += len(batch)
                    self.metrics['frames_durable'] += len(batch)
                    self.metrics['participant_rows'] += self.c._counters['participant_rows'] - before
                    process_latency = max(start - item[2] for item in batch)
                    persist_latency = max(finished - item[2] for item in batch)
                    self.metrics.update(
                        last_processed_event_at=iso(batch[-1][1]),
                        last_process_completed_at=iso(self.c.clock()),
                        last_processed_event_key=getattr(self.c, 'last_processed_event_key', None),
                        last_persisted_event_key=getattr(self.c, 'last_processed_event_key', None),
                        last_durable_write_at=iso(self.c.clock()),
                        last_checkpoint_at=checkpoint_at,
                        receive_to_process_seconds=process_latency,
                        receive_to_persist_seconds=persist_latency,
                        write_batch_seconds=finished-start,
                        sqlite_commit_seconds=self.c.last_sqlite_commit_seconds,
                        data_error_count=self.c._counters['provider_errors'],
                        jsonl_fsync_seconds=self.c.last_jsonl_fsync_seconds,
                        outcome_job_backlog=len(self.c._outcome_heap),
                        outcome_snapshots_written=self.c._counters['outcome_snapshots'],
                        outcome_jobs_scheduled=self.c._counters['outcome_jobs'],
                        outcome_job_oldest_due_age_seconds=max(0, self.c.clock().timestamp()
                            - self.c._outcome_heap[0][0]) if self.c._outcome_heap else 0,
                    )
                    self.metrics['max_queue_age_seconds'] = max(self.metrics['max_queue_age_seconds'], process_latency)
                    for field, value in [('max_receive_to_process_seconds', process_latency),
                                         ('max_receive_to_persist_seconds', persist_latency)]:
                        self.metrics[field] = max(self.metrics[field], value)
                    self.latencies.extend(finished-item[2] for item in batch)
                self.publish_progress(finished-item[2] for item in batch)
                if finished-self.last_manifest >= 5:
                    # Receiver health is authoritative in runtime-health.json;
                    # the child never claims transport health from its own copy.
                    snapshot = self.metrics | {'state': 'RECOVERING'} if self.process_worker else self.snapshot()
                    self.c.manifest.update(status=snapshot['state'],
                        source_commit=self.c.source_commit, runtime_health_file=str(self.health_path),
                        runtime_connection={key: snapshot.get(key) for key in
                            ('connection_state', 'connection_number', 'connection_started_at',
                             'last_local_receive_at', 'reconnects')})
                    self.c._write_manifest()
                    self.last_manifest = finished
            self.apply_faults()
            self.c.flush()
        except BaseException as exc:
            with self.lock:
                self.metrics['fatal_error'] = type(exc).__name__
            self.c.request_stop()
            self.gap('PERSISTENCE_FAILED:' + type(exc).__name__)
            self.publish_progress()
            raise
        finally:
            self.worker_done.set()

    async def heartbeat(self):
        prior = time.monotonic()
        while not self.worker_done.is_set():
            self.drain_progress()
            if self.process_mode and not self.worker_process.is_alive():
                self.metrics['fatal_error'] = 'WORKER_EXITED'
                self.c.request_stop()
                break
            now = time.monotonic()
            with self.lock:
                self.metrics['heartbeat_at'] = iso(self.c.clock())
                self.metrics['event_loop_delay_seconds'] = max(0, now-prior-2)
                self.metrics['open_file_descriptors'] = len(os.listdir('/proc/self/fd'))
                usage = resource.getrusage(resource.RUSAGE_SELF)
                self.metrics['max_rss_kib'] = usage.ru_maxrss
                self.metrics['cpu_seconds'] = usage.ru_utime + usage.ru_stime
                t, received, processed, participants = self.last_rates
                elapsed = max(now-t, .001)
                for name, count, previous in (
                    ('frames_received_per_second', self.metrics['frames_received'], received),
                    ('frames_processed_per_second', self.metrics['frames_processed'], processed),
                    ('participant_rows_per_second', self.metrics['participant_rows'], participants)):
                    self.metrics[name] = (count-previous)/elapsed
                self.last_rates = (now, self.metrics['frames_received'],
                                   self.metrics['frames_processed'], self.metrics['participant_rows'])
            await asyncio.to_thread(_atomic_json, self.health_path, self.snapshot())
            prior = now
            await asyncio.sleep(2)
        if not self.finished_receiving.is_set():
            self.drain_progress()
            self.metrics.setdefault('fatal_error', 'WORKER_STOPPED_BEFORE_RECEIVER')
            self.c.request_stop()

    async def receive(self, stop_at, reconnect_max_seconds):
        backoff = 1
        attempts = 0
        while not self.c.stop_requested and self.c.clock() < stop_at:
            self.c.connection_number += 1
            attempts += 1
            with self.lock:
                self.metrics.update(connection_state='CONNECTING', reconnects=attempts-1,
                                    connection_number=self.c.connection_number)
            try:
                async with websockets.connect(self.c.stream_uri, open_timeout=15, close_timeout=3,
                    ping_interval=5, ping_timeout=10, max_queue=16,
                    max_size=self.c.max_event_bytes) as ws:
                    with self.lock:
                        self.metrics.update(connection_state='CONNECTED',
                                            connection_started_at=iso(self.c.clock()))
                    last_received = time.monotonic()
                    silence_limit = min(self.contract['max_socket_receive_silence_seconds'],
                                        self.c.receive_timeout_seconds)
                    while not self.c.stop_requested and self.c.clock() < stop_at:
                        try:
                            frame = await asyncio.wait_for(ws.recv(), min(1, silence_limit))
                        except TimeoutError:
                            if time.monotonic()-last_received >= silence_limit:
                                raise TimeoutError('APPLICATION_STREAM_SILENCE') from None
                            continue
                        received = self.c.clock()
                        tick = time.monotonic()
                        last_received = tick
                        # Receiver clock is assigned before JSON parsing or queueing.
                        try:
                            header = json.loads(frame)
                            timestamp = parse_provider_timestamp(header.get('timestamp')) if isinstance(header, dict) else None
                        except (ValueError, UnicodeError):
                            timestamp = None
                        with self.lock:
                            self.metrics['frames_received'] += 1
                            self.metrics.update(last_socket_receive_at=iso(received),
                                last_local_receive_at=iso(received),
                                last_received_frame_sha256=hashlib.sha256(frame.encode() if isinstance(frame, str) else frame).hexdigest())
                            if timestamp:
                                self.metrics['last_provider_event_at'] = iso(timestamp)
                        if not self.put(frame, received, tick):
                            await asyncio.to_thread(self.gap, 'BACKPRESSURE_OVERFLOW_ONE_FRAME_UNPERSISTED')
                            self.c.request_stop()
                            break
                        with self.lock:
                            self.metrics['receiver_hot_path_seconds'] = time.monotonic()-tick
                        backoff = 1
            except Exception as exc:
                reason = type(exc).__name__ + ':' + str(exc)[:160]
                with self.lock:
                    self.metrics.update(connection_state='DISCONNECTED', last_connection_error=reason,
                                        last_stall_at=iso(self.c.clock()))
                await asyncio.to_thread(self.gap, reason)
                if not self.c.stop_requested:
                    await asyncio.sleep(min(backoff, reconnect_max_seconds))
                    backoff = min(backoff*2, max(reconnect_max_seconds, 1))
        self.finished_receiving.set()


def _process_worker(pipeline, stop_at):
    pipeline.process_worker = True
    pipeline.c._db = pipeline.c._open_db()
    try:
        pipeline.worker()
        pipeline.c._mark_finished('STOPPED_BEFORE_WINDOW_END'
            if pipeline.c.clock() < stop_at else 'WINDOW_COLLECTION_ENDED')
        durable_json(pipeline.session_path, {'status': 'STOPPED', 'at': iso(pipeline.c.clock())})
    finally:
        pipeline.c._db.close()


async def run_pipeline(collector, stop_at, reconnect_max_seconds=60):
    # Fork before WebSocket/default-executor threads exist, with no open SQLite
    # connection inherited. Exactly one child owns the durable writer state.
    if threading.active_count() != 1:
        raise RuntimeError('Collector process isolation requires single-threaded startup')
    pipeline = Pipeline(collector)
    context = multiprocessing.get_context('fork')
    pipeline.q = context.Queue(pipeline.contract['queue_capacity_frames'])
    pipeline.progress_queue = context.Queue(64)
    pipeline.worker_done = context.Event()
    pipeline.process_mode = True
    collector._db.close()
    collector._db = None
    worker = context.Process(target=_process_worker, args=(pipeline, stop_at),
                             name='collector-persistence')
    pipeline.worker_process = worker
    worker.start()
    heartbeat = asyncio.create_task(pipeline.heartbeat())
    failed = False
    try:
        await pipeline.receive(stop_at, reconnect_max_seconds)
    except BaseException:
        failed = True
        collector.request_stop()
        raise
    finally:
        pipeline.finished_receiving.set()
        try:
            while worker.is_alive():
                pipeline.drain_progress()
                try:
                    pipeline.q.put_nowait(None)
                    break
                except queue.Full:
                    await asyncio.sleep(.05)
            while worker.is_alive():
                pipeline.drain_progress()
                await asyncio.sleep(.05)
            worker.join()
            pipeline.drain_progress()
            if worker.exitcode:
                failed = True
                pipeline.metrics['fatal_error'] = 'WORKER_EXIT_' + str(worker.exitcode)
        finally:
            pipeline.worker_done.set()
            await heartbeat
            final = pipeline.snapshot()
            final['state'] = 'FAILED' if failed or pipeline.metrics.get('overflow_count') or pipeline.metrics.get('fatal_error') else 'STOPPED'
            _atomic_json(pipeline.health_path, final)
            pipeline.q.cancel_join_thread()
            pipeline.q.close()
            pipeline.progress_queue.close()
            collector._db = collector._open_db()
    return 1 if failed or pipeline.metrics.get('overflow_count') or pipeline.metrics.get('fatal_error') else 0
