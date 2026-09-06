# Quant ↔ NAVE repair verification — 2026-09-06

**Code integration: focused checks passed. Production integration: NOT_READY. Strategy: NO EDGE VALIDATED.** These are separate verdicts. This report supersedes earlier readiness summaries for the addressed review findings; it does not claim that every operational requirement is solved.

## Implemented in the open NAVE PRs

| PR | Repair |
|---|---|
| #42 | Provenance/state-owner contract; strict shared macro freshness; observation versus retrieval timestamps. |
| #43 | Reject partial/stale/contradicted Cava context; invalidate prior context on failed new evidence; save context before cursor; timestamp live decisions after acquisition; missing transcript remains DATA_UNAVAILABLE. |
| #44 | Missing/partial BTC+ETH COT cannot become neutral; dated macro/market observations required; missing evidence differs from evaluated NO_SETUP; no implicit PONS replay universe; no COT cache directory creation at import. |
| #45 | No generic portfolio watchlist; private holdings and Quant responsibilities remain separate; candidates read Quant numeric watches; invalid/stale prices fail closed; zone/threshold re-arm; missing fundamentals/state/price produces REVIEW_REQUIRED; private ledger refresh wired with its existing audit history. |
| #46 | Result persisted before consuming disclosure IDs; missing availability is not fabricated at result level. |
| #47 | Chain+address+decision-time identity joins; duplicate/collision rejection; finite features/outcomes; explicit case studies; cache lock, limit identity, TTL, explicit refresh and consumption checks; nonfinite budget estimates fail closed. |
| #48 | Shared foundation synchronized; strategy command registration kept independent of portfolio. Experimental options remain research-only and unscheduled in prepared contracts. |
| #49 | Full result/payload/evidence retained; Spanish Discord presentation, stocks versus crypto prefixes, parent-channel metadata, UTF-16-sized chunks, explicit long-report excerpts; bounded CLI executor with unique journals and Shabbat gate. |

All eight branches were merged sequentially into a **fresh detached verification worktree without conflicts**. Focused combined tests: **191 passed** (research contracts, Cava, crypto/COT/universe, portfolio/ledger/watches, disclosures, memecoin/cache/budget, options, orchestration/runner, CLI and existing Hermes adapter). Touched-module Ruff and `git diff --check` passed. A real local fixture CLI run produced a CRYPTO report and durable JSON journal; no platform send occurred. This is focused verification, not a claim that the entire repository suite or production providers passed.

## Abi/Hermes companion repair

The `agent` repository contains the reviewed no-agent script templates, Quant profile overlay, exact two-store migration map, updated Discord skill and read-only audit. Live Hermes base `13e72fb205` lacks the two previous shared-primary fixes. Candidate `e480de5946` ports them to refactored modules and also records execution/delivery outcomes with aligned timestamps. Exact primary-route authorization survives both transport resolutions; foreign/unmatched/disabled routes fail closed, Quant-local Discord remains disabled. The existing Discord adapter already splits messages; Grok's unsplit-adapter concern does not apply to this current revision.

Hermes checks: **286 passed** across routing, durable delivery queue, delivery confirmations, jobs/status, scheduler, housekeeping and Discord formatting. A real temporary SQLite queue reached `delivered` through the real router with a fake transport and did not replay on a second drain. That is not a production Discord acknowledgement. The patch applies cleanly to the checked served revision, but has **not been applied or restarted live**.

## Remaining activation/acceptance gates

- Latest live Quant rows still fail: the observed queue contains 26 failed and 9 historical delivered rows; the latest row fails with Discord disabled. Historical successes do not validate this candidate.
- No approved one-shot production Discord test has been sent. Require an acknowledged parent-channel message and its durable delivered row before claiming integration.
- No Supadata key declaration was found in the checked Quant/home/NAVE environment files. Provision a profile-scoped credential or validate a supported alternative; do not turn credential failure into a market conclusion.
- Live job stores, destinations, workdirs and schedules have not been migrated. Versioned desired Quant jobs are held PREPARE_ONLY; missing workdirs, origin-thread delivery, duplicate M3/options paths and legacy channels are resolved in the cutover plan, not falsely marked applied.
- A1/A2/A4 natural-language/event responsibilities are preserved but are **not evaluated by the deterministic price checker**. A4's old paused-provider assertion requires reconciliation against the actual home R4 owner before cutover. Do not label these responsibilities healthy solely because numeric watches ran.
- Live wallet refresh/provider freshness, invalid-price behavior and alert re-arm need profile-scoped acceptance with private state. No wallet or watch state was changed here.
- Memecoin requires a valid explicit snapshot and independent strategy gates. It is not an autonomous profitable scanner. M3/options promotion remains blocked by validation, not by transport.
- Long report excerpts are explicitly labeled; full evidence stays in the journal. Confirm retention/access during deployment. No stale CAT/Cava/memecoin alert is automatically replayed.

Merge-readiness means the reviewed research code can be combined and tested. It does not authorize orders, strategy promotion, automatic live job activation or a claim of profitable edge. PRs remain open for review; none were merged by this work.
