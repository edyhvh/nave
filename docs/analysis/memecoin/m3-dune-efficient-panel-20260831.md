DUNE PIPELINE VALIDATED WITH LIMITATIONS

# NAVE efficient Dune historical panel — 2026-08-31

This iteration recovered value from the prior completed execution, measured the
cost of compact stages, and built a reusable local-first panel path. It did not
optimize a strategy and makes no edge claim.

The canonical local artifacts are `launches.parquet`,
`token_trajectories.parquet`, `migrations.parquet`,
`pumpfun_first_hour_events.parquet`, `pumpswap_postmigration_events.parquet`,
`participant_early_episodes.parquet`, and
`participant_targeted_history.parquet`. Raw event history remains ignored by
git and is inspected only through schemas, counts, null rates, quantiles, and
small samples.

## Result recovery

The prior query `research/dune/50_windows/01_token_windows_and_outcomes.sql`
was not rerun. Its completed execution is recorded in
`data/research/dune/raw/2026-08-27/recovered_execution_metadata.json`.
The result has 701,428 rows, 33 columns, and 253,462,228 bytes, expiring
2026-11-29. Metadata, a uniform sample, and a deterministic one-mint filter
were recovered. The full export was rejected. The CLI retrieval path consumed
319 credits when it failed to honor the intended bounded fetch; the API paths
used server-side columns, filters, limits, and sampling thereafter.

## Pipeline design

Stage A reuses the complete 53,956-launch denominator. Stage B scans Pump.fun
events once for the 0–60 minute burst window. Stage C creates the small
completion/migration set. Stage D queries `dex_solana.trades` only for verified
migrated mints with Solana/project/time filters. Stage E retains high-resolution
wallet entry and same-block ordering only for bounded early participants.
Stage F performs windows, outcomes, right-censoring, trajectory descriptions,
and FIFO accounting locally.

The local helpers in `research/dune/efficient.py` enforce deterministic mint
sampling, one-row-per-mint aggregation, no landmark multiplication, explicit
right censoring, incremental checkpoints, multi-token episodes, and
point-in-time wallet history. The test suite includes these invariants.

## Acquired proof

The deterministic 1,000-mint sample has 917 tokens with first-hour trades and
1,000 token-level rows. Seven of those mints migrated. Their targeted slices
contain 2,367 Pump.fun first-hour events, 6,227 PumpSwap events, 1,786
wallet-token episodes, and 1,666 wallets. Multi-token FIFO realized-PnL is
validated, including fees and remaining inventory as separate fields. This is
not a full-cohort participant reputation result.

The local mark-return proxy has 887 resolved first-hour price rows: median
1.99%, mean 47.46%, +100% in 110 rows, +200% in 53, +500% in 19. It is a
descriptive mark proxy and not an executable-return estimate. Long-horizon
Pump.fun marks are sparse after migration, so a complete Runner panel remains
partial.

## Economics and decision

The iteration used 326.052 credits in total, ending with 636.430 included
credits remaining. The 100-mint and 1,000-mint first-hour probes cost 0.584 and
0.472 credits; the compact token panel cost 0.147. The 7-mint PumpSwap and
participant slices cost 3.601 and 1.653. Full-cohort 24h, 7d, and 30d panels
were estimated at 60–180, 420–1,260, and 1,800–5,400 credits respectively and
were not run.

Projected monthly use is 150–350 light, 900–2,400 normal, and 3,500–7,500
heavy. The recommendation is **STAY_FREE**; do not purchase credits until a
second-day cost/coverage experiment is justified. Plus is not justified.

## Remaining limitations

PumpSwap historical depth/reserves, failed exits, priority fees, Jito bundles,
wallet funding/sybil identity, BOOST/generated-flow attribution, and complete
participant history remain missing. Helius is useful later for independent
validation but is not needed now. BNB/Four.meme is not yet lifecycle-sufficient;
Base/Clanker is a promising partial future adapter; TON is currently
insufficient. No live trading, wallets, signatures, notifications, OpenClaw
changes, Sim, Helius, or other paid provider were used.
