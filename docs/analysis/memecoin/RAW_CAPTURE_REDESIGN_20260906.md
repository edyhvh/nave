# RESEARCH_COLLECTOR_REDESIGN_PENDING

The third gate failed. It is not a core Abi/Hermes production dependency.
No fourth gate on the previous pipeline, larger queue, relaxed health limit,
new provider, paid research, or experiment-contract/date change is authorized
by this implementation. Memecoin recommendation jobs remain disabled.

## Existing storage assessment

Existing events.jsonl is normalized evidence, not lossless raw capture:
`source_raw_event_retained` is false. It cannot reconstruct discarded provider
fields. Its receipt-to-durable acknowledgement also waits on SQLite, expansion
and downstream work. It cannot meet the new capture contract unchanged.

Local append-only storage is the first implementation choice. There is no
evidence requiring Redis/Kafka or a provider switch. The new
`research/nave/raw_capture_spool.py` supplies an independently testable storage
primitive, NOT a deployed collector:

    receive -> bounded raw-only writer -> fsync acknowledgement
    sealed spool -> replay -> existing normalization/participants/dedupe
                 -> existing outcome/checkpoint work -> durable replay cursor

The raw envelope retains exact provider bytes, local receive/available UTC
clock, deterministic SHA-256 identity and schema. All provider timestamp,
signature, slot, mint, pool, participants and deployer fields remain losslessly
inside the original bytes. No participant parsing, SQLite call, outcome work
or full-file hashing occurs in capture append. SHA-256 is per raw frame, not
a growing-file scan. UTF-8 payloads and exact non-UTF-8 bytes remain lossless.

Acknowledgement follows file AND containing-directory fsync. One writer holds
an exclusive filesystem lock. Segments and aggregate bytes are bounded;
filesystem free-space reserve is checked before writes. Capacity failure is
INCOMPLETE and never deletes old evidence. Failed writes prevent subsequent
acknowledgement until reconciliation. Replay validates framing, identity and
receive/available clocks; a corrupt/partial tail stops replay, not skips it.
Restart opens a new numbered segment without truncating earlier evidence.

## Required integration before any new stability gate

- Connect the WebSocket receiver only to the raw writer and release admission
  only after its fsync receipt. Keep frame/byte queues bounded; explicit
  overflow remains incomplete. Do not wait on downstream durable receipts.
- Seal segments with durable metadata. On restart, reconcile any active tail
  before treating it as sealed. The current primitive's reader MUST NOT read
  a concurrently written segment.
- Persist downstream cursor atomically after SQLite/dedupe and checkpoint
  commit. Restart before cursor commit intentionally replays and dedupes;
  never advance a cursor before durable processing. Existing primitive yields
  offsets but the consumer/cursor integration is still pending.
- Keep raw-capture lag, raw durable counts, processing lag, pending spool bytes,
  oldest pending capture, corruption, disk reserve and checkpoint health
  separate. Slow indexing cannot be called failed capture unless raw receipt
  actually failed, and captured data cannot be called analyzed or complete.
- Validate capture under synthetic bursts, fsync failure and forced restart;
  verify causal replay uses original receive clocks, not replay wall time.
- Measure storage footprint and whole-window capacity before live deployment.
  Approximately 18 GiB free was observed; this is NOT demonstrated sufficient
  for six days of lossless capture. No historical evidence may be removed to
  manufacture space or completeness. Compression/capacity decisions remain
  an explicit deployment gate.
- Freeze a distinct operational contract that separately reports raw capture
  and downstream lag. Preserve the old failed gate/results and do not claim
  its limits were met by changing metric definitions.

21 focused tests pass, including fsync failure, lossless bytes/clock, stable IDs, exclusive
writer, restart replay, cursor offset and fail-closed capacity/corrupt tail.
The normal collector remains stopped. No outcome data was inspected.

Validation still starts September 7 UTC. If the fully integrated raw capture
cannot be prospectively stable before then, WINDOW_REFREEZE_REQUIRED must be
reported; a future window must be explicitly frozen before new collection.
Do not silently edit either existing experiment contract or backfill gaps.
