# Solana and TON asymmetric discovery pipeline

As of: 2026-08-21T12:19:01+02:00
Status: research/admission contract only; read-only; no execution or wallet access.

## Objective and research definition

Hypothesis: short-horizon Solana and TON/Gram assets can occasionally offer
positive asymmetry, but only after contract, distribution, market-integrity,
and exit-capacity evidence eliminates predictable permanent-loss paths.
A scan that finds no admissible setup is a successful result.

Market and instruments:

- Solana SPL and Token-2022 fungible tokens, initially discovered from public
  launch and DEX feeds.
- TON Jetton masters and their corresponding Jetton wallets. TON uses a master
  contract plus per-holder wallet contracts, so identity and holder analysis
  must resolve the master/wallet relationship rather than treating every token
  contract as one ERC-20-like address.[8]
- Verify TON asset identity against the canonical master address and trusted
  asset metadata rather than symbol/name alone.[6]
- Spot research only. No leverage, perpetuals, options, borrowing, bridging,
  swaps, signing, approval, or custody automation.

Timeframe and evaluation:

- Discovery refresh: 5-15 minutes for newly active assets; slower sources carry
  their own observed-at timestamp and freshness limit.
- Setup: 1h trigger with a maximum 24-72h thesis horizon, declared per asset.
- Promotion path: discovery -> normalized evidence -> hard safety gates ->
  market-integrity gates -> risk plan -> WATCH -> trigger-confirmed ENTER
  candidate -> human decision.
- Validation: forward-only outcome journal. Measure availability, gate rejection
  rates, false-pass safety incidents, quote-to-realized slippage where a human
  later records a fill, maximum adverse/favourable excursion, expectancy after
  fees, drawdown, and outcome by chain/regime. Research candidates are not
  validated setups until enough forward observations exist.

## Audit of existing Nave work

| Existing component | Useful evidence | Integrity gap |
|---|---|---|
| `docs/analysis/memecoin/plan.md` | Solana-only scope, read-only intent, $25k liquidity floor, holder thresholds | No TON path, unlock/custody/fake-volume/manipulation gates, complete risk plan, or valid no-setup contract |
| `trading/memecoin/data_provider.py` | Helius metadata/largest token accounts, Pump.fun discovery, DexScreener market snapshot, Jupiter sell quote | Provider errors collapse to `None`/empty; no source-level completeness or freshness manifest |
| `trading/memecoin/safety_check.py` | Mint/freeze authority, holder concentration, route and LP fields | Empty holder data currently becomes 0% concentration; a DEX pair with liquidity is labelled `locked` without lock/burn proof; buy simulation is inferred from market presence; Token-2022 transfer fees/delegates/hooks are not parsed |
| `trading/memecoin/scoring.py` | Explainable FDV/turnover/liquidity/momentum/age score | Volume is treated as genuine without maker/trade/cross-venue checks; score is not an admission gate |
| `trading/memecoin/recommend.py` | Small nominal risk budget and class cap | `enter_now=True` can be emitted without entry zone, invalidation, actual stop distance, maximum loss, exit capacity, targets, time stop, monitoring, or unlock evidence |
| `trading/memecoin/archive.py` | Scan snapshots and first/repeat appearance | No decision/outcome lifecycle or later price/path attribution |

The existing Solana scanner is therefore a source adapter/research candidate
generator, not a validated setup engine. Its current PASS/GOOD and
`enter_now=True` outputs must not be treated as ENTER decisions.

## External protocol facts that change the gates

- Solana Token-2022 can apply a fee to every transfer, retain withheld fees,
  and let an authority update a later fee configuration; route existence alone
  does not establish acceptable round-trip mechanics.[1]
- A Solana permanent delegate can authorize transfers and burns for any token
  account of that mint, so mint/freeze authority checks are insufficient.[2]
- A freeze authority can block transfers, burns, and delegate changes for a
  token account.[3]
- `getTokenLargestAccounts` is only an RPC primitive for the largest token
  accounts; Nave must resolve account owners, pools, lockers, treasury, and
  related-wallet clusters before interpreting holder concentration.[4]
- A Jupiter quote is evidence that the routing engine found a route with quoted
  amounts and price impact; it is not a signed simulation and does not prove
  that a round trip can execute without transfer hooks, taxes, state changes,
  or material price impact.[5]
- A TON Jetton may remain mintable under an admin-controlled master contract;
  mintability and admin state are hard authority evidence.[7]
- DEX Screener exposes pair snapshots including market fields, but a single
  aggregator snapshot is not proof of genuine volume, locked liquidity, or
  executable depth.[9]

## Reproducible workflow

### 1. Freeze the run manifest

Persist before filtering:

- `run_id`, schema/policy version, chain, started/finished timestamps and timezone;
- source endpoint, query parameters, page/cursor, requested/received counts,
  HTTP/RPC status, retry count, block/slot or masterchain sequence where available;
- raw response content hash or immutable cache path;
- coverage state: `complete`, `partial`, `failed`, plus source errors;
- threshold set and intended risk budget.

A source failure is never an empty universe. A run can claim `no_valid_setup`
only when every required source and every discovered candidate reached a
terminal gate result.

### 2. Normalize identity before ranking

Common identity fields: chain, canonical asset address, token program/standard,
symbol/name as untrusted labels, decimals, supply, creation/deployment
transaction, deployer/admin/update authorities, and official/verified-list
status. Deduplicate by canonical chain + address, never symbol.

Solana adapters must distinguish legacy SPL from Token-2022 and enumerate all
mint/account extensions. TON adapters must resolve Jetton master code/data,
admin, total supply, wallet code, and prove sampled wallet addresses derive
from that master. Metadata or social claims cannot override an address mismatch.

### 3. Cheap universe and liquidity prefilter

Record, do not infer:

- deepest verified native pool and quote asset;
- pool reserves and ownership/lock/burn evidence;
- executable two-way quotes at the proposed position and exit clip sizes;
- price impact, route, transfer fee/tax, protocol fee, priority/gas fee,
  spread and conservative slippage;
- 5m/1h/24h volume, trades, unique makers and cross-source consistency.

The configurable floor is the greater of the absolute floor and the depth
needed to exit the maximum position in bounded clips. A displayed USD
liquidity number alone cannot pass this gate.

### 4. Chain-specific hard safety

Solana:

- parse mint, freeze, close, metadata-update, transfer-fee/withdraw,
  permanent-delegate, transfer-hook, default-frozen, non-transferable and
  confidential/pausable authorities/extensions;
- resolve top accounts to owners and exclude only independently verified pool,
  locker, burn and treasury addresses;
- cluster creator/funder/update-authority/early-buyer wallets; inspect mint,
  sell, liquidity add/remove and authority-change history;
- verify pool-lock/burn state on chain; a pair address is not lock evidence;
- obtain buy and sell quotes for exact proposed sizes and, where a read-only
  simulator supports it, simulate both legs without signing.

TON:

- verify Jetton master identity, code hash/implementation, total supply,
  mintability, admin address and admin-change history;
- derive/verify Jetton wallet contracts from the master; reject counterfeit
  wallets and mismatched metadata;
- resolve deployer/admin/funder relationships and holder concentration;
- verify pool contracts, LP custody/lock state, reserve changes and two-way
  quotes on the selected TON DEX;
- classify custom wallet/master code, transfer restrictions, unexpected fees
  or unverified behavior as unknown/fail, never as a standard pass.

Any dangerous authority, unknown critical field, holder/deployer breach,
honeypot/restriction, unacceptable tax, mutable critical behavior, unlock, or
unverified LP state blocks admission.

### 5. Supply, unlock and insider gate

Require a supply schedule with source URLs and timestamps. Capture team,
treasury, investor, airdrop, staking and liquidity allocations; vesting
contracts; next unlock date/amount; circulating/fully diluted supply; and
untracked mint/admin capacity. Compare deployer/insider wallet behavior with
that schedule. Missing or contradictory schedules are `unknown`, not zero
unlocks.

### 6. Fake-volume and manipulation gate

Cross-check DEX aggregates with on-chain swaps. Test maker concentration,
repeated sizes/timing, self-funding loops, circular flows, same-block
round-trips, price/volume divergence, cross-pool price consistency, top-wallet
coordination, liquidity pull/re-add patterns and promotion concentration.
Social evidence is supporting context only and never repairs an on-chain fail.

### 7. Custody and bridge gate

The plan must name the venue, quote asset, route and custody assumption. Native
chain spot is preferred. If any wrapped/bridged asset is unavoidable, identify
canonical contracts, bridge operators/validators, pause/admin powers, proof of
reserves/redemption path, destination liquidity and incident state. Unknown or
noncanonical bridges fail. This pipeline does not create or access wallets.

### 8. Setup and risk gate

Before WATCH or ENTER, preserve:

- hypothesis, catalyst, 1h trigger, entry-zone low/high and observation time;
- invalidation price and thesis event; no averaging below invalidation;
- maximum loss in USD and % NAV derived from entry-to-invalidation distance,
  fees and stress slippage—not a fixed notional mistaken for risk;
- maximum position no larger than verified exit capacity;
- TP ladder, liquidity-aware clip plan, time stop and emergency exit rules;
- monitoring for authorities, deployer/insiders, liquidity, transfer mechanics,
  unlocks, volume quality, bridge/custody and manipulation;
- explicit falsifiers and human decision pending.

Classification:

- `REVIEW`: any hard fail, unknown/untraceable gate, incomplete plan or stale evidence.
- `WATCH`: every hard gate passes with provenance and the full risk plan exists,
  but the declared execution trigger is not confirmed.
- `ENTER`: same evidence as WATCH plus a confirmed trigger; advisory and
  human-gated only. It never authorizes execution.
- `NO_VALID_SETUP`: complete run, zero WATCH/ENTER decisions, all candidates
  terminally rejected with reason counts.
- `DATA_INCOMPLETE`: source errors, partial pagination or fewer evaluated assets
  than the frozen universe; never relabel as no setup.

## Outcome journal

Append one immutable decision record per candidate/run:

- IDs: journal ID, run ID, chain/address, policy version, evidence hash;
- decision: REVIEW/WATCH/ENTER, blockers, human-gate flag, decision timestamp;
- frozen plan: entry, invalidation, max loss/position, costs, targets, time stop,
  exit capacity and monitoring triggers;
- later observations at fixed horizons (1h, 4h, 24h, 72h): price, liquidity,
  authority/supply changes, maximum adverse/favourable excursion;
- if a human records a trade: venue, fill/fees/slippage and exit reason, without
  storing wallet secrets;
- terminal outcome: invalidated, target, time stop, rug/liquidity event,
  no-entry, unavailable, and data quality notes.

Never overwrite the original decision or evidence. Corrections append a linked
revision. Evaluate rejected candidates too, so the process can measure false
negatives without hindsight-changing old thresholds.

## Verified first slice in this worktree

`trading/memecoin/discovery_policy.py` implements only the provider-neutral,
fail-closed admission contract:

- ten required evidence gates shared by Solana and TON;
- PASS provenance requirements (timestamp + source URL);
- complete entry/invalidation/max-loss/exit/monitoring risk-plan validation;
- REVIEW/WATCH/human-gated ENTER decisions;
- coverage-aware run outcomes, including a valid `no_valid_setup` result that
  cannot be emitted for partial coverage or provider errors.

It deliberately does not adapt Helius, Pump.fun, Jupiter, TON APIs or any DEX,
and it is not wired into the legacy scanner/recommender yet. Therefore this
slice cannot emit production WATCH/ENTER candidates. The next coherent slice
is a Solana adapter that fixes provider completeness, resolves holders and
proves LP/Token-2022/round-trip mechanics before feeding this policy; the TON
adapter follows the same normalized contract independently.

## Sources

[1] https://solana.com/docs/tokens/extensions/transfer-fees — Solana Transfer Fees
[2] https://solana.com/docs/tokens/extensions/permanent-delegate — Solana Permanent Delegate
[3] https://solana.com/docs/tokens/basics/freeze-account — Solana Freeze Account
[4] https://solana.com/docs/rpc/http/gettokenlargestaccounts — Solana getTokenLargestAccounts
[5] https://dev.jup.ag/docs/swap/get-quote — Jupiter Get Quote
[6] https://docs.ton.org/v3/guidelines/dapps/asset-processing/jettons — TON Jetton Processing
[7] https://docs.ton.org/contracts/standard/tokens/jettons/mint — TON Mint Jettons
[8] https://docs.ton.org/contracts/standard/tokens/jettons/how-it-works — TON Jetton Mechanics
[9] https://docs.dexscreener.com/api/reference — DEX Screener API Reference
