# Collector receive/persistence repair

Scope: operational prospective capture only. NO EDGE VALIDATED and both frozen experiments/dates remain unchanged. No strategy, P&L, validation/holdout outcome inspection, provider switch, paid data, Hermes restart, or Quant migration.

## Proven cause

SYNCHRONOUS_PERSISTENCE, producing local receive backpressure. The old hot loop awaited the next WebSocket frame only after normalization, participant expansion, per-frame SQLite commit, JSONL flush, outcome polling, and checkpoint work. It could not drain the feed at arrival rate. Reconnects temporarily cleared accumulated socket data without fixing this throughput deficit.

A bounded current-warmup profile received 2,000 frames in 3.128 seconds (639 fps) and processed them in 10.543 seconds (190 fps). Inclusive measurements: SQLite commit 6.746 seconds; normalization 0.701; participant expansion including its append work 0.340; all JSONL append work 0.862; outcome polling 0.091; checkpoint 0.018; manifest 0.036. There were 4,001 commit method invocations, including no-op calls, and 1,241 participant rows. Participant expansion was not the dominant bottleneck.

Live OS snapshot: receive queue approximately 4.7 MB, process in folio_wait_bit_common at one sample, RSS about 56 MB, two threads, CPU about 39%; 24 GiB disk free and 87% inodes free. A bounded syscall summary showed writes and fsync activity. There is no evidence of a permanent SQLite lock, exhausted disk/inodes, outcome-job backlog as the root cause, or provider-wide inactivity. Kernel NIC-to-userspace latency was not directly measured; an established socket alone is not health. Provider-side reasons for silent streams are not claimed as proven.

## Repair and measurement boundaries

WebSocket receipt → bounded frame/byte queue → one serialized processing/persistence worker. The local receive clock is assigned immediately after ws.recv, before JSON parsing, normalization, expansion, or queueing. Kernel packet-arrival time is unavailable and explicitly distinguished from application-frame receipt. Provider timestamp is separately exposed; no receive timestamp is backdated from provider time.

Queue capacity: 4,096 frames AND 32 MiB including in-flight batches. Exceeding either bound records BACKPRESSURE_OVERFLOW and the unpersisted frame count, stops ingestion, drains already accepted work where possible, and leaves the affected interval INCOMPLETE. No silent dropping or overwriting. A single worker owns the SQLite connection after initialization; check_same_thread=False permits that ownership transfer, not concurrent SQL writers.

Batches contain at most 256 frames, gathered for at most 100 ms. JSONL handles are buffered within a batch, then flushed/fsynced before a single SQLite FULL transaction commit. SQLite synchronous mode is unchanged. A durable IN_FLIGHT/COMMITTED marker brackets each batch. An abrupt stop can leave keyed JSONL tails before dedupe commit; restart records mandatory reconciliation instead of silently accepting them as complete. Existing committed dedupe survives restart. No truncation, historical record deletion, or exactly-once JSONL claim is made.

Heartbeat is independent of the persistence worker. Telemetry includes frame and participant rates, queue depth/bytes/oldest age and high-water marks, provider/local-receive/processed/durable/checkpoint clocks, processing and persistence latency/high-water marks, stage timing, fsync/commit time, batch time, outcome backlog and snapshot counts, connection age/reconnects, receiver hot-path time, event-loop delay, CPU/RSS and FD count. Outcome capture remains in the ordered worker with its original two horizons and clock cutoffs. It cannot block WebSocket receipt directly. Expensive integrity hashes remain at shutdown, outside the receive hot path; closed files are pending reconciliation, not automatically complete hours.

The status command reads only operational health/lock/checkpoint files. It no longer counts lines in outcome snapshots. Health states distinguish HEALTHY, DEGRADED_BACKLOG, PROVIDER_STALLED, RECOVERING and FAILED. Missing/stale telemetry fails closed. A receive silence deadline only responds to missing receipt, never high persistence lag; queue growth is a separate local failure.

## Bounded post-change profile

A separate 2,000-frame current-warmup sample arrived in 3.769 seconds (531 fps) and processed in 2.333 seconds (857 fps) under profiling. SQLite commit time was 0.073 seconds across nine invocations, normalization 0.514, participant expansion 0.178, all JSONL append work 0.259, checkpoint 0.006, and outcome polling 0.010. All 1,182 participant rows were retained. The two profiles used different live frames and are throughput evidence, not an identical replay comparison or a stability result. Temporary profiling captures were isolated under /tmp/collector-profile-* as DRY_RUN_ONLY and did not alter production cursor/dedupe state or inspect validation/holdout outcomes.

## Frozen acceptance

research/nave/experiments/collector-health-gate-v1.json freezes the 1,800-second local deterministic gate before launch: 10-second samples, heartbeat ≤10 s, receive silence ≤20 s, provider event age ≤15 s, receive→process ≤5 s, receive→durable ≤8 s, queue age ≤5 s, queue depth ≤2,048, checkpoint age ≤15 s, recovery ≤30 s, at most two reconnects and two consecutive unhealthy samples. These operational limits are not strategy thresholds and will not be loosened after failure.

scripts/memecoin_collector_stability_gate.py reads operational metrics, lock and frozen-contract hashes only. It rejects short intervals, missing samples, stagnant counters, stale timestamps, excessive latency/backlog, reconnect loops, overflows, source/PID changes and lock/contract changes. It produces streaming samples and final PASS/FAIL under the ignored prospective/health path. Its sampled p95 is explicitly an estimate of batch maximum latency, not an exact per-frame percentile; cumulative maxima enforce the hard latency bounds.

The detached result—not this throughput profile—is the authority for the next session. Full launch metadata and continuation instructions are in /home/david/MEMECOIN_COLLECTOR_STABILITY_CONTINUATION.md.
