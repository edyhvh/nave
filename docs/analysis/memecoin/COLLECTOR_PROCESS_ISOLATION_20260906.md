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

18 focused collector/runtime/health tests passed, including real child-process
drain/dedupe, separate worker PID, and abrupt worker exit failing closed.
Ruff and git diff --check passed. Synthetic test fixtures are not production
validation data. A fresh detached 1800-second gate is required; a short startup
snapshot is not stability acceptance. Warmup gaps cannot be marked complete.
