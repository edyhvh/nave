# PONS and AI-assisted memecoin opportunity research

Research date: 2026-09-06 Europe/Berlin (retrieval on 2026-09-05 UTC).
Mode: `READ_ONLY_RESEARCH_ONLY_HUMAN_GATED`.
Verdict: **research specification ready for review; NO EDGE VALIDATED**.

Continuation: [the cached-cohort verification](stage1-frozen-cohort-verification-20260906.md)
recovered the completed 24-hour replay locally but found that the launch
sample was frozen before its UTC day ended. It remains descriptive, not a
fifth comparable day. The unchanged A/C comparison shows no stable added
benefit; no new Dune query or paid acquisition was needed.

This addition connects the supplied Miles Deutscher video to NAVE's existing
research contracts. It proposes an evidence-producing scanner experiment, not
a production scanner or a PONS recommendation. No strategy thresholds, jobs,
watchlists, services, orders, or delivery settings are changed. New Dune
queries and credits used: **0**; paid transcription/provider acquisitions: **0**.

## 1. What the supplied source actually supports

The [September 4 post](https://x.com/milesdeutscher/status/2096010425879961883)
contains a 31-minute video and quotes a
[research thread](https://x.com/milesdeutscher/status/2095911931131600912).
X returned 403. Metadata came through the
[FxTwitter mirror](https://api.fxtwitter.com/status/2096010425879961883);
the entire public, auto-generated [caption track](https://video.twimg.com/subtitles/amplify_video/2095915267679506435/0/haa6RZFXmA9CTyaG.vtt)
was read. Thread replies and the prompt library were not retrieved.
Caption spelling cannot establish token identity.

| Video time | Source observation, paraphrased |
|---|---|
| 01:47–05:05 | Curate social ideas; use scanning to supplement human coverage. |
| 06:00–10:15 | Investigate founders, revenue, value accrual, catalysts and technical risk; CHIP is the example. |
| 14:20–16:35 | Scout extracts smaller-token mentions, checks momentum, and reports narrative, risks and originating posts. |
| 17:20–19:55 | Position monitoring, risk briefs and order preparation are separate capabilities. |
| 24:20–24:45; 26:30–28:35 | PONS is a retrospective example and conditional pullback idea; further on-chain AI tests are unfinished. |

**Interpretation:** adopt traceable idea intake and falsifiable due diligence.
The demonstration does not establish early detection accuracy or executable
returns. Its trade anecdotes cannot validate NAVE's scanner.

## 2. PONS: recent events and unresolved economics

[Decrypt's September 3 coverage](https://decrypt.co/377349/pons-robinhood-chain-meme-coin-token-factory)
reports a rise from roughly $0.0033 on July 17 to $0.5978 on September 3,
Binance Alpha access from September 2, and an 80%-of-revenue buyback narrative.
These are retrospective reporting claims, not NAVE-reconstructed prices or
proof that a trade was available before the move. Alpha access is not a
Binance spot listing. The embedded Binance announcement was not independently
retrieved here.

[OKX's own announcement](https://www.okx.com/en-ar/help/okx-to-list-perpetual-futures-for-pons-crypto)
specifies PONS/USDT perpetual trading from **2026-09-05 03:00 UTC**.
Its HTML metadata records publication at 02:00 UTC that day. This establishes
an announced access catalyst, not actual fills, spot depth, or an explanation
for July/August returns. The page was readable by direct HTTP after browser
retrieval failed.

[Bitquery's September 4 investigation](https://bitquery.io/investigations/pons-launchpad)
reports 207,893 v2 launches in August 3–September 3, with 3,228 graduations
(1.55%). Its wallet cash-flow measure counts unsold inventory as zero; it is
not realized trading PnL. The article says the PONS token predates the sampled
factory and reports no contract reference tying it to that factory. Its
factory label differs from the provider's API documentation, which calls the
same address a launch deployer. These are provider findings, not independently
replayed NAVE results.

The [provider's API documentation](https://docs.bitquery.io/docs/blockchain/robinhood/pons-api/)
distinguishes v1/v2 contracts, lists a v2 buyback vault, and documents
`TokenLaunched`, `CurveBuy`/`CurveSell`, and graduation events. It also warns
that decoded historical coverage and USD fields vary by dataset. This is a
candidate acquisition path, not proof of token-holder cash flow. A named vault
does not resolve which token it buys or what share of fees reaches it.

**Unresolved claim:** the v2 business's growth funds PONS buybacks at the
advertised rate. Require a versioned fee-recipient → swap → burn transaction
reconciliation, including the bought token's address, before using it as a
valuation feature. Gross volume, trader fees, protocol revenue, creator fees,
and token-holder value accrual must remain distinct quantities. Do not
annualize a single exceptional day into a verified earnings multiple.

The token's canonical identity is **not resolved by this PR**. Provider-reported
addresses are discovery leads; no explorer/source-code or bridge mapping was
independently verified. There is no current PONS price, entry level or return
estimate in this report.

## 3. Preserve the prior parameters and negative evidence

These are existing research conventions, not optimized trading instructions.

| Track | Existing contract retained |
|---|---|
| Feature availability | Decisions at launch +1/3/5/10 minutes; `available_at <= decision_time`; future features rejected, missing values UNKNOWN. See [feature contract](m3-feature-contract-20260831.json). |
| Stage-1 survival | Future trades in (15m,20m], (30m,35m], (60m,65m] after launch; interval completeness required. Activity is not profit. See [survival contract](nave-stage1-survival-contract-20260901.json). |
| Burst paper benchmark | $100, no more than 0.25% of reconstructed liquidity, +20% target, −15% stop, 60m time stop; stop-first on same-event ambiguity. Report 5/15/30/60m executable outcomes. See [dual-horizon research](m3-dual-horizon-trajectory-research-20260831.md). |
| Runner | Separate 4/8/12/24/48/72h outcomes; graduation and peak capitalization are not success. Fixed 4/8/24/48h and 20/30/40% trailing exits stay exploratory until entry information is demonstrated. Same dual-horizon source. |
| Participant controls | A/B/C/D comparisons, matured prior history, raw versus participant-excluded flow, activity-matched placebos, top-wallet/top-winner removal. See [signal-sanity contract](m3-signal-sanity-contract-20260831.json). |
| Executable-strategy gate | Chronological 60/20/20 split; ≥1,000 eligible launches, ≥200 holdout signals, ≥90% coverage per primary horizon, ≥200 resolved 60m signals; positive base/stressed net expectancy and stable improvement. See [bounded-probe plan](m3-reassessment-and-next-probe-20260831.md). |

Do not silently combine differing experiments: the bounded-probe document
contains both 5-minute entry-window and 10-minute observation language. This
PR does not resolve that legacy inconsistency or run its trade replay. The
proposed experiment below uses the unambiguous **launch +10m survival** decision;
a later execution experiment must freeze its entry clock explicitly.

The [Day-5 report](nave-stage1-survival-day5-20260901.md) retains four complete
daily samples. On August 31, C_survival PR-AUC was 0.2220 versus A's 0.2464;
the bootstrap difference interval crossed zero. Prior transfers changed sign.
The [Day-6 report](nave-stage1-survival-day6-20260901.md) records 21/24 archive
hours and excludes that partial day. These are retained results, not reruns
or a claim that the provider remains unavailable today. B/D maturity and Runner
coverage remain unresolved in that evidence.

## 4. Scanner specification: three separate research populations

1. **Launch cohort:** a complete, fixed-period launch denominator, including
   zero-trade launches. Sample by predeclared hash before inspecting outcomes.
   Initially reuse the Solana adapter; a Pons/Robinhood adapter requires its
   own lifecycle and coverage proof.
2. **Social discoveries:** freeze an account/source set and poll policy; retain
   every mention, duplicates and rejected identities. This is a social-source
   cohort, not the complete launch population. A video published after a pump
   cannot supply an earlier signal. Popularity lists are selection channels,
   not ground truth or organic-demand evidence.
3. **Established platform tokens:** assess dated business metrics, actual
   token rights, catalysts and market depth. PONS belongs here as an unresolved
   case study; being discussed beside memecoins does not make it a new launch.
   Keep any later weekly/daily context, 4H setup and 1H trigger evaluation
   separate from minute-scale launch models. No entry rule is introduced here.

Required identity key: `(chain_id, canonical_asset_address)`. Preserve token
standard/decimals, deployment time, protocol version, pool address or pool ID,
quote asset and quote conversion timestamp. Pool creation is not token birth.
Bridged representations require explicit provenance; ticker equality never
merges them. PONS is an explicit user-supplied case, never a default universe
member or reusable strategy parameter.

For each candidate, retain `event_time`, `published_at`, `first_seen_at`,
`retrieved_at`, `available_at`, decision time, source ID/hash, coverage, feature
version, and selected/rejected reasons. Derivation availability is at least
the latest input availability. Malformed clocks, NaN/infinity, missing chain
identity, stale reserves or conflicting token mappings block eligibility.
Unknown social coverage is not zero mentions; wallet count is not owner count.

Apply cheap identity/completeness filters before costly enrichment. Then
evaluate holder/authority risks, concentration, protocol-generated versus
organic flow, two-way execution costs and fixed-notional exit capacity.
Preserve provider gaps, right censoring, migration uncertainty and verified
unexitability separately. A vanished endpoint alone is not evidence of death.

Output a research candidate with sources, reason, missing evidence and expiry.
An empty complete scan may report no candidates; an incomplete scan reports
provider/coverage failure. Do not convert either into a market HOLD decision.

## 5. One bounded next experiment

**Proposal only; not executed or registered in the live research state.**

Question: does social evidence known by launch +10m add information about
60m activity beyond the frozen C_survival baseline?

- First finish the existing cohort's missing coverage using the same frozen
  sample if it is recoverable; do not replace an inconvenient day or retune C.
- Freeze a new prospective social-source manifest before collection. Primary
  added feature: distinct source accounts with an independently authored,
  address-resolved mention known by the decision. Remove reposts; report
  suspected coordinated accounts separately. No verified mention feed means
  the social extension is BLOCKED, not a null result.
- Run the social extension only on launch-cohort tokens with full source
  observation coverage. Report the eligible denominator and exclusions against
  the full launch cohort. Keep later mentions as outcomes/context only.
- Compare C versus C+social on the same eligible rows, alongside a
  time-shifted-mention placebo. Freeze transformations in development; use
  chronological validation/holdout, token clustering and day-block uncertainty.
  Report PR-AUC, Brier, base rates, precision lift, coverage and top-token/day
  sensitivity. A social-selected PONS anecdote is outside this test.
- No model fitting until the source manifest, time boundaries and training
  cutoff are frozen. Existing evidence is development context, not a fresh
  untouched holdout. The existing 5–7 comparable-day checkpoint is a data
  review, not an automatic strategy-acceptance gate.
- Positive activity information only earns a separate execution study using
  the prior trade/evidence gates. Missing historical depth or numerical
  fee/latency scenarios blocks profitability claims. Stops are modeled
  triggers, never guaranteed maximum loss.

Pons acquisition is a separate prerequisite proposal: prove one versioned
launch → curve trade → graduation → pool trade chain before collecting a
population. Retain an independently sampled denominator and negative cases;
do not query only named winners. The protocol-token fee reconciliation from
section 2 is a different dataset and hypothesis.

## 6. Efficiency and integration boundary

Reuse local manifests, cached schema and existing results first. Dune's
[query guidance](https://docs.dune.com/query-engine/writing-efficient-queries)
supports chain/time partition filters, projected columns and incremental
reuse. An SQL LIMIT alone is not a scan-cost budget. Do not repeat the prior
large-result retrieval mistake documented in the
[credit review](dune-review-packet-v2-20260831.md).

This research used no Dune calls. Historical account balances are not current
authorization. For any subsequent acquisition, get fresh usage and count
execution plus export costs. Use the stricter prior small-probe policy
(target <5 credits/query, ≤15 single-query ceiling, ≤75 iteration ceiling)
from the [statistical review](m3-statistical-signal-sanity-20260831.md), together
with the existing resource guard's 200-credit checkpoint ceiling and 15-GiB
disk floor. These are proposed acquisition limits, not a claim that the
current guard enforces every one of them or can cancel before costs accrue.
Unknown cost/coverage means stop that acquisition and retain the gap. No plan
upgrade, full-chain backfill, or paid social subscription is needed for this PR.

[PR #47](https://github.com/jhonnyisaacc/nave/pull/47), inspected at
`53131c34a67ed967d7ab49ac9ca992487518651b`, offers snapshot-based discovery but
does not implement this whole spec. Its 2× volume acceleration and $25k
liquidity defaults are candidate filters, not validated edge parameters; its
asset-label identity and per-feature evidence handling need further work.
The $100/0.25% paper cap separately requires at least $40k reconstructed
liquidity for the full notional, before price-impact checks.

The supplied September 4 integration reports remain **reported operational
blockers**, not independently re-audited live state in this PR. Their Discord
routing/delivery concerns belong to Hermes; NAVE owns deterministic research
and evidence. Any future cutover needs the actual CLI result preserved through
Spanish Discord presentation, correct parent-channel routing, bounded message
parts, deduplication/expiry and a confirmed delivery outcome. Crypto reports
need an explicit crypto label; do not silently inherit `STOCKS:`. Runtime
repair and replay of dropped alerts are outside this research change.

## 7. Review disposition

Useful improvement: a traceable social-evidence experiment plus separate
protocol-token economics and launch-cohort identity requirements. Unsupported:
PONS buyback yield, an earlier detectable PONS entry, cross-chain profitability,
or a validated live opportunity scanner. The attached
[research manifest](pons-ai-opportunity-research-20260906.json) records the
source provenance, unchanged parameter references and outstanding gates.
