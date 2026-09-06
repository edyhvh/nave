# Memecoin snapshot and cache contract

Discovery is research-only. Supply `--input-file` containing a rows array; it is not a live autonomous scanner.

Each row requires explicit `chain_id` (`eip155:<chain number>` or `solana:mainnet`), `contract_address` or `mint`, timezone-aware `decision_time` and `available_at`, and its observed features. Symbols are display labels, never join keys. Outcomes must carry the same identity and decision time plus a later `observed_at`. Duplicate identities at a decision time are rejected. Nonfinite values and unknown/late availability do not produce valid setups. Optional `feature_available_at` must contain no unknown or late supplied clocks; an aggregate clock is an assertion about every feature, not permission to include later narrative data.

Case studies require explicit `case_study_source`; PONS is not a default. EVM or Solana address syntax validation is not proof of official token identity, mint authorities, ownership, liquidity, or safety. Other ecosystems remain unsupported and fail closed.

Dune materialization locks check/run/write, keys caches by query text fingerprint and requested row limit, and defaults to a 24-hour freshness limit. A stale/incompatible cache requires explicit `--force`, not automatic paid refresh. Invalid responses preserve existing cache. Reported row counts are not proof of full-universe coverage. Dune `--limit` limits returned rows, not compute credits: perform the existing fresh-usage budget preflight before execution. No credits are purchased by this workflow.
