# NAVE source capability matrix

This matrix is a research-data source decision, not an execution-provider decision. NAVE remains read-only and human-gated.

| Requirement | Dune | PumpApi Historical Replay | Local derived | Helius later | Current decision |
|---|---|---|---|---|---|
| Launch denominator | Strong, compact SQL | Available through CREATE events but expensive to discover | Deterministic sampling | Not needed | Dune denominator, local sample |
| Early Pump.fun trades | Strong semantics, expensive at broad raw scale | Strong overlap proof on 6,641 rows | Normalize/partition | Not needed | Hybrid |
| Wallet identity | Strong in Dune trade table | Strong when `breakdown[].trader` is singular; ambiguous otherwise | Preserve ambiguity | Not needed | Hybrid with quality flags |
| Reserves | Strong for Pump.fun fields | Strong for observed pool fields; aliases require normalization | Derive curve state | Useful later for account-level validation | Hybrid |
| Migration | Strong targeted event queries | MIGRATE events observed | Build migration map | Not needed | Dune + PumpApi cross-check |
| PumpSwap continuation | Targeted Dune is preferred | Available, but not yet audited for NAVE | Trajectory derivation | Useful later for depth validation | Dune targeted until audited |
| Priority fee | Not part of current compact panel | Present in archive schema | Derive only when retained | Not needed | Future optional field |
| Failed transactions | Limited for successful event archive | Not a reliable failed-tx source | Unknown | Useful later | Helius later if needed |
| Bundles | Possible heuristics only | Millisecond timing / grouping only | Label POSSIBLE_BUNDLE | Useful later for confirmation | Never confirmed from heuristic |
| Funding chains | Not in current panel | Not in current panel | Unknown | Useful later | Defer |
| BOOST attribution | Unknown | Mayhem/cashback fields, not BOOST attribution | Unknown | Useful later | UNKNOWN |
| Historical depth/liquidity | Limited | Pool/reserve observations, not full executable depth | Partial proxies | Useful later | UNKNOWN where absent |
| Participant history | Targeted historical queries | Replay can provide bounded history but high bandwidth | Point-in-time Beta-Binomial | Useful later for funding/economic clusters | Targeted only |

## Provider interpretation

The 2026-08-28 21:00 UTC overlap had 6,641/6,641 transaction-signature matches and 6,641/6,641 mint matches. Singular economic-wallet matches were 6,634/6,641. Four side differences were concentrated in one mint and remain a semantic discrepancy requiring follow-up; 67 additional CREATE rows are a known Dune lifecycle representation difference. Seven wallet identities were intentionally left ambiguous because PumpApi exposed multiple breakdown traders. Amount and reserve mismatches were retained for audit rather than silently reconciled.

PumpApi Historical Replay is therefore `PUMPAPI_VALID_WITH_LIMITATIONS` for early-event research, not a canonical replacement for every Dune field. Dune remains the compact denominator, migration, and targeted continuation source.

The replay source is historical data only. The Trade API, wallet functionality, signing, and execution endpoints are out of scope.
