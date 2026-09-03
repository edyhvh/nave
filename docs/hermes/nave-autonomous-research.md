# NAVE Autonomous Research on Abi / Hermes

NAVE is a durable research workstream owned by the existing `quant` profile.
Abi routes bounded background research to the existing default-board Kanban;
the single multiplexed Hermes gateway's embedded dispatcher claims ready tasks
atomically and launches the assigned profile. There is no NAVE daemon, second
dispatcher, scheduler, or replacement state framework.

## Iteration contract

Each task asks one bounded question and references the compact ledger at
`research/nave/state.json`. Quant reads the current state, performs reversible
historical/local work, writes a detailed report, writes a distinct skeptical
review, updates the ledger, and decides the next step. A justified continuation
is materialized as exactly one child task assigned to `quant`; the parent link
keeps it dependency-aware and the dispatcher promotes it when the parent is
done. A gate becomes native blocked/action-required attention instead.

The task context remains compact: state, latest report, latest review, frozen
contracts, and relevant repository paths. Kanban itself supplies parent
handoffs, task history, comments, attachments, claim leases, retries, and
worker logs.

## Safety and resource policy

NAVE is read-only and research-only. It cannot trade, sign, touch wallets,
create live alerts, buy credits, purchase services, or alter live behavior.
Dune is used only after usage/execution preflight and recovery checks. The
current policy is <=25 target credits per task, warning at 50, hard stop at 75,
and <=200 cumulative since a human checkpoint; no limit authorizes a purchase.
PumpApi replay is staged hour → day → three days → multi-day with streaming,
checkpoints, hashes, compact Parquet, and explicit failed/missing hours.

## Current scientific position

The ledger records the verified current position: `NO EDGE VALIDATED`, with
PumpApi early-event acquisition `PUMPAPI_VALID_WITH_LIMITATIONS`. One usable
day is not enough for A/B/C/D participant/precursor comparisons, Runner
continuation, or temporal stability. The next information-rich step is to
finish/verify the one-day gate and then run a bounded three-day panel with
frozen daily manifests. The current branch/ref and working tree must be
checked before treating any report path as available.

## Stop, resume, and crash behavior

Operators inspect `hermes kanban list --assignee quant --json`, `show`, and
`runs`. They pause a task with `hermes kanban block <id> --kind needs_input
"reason"` and resume with `hermes kanban unblock <id> --reason "decision"`.
For a newly created standalone attention card, issue and verify the explicit
`needs_input` block immediately; `--initial-status blocked` is not by itself a
durable hold on the observed Hermes dispatcher build.
After a crash, the gateway's native claim lease, heartbeat, retry, and stale
recovery path controls the task; expensive provider operations are recovered
from their persisted execution metadata before retry. No manual shell loop is
needed.

See `nave-quant-runbook.md` and `nave-task-template.md` for the operator and
worker contract.
