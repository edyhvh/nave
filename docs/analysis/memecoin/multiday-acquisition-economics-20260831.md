# NAVE multi-day acquisition economics

## Comparison

| Architecture | Dune credits | Network/storage profile | Completeness | Decision |
|---|---:|---|---|---|
| Dune-only raw events | High and unpredictable at broad scale | Low local transfer, high provider cost | Good where query completes | Reject as default |
| PumpApi-only | 0 provider credits | ~13.5 GB compressed/day at the measured date; stream-only local retention | Early-event coverage promising; continuation not yet audited | Use only after one-day gate |
| Hybrid | Compact Dune denominator/migrations plus PumpApi early events | Network-heavy but low Dune cost; local compact Parquet | Best current division of labor | Recommended |

## Current evidence

The one-hour overlap consumed no new Dune credits and showed complete signature/mint overlap for 6,641 Dune rows. Wallet agreement was 99.895% after using singular `breakdown[].trader`; four CREATE rows required a known side-semantic mapping and seven ambiguous multi-trader events were left unknown. That is adequate for `PUMPAPI_VALID_WITH_LIMITATIONS` for early events, with field-level caveats.

## Recommended steady state

Use Dune for daily launch denominators, deterministic sample manifests, verified migrations, and targeted PumpSwap continuation. Use PumpApi Historical Replay for streamed early-event acquisition, retaining normalized Parquet only for the deterministic launch sample and all verified migrants. Use DuckDB/local Python for features, outcomes, matching, temporal splits, and quality reports. Defer Helius until a specific unresolved field—failed exits, account-level depth, funding chains, or confirmed bundles—blocks a result.

The 14-day target remains conditional. The one-day pipeline must finish with stable schema, checkpoints, output hashes, and usable selected-token coverage before any 3-day pilot. No Dune credit purchase or upgrade is justified.
