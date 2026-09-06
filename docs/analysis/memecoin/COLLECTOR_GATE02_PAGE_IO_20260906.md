# Gate 02: bounded SQLite page-I/O repair

Only operational metadata/function costs were inspected. Frozen health and
scientific contracts are unchanged; no validation/holdout outcomes inspected.

Gate `collector-health-20260906-d63f55e-02` completed 1800.0104 seconds with
181 samples and failed only MAX_QUEUE_DEPTH (4059 versus 2048). The receiver
remained timely (maximum provider age 2.099899 seconds), zero reconnects,
heartbeat age 2.012067 seconds, checkpoint age 7.04091 seconds. Maximum durable
latency was 4.907509 seconds and queue age 4.574327 seconds. Bursts exceeded
processing capacity; the collector subsequently overflowed and stopped at
approximately 12:17 UTC. This is not a provider-unreliability verdict.

A bounded full-worker profile isolated SQLite statements: 10.699 of 19.005
seconds for 4934 frames; queue retrieval was only 0.685 seconds. A second
bounded profile split statements: inserts consumed 9.34455 seconds wall time,
2.60793 seconds CPU (6367 calls); launch lookup consumed 0.23412 seconds
(2422 calls). An eight-second syscall summary attributed 34.98% syscall time
to pwrite64 and 24.13% to pread64. Trace output contained syscall aggregates,
not payloads or file contents. The dedupe database was 1,326,919,680 bytes.
This establishes local database insert/page-I/O cost rather than participant
expansion, queue handling or outcome scheduling as the remaining bottleneck.

## Repair

Keep the existing schema, event keys, ordered single writer, batches, FULL
synchronization, fsync and reconciliation behavior. Increase the bounded
SQLite page cache from 128 to 512 MiB and enable at most 2 GiB of demand-paged
read mapping (SQLite clamps this build to 2 GiB minus 64 KiB). This targets
index-page churn and read syscall overhead without rewriting historical data.
The host has approximately 8 GiB RAM; normal-operation memory remains subject
to verification. No threshold in collector-health-gate-v1.json was increased.

The bounded post-change profile remains dominated by inserts; it is not a
claim that all burst limits are solved. Startup profiling creates cold-cache
and execution overhead and may itself exceed admission limits. Such overflows
are explicitly recorded as INCOMPLETE, never relabeled as complete. A normal
unprofiled startup and a new detached frozen gate must establish acceptance.

## Tests and evidence preservation

18 focused collector/runtime tests pass, including unchanged FULL mode,
bounded cache and supported mmap limit, committed dedupe/participant fields,
worker failure and ordered drain. Ruff and git diff --check pass.

Original gate result and streaming samples are preserved. Subsequent failed
runtime metadata is archived as GATE02_POST_OVERFLOW_runtime-health.json under
/home/david/nave-research-archive-20260906-pre-cutover/. Bounded profiling
launchers are archival diagnostics, not the production start command. All
restart/profiling interruptions remain incomplete warmup gaps. Validation
still starts 2026-09-07T00:00:00Z; no retroactive completeness claim is made.
