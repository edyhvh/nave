"""Deterministic operational acceptance; never opens event/outcome data."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import time

from research.nave.prospective_runtime import age, health_reasons, durable_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_sample(root: Path, contract: dict, pinned: dict):
    now = datetime.now(UTC)
    sample = {'sampled_at': now.isoformat(), 'violations': [], 'lock_intact': False}
    try:
        metrics = json.loads((root / 'runtime-health.json').read_text())
        lock_path = root / 'holdout-lock.json'
        lock = json.loads(lock_path.read_text())
        sample['lock_intact'] = (sha(lock_path) == pinned['lock_sha256']
            and lock.get('status') == 'HOLDOUT_LOCKED'
            and not (root / 'holdout-unlock.json').exists())
        sample['metrics'] = metrics
        sample['violations'] = health_reasons(metrics, contract, now)
        if not sample['lock_intact']:
            sample['violations'].append('HOLDOUT_LOCK_CHANGED')
        for path, digest in pinned['scientific_contracts'].items():
            if sha(Path(path)) != digest:
                sample['violations'].append('SCIENTIFIC_CONTRACT_CHANGED')
        if sha(Path(pinned['health_contract_path'])) != pinned['health_contract_sha256']:
            sample['violations'].append('HEALTH_CONTRACT_CHANGED')
        if metrics.get('health_contract_sha256') != pinned['health_contract_sha256']:
            sample['violations'].append('COLLECTOR_HEALTH_CONTRACT_MISMATCH')
        if metrics.get('collector_revision') != pinned['collector_revision']:
            sample['violations'].append('COLLECTOR_REVISION_CHANGED')
        if metrics.get('collector_pid') != pinned['collector_pid']:
            sample['violations'].append('COLLECTOR_PID_CHANGED')
        os.kill(pinned['collector_pid'], 0)
        if metrics.get('state') != 'HEALTHY':
            sample['violations'].append('STATE_' + str(metrics.get('state')))
        for field in ('strategy_analysis_performed', 'validation_outcomes_inspected', 'holdout_outcomes_inspected'):
            if metrics.get(field) is not False:
                sample['violations'].append(field.upper())
        for field in ('heartbeat_at', 'last_local_receive_at', 'last_checkpoint_at'):
            sample[field + '_age_seconds'] = age(metrics.get(field), now)
        sample['provider_event_age_seconds'] = age(metrics.get('last_provider_event_at'), now)
        # Reject nonfinite/malformed numeric telemetry rather than accepting NaN comparisons.
        for field in ('frames_received', 'frames_processed', 'frames_durable', 'queue_depth',
                      'receive_to_process_seconds', 'receive_to_persist_seconds',
                      'oldest_queue_age_seconds', 'event_loop_delay_seconds', 'reconnects'):
            value = metrics.get(field)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                sample['violations'].append('INVALID_METRIC_' + field)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sample['violations'].append('OPERATIONAL_READ_FAILED:' + type(exc).__name__)
    return sample


def summarize(samples, contract, pinned, elapsed):
    def number(mapping, field):
        value = mapping.get(field)
        return value if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 else 0
    failures = set()
    consecutive = unhealthy = 0
    previous = None
    recovery_started = None
    durations = []
    for sample in samples:
        stamp = datetime.fromisoformat(sample['sampled_at'])
        violations = sample['violations']
        if violations:
            unhealthy += 1
            consecutive += 1
        else:
            consecutive = 0
        if consecutive > contract['maximum_consecutive_unhealthy_samples']:
            failures.add('CONSECUTIVE_UNHEALTHY_SAMPLES')
        if sample.get('metrics', {}).get('connection_state') != 'CONNECTED':
            recovery_started = recovery_started or stamp
        elif recovery_started:
            if (stamp-recovery_started).total_seconds() > contract['reconnect_recovery_deadline_seconds']:
                failures.add('RECONNECT_RECOVERY_DEADLINE')
            recovery_started = None
        if recovery_started and (stamp-recovery_started).total_seconds() > contract['reconnect_recovery_deadline_seconds']:
            failures.add('RECONNECT_RECOVERY_DEADLINE')
        for reason in violations:
            if reason in ('HOLDOUT_LOCK_CHANGED', 'SCIENTIFIC_CONTRACT_CHANGED',
                          'HEALTH_CONTRACT_CHANGED', 'COLLECTOR_HEALTH_CONTRACT_MISMATCH',
                          'COLLECTOR_REVISION_CHANGED', 'COLLECTOR_PID_CHANGED',
                          'BACKPRESSURE_OVERFLOW', 'FAILED') or reason.startswith((
                              'INVALID_METRIC_', 'OPERATIONAL_READ_FAILED:',
                              'STRATEGY_', 'VALIDATION_', 'HOLDOUT_', 'STATE_FAILED', 'STATE_STOPPED')):
                failures.add(reason)
        if previous:
            if (stamp-datetime.fromisoformat(previous['sampled_at'])).total_seconds() > contract['max_sample_gap_seconds']:
                failures.add('VALIDATOR_SAMPLE_GAP')
            for field in ('frames_received', 'frames_processed', 'frames_durable', 'reconnects'):
                if number(sample.get('metrics', {}), field) < number(previous.get('metrics', {}), field):
                    failures.add('COUNTER_REGRESSION:' + field)
        previous = sample
        value = sample.get('metrics', {}).get('receive_to_persist_seconds')
        if isinstance(value, (int, float)) and math.isfinite(value):
            durations.append(value)
    if elapsed < contract['duration_seconds']:
        failures.add('SHORT_INTERVAL')
    if len(samples) < contract['duration_seconds']/contract['sample_interval_seconds']:
        failures.add('INSUFFICIENT_SAMPLES')
    if unhealthy/max(len(samples), 1) > contract['max_unhealthy_fraction']:
        failures.add('UNHEALTHY_SAMPLE_FRACTION')
    first = samples[0].get('metrics', {}) if samples else {}
    last = samples[-1].get('metrics', {}) if samples else {}
    def maximum(field, nested=True):
        values = [(s.get('metrics', {}) if nested else s).get(field) for s in samples]
        return max((v for v in values if isinstance(v, (int, float)) and math.isfinite(v)), default=None)
    advanced = {}
    for field in ('frames_received', 'frames_processed', 'frames_durable'):
        advanced[field] = number(last, field) - number(first, field)
        if advanced[field] <= 0:
            failures.add('NO_PROGRESS:' + field)
    checkpoint_advanced = first.get('last_checkpoint_at') != last.get('last_checkpoint_at')
    if not checkpoint_advanced:
        failures.add('NO_CHECKPOINT_PROGRESS')
    reconnects = number(last, 'reconnects') - number(first, 'reconnects')
    if reconnects > contract['max_reconnects']:
        failures.add('REPEATED_RECONNECT_LOOP')
    for field, limit in (('max_receive_to_process_seconds', 'max_receive_to_process_seconds'),
                         ('max_receive_to_persist_seconds', 'max_receive_to_persist_seconds'),
                         ('max_queue_depth', 'max_queue_depth'),
                         ('max_queue_age_seconds', 'max_queue_age_seconds')):
        value = maximum(field)
        if value is None or value > contract[limit]:
            failures.add(field.upper())
    return {
        'status': 'FAIL' if failures else 'PASS',
        'run_id': pinned['run_id'], 'started_at': pinned['started_at'],
        'completed_at': datetime.now(UTC).isoformat(),
        'duration_seconds': elapsed, 'required_duration_seconds': contract['duration_seconds'],
        'health_contract_sha256': pinned['health_contract_sha256'],
        'collector_revision': pinned['collector_revision'], 'collector_pid': pinned['collector_pid'],
        'samples': len(samples),
        'heartbeat': {'max_age_seconds': maximum('heartbeat_at_age_seconds', False)},
        'receiver': {'max_event_age_seconds': maximum('provider_event_age_seconds', False),
                     'frames_received': advanced['frames_received']},
        'processing': {'frames_processed': advanced['frames_processed'],
                       'max_queue_depth': maximum('max_queue_depth'),
                       'max_queue_age_seconds': maximum('max_queue_age_seconds')},
        'persistence': {'p95_receive_to_persist_seconds': sorted(durations)[int(.95*(len(durations)-1))] if durations else None,
                        'p95_method': 'upper-batch-latency sampled every contract interval; not per-frame exact percentile',
                        'max_receive_to_persist_seconds': maximum('max_receive_to_persist_seconds'),
                        'writes_advanced': advanced['frames_durable'] > 0},
        'checkpoint': {'advanced': checkpoint_advanced, 'max_age_seconds': maximum('last_checkpoint_at_age_seconds', False)},
        'connections': {'reconnects': reconnects, 'stalls': sorted({s.get('metrics', {}).get('last_stall_at') for s in samples
                            if s.get('metrics', {}).get('last_stall_at')})},
        'holdout_lock_intact': bool(samples) and all(s['lock_intact'] for s in samples),
        'strategy_analysis_performed': False, 'validation_outcomes_inspected': False,
        'holdout_outcomes_inspected': False, 'failure_reasons': sorted(failures),
        'observed_criterion_violations': sorted({v for s in samples for v in s['violations']}),
    }


def run_gate(root: Path, contract_path: Path, run_id: str):
    contract = json.loads(contract_path.read_text())
    output = root / 'health' / run_id
    output.mkdir(parents=True, exist_ok=False)
    metrics = json.loads((root / 'runtime-health.json').read_text())
    scientific_root = Path(__file__).parent / 'experiments'
    pinned = {'run_id': run_id, 'started_at': datetime.now(UTC).isoformat(),
              'validator_pid': os.getpid(), 'collector_pid': metrics['collector_pid'],
              'collector_revision': metrics['collector_revision'],
              'health_contract_path': str(contract_path.resolve()),
              'health_contract_sha256': sha(contract_path),
              'lock_sha256': sha(root / 'holdout-lock.json'),
              'scientific_contracts': {str(scientific_root / name): sha(scientific_root / name)
                  for name in ('closed-day-participant-history-v1.json', 'bundle-adjusted-unique-demand-v1.json')}}
    durable_json(output / 'run.json', pinned)
    samples = []
    start = time.monotonic()
    deadline = start + contract['duration_seconds']
    next_sample = start
    with (output / 'samples.jsonl').open('x') as handle:
        while True:
            sample = read_sample(root, contract, pinned)
            # Invalid telemetry fails above, but must not prevent a FAIL artifact.
            sample = json.loads(json.dumps(sample), parse_constant=lambda _: None)
            samples.append(sample)
            handle.write(json.dumps(sample, allow_nan=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
            now = time.monotonic()
            if now >= deadline:
                break
            next_sample += contract['sample_interval_seconds']
            time.sleep(max(0, min(next_sample, deadline)-now))
    result = summarize(samples, contract, pinned, time.monotonic()-start)
    durable_json(output / 'result.json', result)
    return result
