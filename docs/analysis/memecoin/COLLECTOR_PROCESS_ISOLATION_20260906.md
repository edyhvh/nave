# Failed gate and local processing repair

Operational evidence only; no strategy, validation or holdout outcome inspection.

Gate `collector-health-20260906-b98c89a-01` failed its frozen contract.
Maximum queue depth reached 4096, queue age 5.7205 seconds and overflow stopped
collector PID 2442775 around 11:00 UTC. The queue drained accepted frames;
one overflow frame was explicitly unpersisted. The missing interval stays
INCOMPLETE. The failed gate and samples remain preserved in the runtime health path.

## Evidence and diagnosis

At 11:00:09 the input rate was approximately 1095.5 frames/second while
processing achieved 358.9. Process CPU increased from 739.622 to 749.807 seconds
across the preceding ten-second sample interval. Provider event age stayed
below 2.113 seconds and reconnect count was zero. Batch wall time rose to
0.3298 seconds, of which SQLite commit was 0.037 and JSONL fsync 0.0324.
The preceding thread-based receiver and Python consumer shared one GIL.
These observations support CPU_PROCESSING_BACKLOG under burst traffic, not
provider unreliability. Process isolation removes that shared execution lock;
whether its capacity is sufficient is deliberately left to the unchanged gate.

## Scoped repair

Keep the receiver in the parent and move the sole ordered normalization,
participant expansion and durable writer into a child process. Linux fork is
allowed only at single-threaded startup, before networking/executor threads.
Close SQLite before fork and open it only in the writer child during ingestion.

Bounded interprocess queues retain the existing 4096-frame/32-MiB admission
limits. Pending byte AND frame counts include in-flight batches until durable
acknowledgement. Progress telemetry is bounded to 64 batch messages. Fault
records and the stop sentinel share the ordered frame pipe; shutdown drains
accepted frames. Dead writer detection stops reception and reports FAILED.
Unclean writer termination leaves reconciliation markers intact.

No fields, dedupe semantics, SQLite FULL durability, batch sizes, health limits,
frozen dates, outcome horizons or scientific contracts changed. New worker
PID/CPU/RSS metrics distinguish receiver and writer resource consumption.

## Verification

The first process-isolated startup (`edab5de`, PID 2447893) still overflowed
at approximately 11:36 UTC; no stability gate was launched for it. Its final
snapshot is archived as `PROCESS_ISOLATION_STARTUP_FAILED.json`. This falsified
the claim that GIL separation alone supplied enough capacity.

A bounded live-worker cProfile (2216 warmup frames, 3.705 seconds profiled)
located 1.433 seconds in SQLite statement execution, versus 0.215 commit,
0.187 fsync, 0.566 normalization and 0.146 participant expansion. The live
dedupe database was 709251072 bytes. A separate temporary-database sample
processed 2000 frames in 1.492 seconds, with only 0.069 seconds SQLite execute.
This isolates production-scale database access as the main remaining cost;
it does not establish provider failure or SQLite lock contention.

The additional scoped repair removes the redundant `UPDATE events` by inserting
the final output path directly with the original dedupe insert. The writer's
SQLite page cache is explicitly bounded at 128 MiB instead of the ~2 MiB
default to reduce index-page churn. Available host memory exceeded 5 GiB.
Schema, keys, transaction ordering, FULL synchronization and fsync are unchanged.
Tests assert bounded cache configuration and persisted output-path equivalence.
The temporary profiler emits function timings only and is removed from the
collector launch command before stability acceptance.

18 focused collector/runtime/health tests passed, including real child-process
drain/dedupe, separate worker PID, and abrupt worker exit failing closed.
Ruff and git diff --check passed. Synthetic test fixtures are not production
validation data. A fresh detached 1800-second gate is required; a short startup
snapshot is not stability acceptance. Warmup gaps cannot be marked complete.
