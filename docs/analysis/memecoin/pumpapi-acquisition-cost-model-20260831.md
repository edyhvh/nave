# PumpApi acquisition cost model

## Measured representative hour

The representative archive was 2026-08-28 21:00 UTC, selected because its Dune overlap contained launches and 6,641 Dune early-event rows. The archive listing reported 608,173,816 compressed bytes. Streaming zstd decompression produced 3,949,203,772 bytes and 3,042,273 JSONL events. The corrected parser retained 12,032 events for 1,000 selected mints.

The optimized streaming run took 97.54 seconds, used 19,584 kB peak resident memory, and retained approximately 14.2 MB of normalized JSONL. No raw decompressed archive was retained.

## Linear planning estimates

These are planning estimates from the representative hour, not guarantees. They assume 24 archives per day and one serial parser process.

| Scope | Compressed network | Decompressed traversal | Retained selected-event JSONL, approximate | CPU time |
|---|---:|---:|---:|---:|
| 1 hour | 0.608 GB | 3.949 GB | 0.014 GB | 0.027 h |
| 1 day | 13.488 GB observed listing | 94.8 GB estimated | 0.34 GB estimated | 0.65 h |
| 3 days | 40.464 GB estimated | 284.3 GB estimated | 1.02 GB estimated | 1.95 h |
| 14 days | 188.832 GB estimated | 1,326.9 GB estimated | 4.75 GB estimated | 9.50 h |

The archive directory for 2026-08-28 contained all 24 hourly files with total compressed size 13.488 GB. Archive sizes vary, so the 14-day estimate is a planning range rather than a storage guarantee.

## Safety decision

Streaming is operationally possible with the measured 49 GB free space because only one compressed hour is held in flight and raw decompression is discarded. A 14-day replay is nevertheless expensive in network transfer and wall-clock processing. It should not be started until the one-day gate completes and retained Parquet quality is verified. The first-day gate is the highest-information next acquisition; Dune raw extraction is not a substitute.

## Reproducibility controls

Each hour must have a checkpoint, source URL, archive size where available, parser metrics, output hash, and a status of `NOT_STARTED`, `DOWNLOADED`, `PARSED`, `VERIFIED`, `PARQUET_WRITTEN`, `COMPLETE`, `FAILED`, or `MISSING_ARCHIVE`. Processed compressed archives may be discarded after output verification.
