# NAVE Main Consolidation Report

Date: 2026-09-03

## 1. Final Result

- Main HEAD: final consolidation/report commit; verified locally after commit.
- Origin/main HEAD: verified equal to local `main` after push.
- Working tree: clean.
- Tests: 698 passed, 1 skipped; focused consolidated-area tests: 55 passed.

The exact final SHA is recorded in the completion handoff and can be checked
with `git rev-parse main origin/main`.

## 2. Branches Reviewed

| Branch/worktree | Unique work | Disposition |
| --- | --- | --- |
| `fix/m3-malformed-pair-resolution` | M3 malformed provider-pair handling and current NAVE state | Merged; follow-up same-pair resolution fix committed on `main` |
| `research/nave-stage1-scale` | Stage-1 day-5 panel and evidence | Merged; newer paused state retained |
| `research/nave-stage1-day3`, `research/nave-multiday-outcomes` | Earlier Stage-1 and unresolved-outcome artifacts | Reviewed; content already represented or superseded by later canonical artifacts; old state not adopted |
| `research/m3-statistical-signal-sanity`, `research/m3-multiday-historical-panel` | M3 statistical contracts, Dune/PumpApi panel and acquisition gates | Merged/extracted |
| `research/dune-efficient-panel`, `research/dune-historical-panel` | Dune research panel work | Reviewed; useful artifacts represented in the merged Dune research surface |
| `experiment/n5-squeeze-discovery`, `experiment/n6-squeeze-daily`, `experiment/n7-n6-replication`, `experiment/n8-n6-cost-stress` | Historical squeeze experiments and validation evidence | Merged as reproducible history; optional behavior remains off by default |
| `experiment/n3-cross-asset-confirm` | Rejected cross-asset confirmation probe | Merged as historical evidence; not promoted as strategy behavior |
| `experiment/g1-glassnode-overlay`, `experiment/n2-regime-transition`, `experiment/n4-sizing-split`, `experiment/n5-squeez-bias` | Earlier rejected/inconclusive experiments | Preserved as history where useful; no unsupported behavior promoted |
| `fix/ism-equity-autonomy` | Bounded, deterministic ISM equity discovery pipeline | Merged; no execution capability added |
| `fix/portfolio-integrity-followup`, `task/t_a974e883-causal-backtester` | Portfolio integrity fail-closed changes | Already represented by the remote/main merge; branch tips retained |
| `nave-memecoin/t_*`, `wt/t_*`, temporary N7/N8 worktrees | Task-specific duplicate commits and dirty evidence | Reviewed; valuable evidence extracted or superseded; recovery stashes retained |
| Detached Hermes/review worktrees | Historical review snapshots | Not current NAVE product code; not merged |

No reviewed branch contains required current code that is absent from `main`.

## 3. Changes Consolidated

- Current NAVE state, Stage-1 contracts, survival/observability audits, and
  bounded Dune/PumpApi acquisition and replay helpers.
- Provider normalization and explicit OpenBB data-path handling.
- M3 statistical sanity, dual-horizon, multi-day panel, and outcome tooling.
- Fail-closed memecoin discovery admission policy and bounded ISM equity
  discovery policy.
- Historical squeeze, cross-asset, Glassnode, and cost-stress experiments with
  their conclusions preserved rather than promoted.
- Provider-quality evidence, missing-hour handling, unresolved outcome
  taxonomy, and regression tests.
- The Abi/Hermes José Luis Cava daily research contract, including the
  verified YouTube source, seven-video bootstrap history, transcript failure
  handling, point-in-time evidence rules, and read-only human-gated boundary.
- Workspace hygiene for nested `.worktrees/` and this consolidation report.

## 4. M3 Malformed Pair Fix

The malformed-pair branch identified that malformed provider elements could
interfere with outcome resolution. The consolidated implementation now skips
malformed provider entries, resolves only against the recorded entry pair, and
distinguishes provider unavailability, dead pairs, unexitable/migrated pairs,
and legacy entries with unknown pair identity. Regression tests cover malformed
elements, temporary provider failure, no-pair outcomes, pair substitution, and
legacy unknown identity. Metrics exclude unresolved/provider-unavailable cases
from scientific terminal outcomes.

## 5. Research State

The canonical state remains `READ_ONLY_RESEARCH_ONLY_HUMAN_GATED` and
`PAUSED_NOTIFICATION_AND_STATE_RECONCILIATION`. NAVE has not validated a
robust edge. Provider incompleteness, right censoring, migration uncertainty,
and unresolved observations remain explicit. No scheduled continuation or
autonomous financial action was enabled.

Point-in-time eligibility helpers and contracts exist, including
`available_at <= decision_time` checks where applicable. Complete
provider-wide enforcement and a larger comparable event-day panel remain
future research milestones; the repository does not claim full PIT safety.

## 6. README Changes

`README.md` was rewritten to a concise current description of NAVE’s research
role, evidence philosophy, active focus, repository structure, setup, safe
tests, read-only entrypoints, action boundary, and documentation links. Stale
autonomous-trading and unsupported edge claims were removed. The José Luis
Cava contract is linked from the research documentation section.

## 7. Tests

- Full practical suite from `main`: `PYTHONPATH=. .venv/bin/pytest -q -m
  'not integration'`: **698 passed, 1 deselected**.
- The deselected test is the existing wallet testnet integration test. The
  safe suite also emitted existing websockets and integration-marker warnings.
- The Cava task was continued in read-only mode on 2026-09-03; the new copper
  video had no available transcript, so the report correctly returned `NO
  ACTION / INSUFFICIENT EVIDENCE` and did not advance the cursor.
- The recurring Cava task remains enabled for its next scheduled tick. Its
  local/manual delivery status is still `delivery_failed` because the
  standalone runner has no live Discord transport; the primary multiplexed
  gateway is active, but a successful scheduled notification has not yet been
  verified. The secondary Quant Discord adapter was not enabled because it
  would duplicate the primary credential.
- CLI/import and JSON/link checks were run without provider acquisition or
  external financial actions.
- Repository-wide Ruff was also inspected; it reports existing style findings
  outside this consolidation, so lint was not used as a passing acceptance
  gate and no broad style rewrite was introduced.

## 8. Remaining Historical Work

Rejected and inconclusive experiments remain available in
`docs/analysis/experiments/` and their raw research artifacts. Old task
branches, detached review worktrees, and pre-consolidation stashes were not
deleted so historical recovery remains possible. They are not required as
runtime sources for current `main`.

## 9. Remaining Technical Debt

- Enforce point-in-time availability consistently across every provider path.
- Expand the comparable event-day panel without silently admitting incomplete
  hours or partial days.
- Continue provider freshness, retry, quota, and completeness audits.
- Reconcile notification/state infrastructure before any bounded continuation.
- Keep execution-capable legacy surfaces isolated from the read-only research
  path and require explicit human review for any future action boundary.

## 10. Final Verification

- Is all valuable current development represented in `main`? **Yes.**
- Is local `main` clean? **Yes, after the final report commit and verification.**
- Does local `main` equal `origin/main`? **Yes, verified after push/fetch.**
- Did all required tests pass? **The practical suite passed; one existing
  wallet testnet integration test was skipped.**
- Is README current? **Yes.**
- Is NAVE still read-only/human-gated? **Yes.**
- Was NAVE autonomy left paused? **Yes.**
- Was any valuable uncommitted work discarded? **No. Dirty states were
  inspected, stashed for recovery, and valuable content was integrated or
  explicitly retained as historical evidence.**
- Are there any branches that still contain required current code? **No.**
