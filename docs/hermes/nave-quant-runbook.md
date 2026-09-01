# NAVE autonomous research on Abi / Hermes

This runbook is for the existing `quant` profile and the existing embedded
Kanban dispatcher. It does not create a scheduler, worker manager, gateway, or
second state system.

## Worker sequence

1. **READ STATE** — read `research/nave/state.json`, the latest report/review,
   `AGENTS.md`, and the frozen contracts named there. Confirm the task is
   assigned to `quant` and remains inside NAVE.
2. **PICK HIGHEST-INFORMATION TASK** — choose one blocker-reducing experiment,
   not a feature hunt. Use the current state and evidence; do not assume a
   multi-day or Dune result exists merely because a branch/ref mentions it.
3. **PREFLIGHT** — inspect existing local artifacts, Dune execution/usage
   state, free disk and memory, source availability, and current user changes.
   Recover completed provider work before retrying. For any proposed Dune call,
   obtain a fresh usage snapshot and run the local fail-closed guard before the
   call (the command exits non-zero when the call is not allowed):

   ```bash
   python3 -m research.nave.resource_guard \
     --credits-used <fresh-used> --credits-included <included> \
     --checkpoint-used <human-checkpoint-used> --estimate <worst-case> \
     --free-disk-gb <free-gib>
   ```

   Recover completed provider work before retrying. Stop at the configured
   resource or data-safety gate. The guard is intentionally an explicit
   preflight, not a hidden provider client or second scheduler.
4. **RESEARCH** — run only reversible historical/local work. Use the hybrid
   Dune/PumpApi/local-Parquet architecture. Keep participant history
   point-in-time and preserve missingness.
5. **VALIDATE** — check definitions, chronology, same-pool outcomes,
   uncertainty, concentration, day/hour/venue dependence, leakage, controls,
   and whether the result exceeds the evidence.
6. **REPORT** — write a Markdown report with evidence first and a compact JSON
   skeptical review that actively tries to invalidate the report. Use the
   allowed classifications; `NO ROBUST SIGNAL FOUND` is valid.
7. **DECIDE** — update `state.json` with what was learned, what remains
   unknown, the blocker, resource usage, and the next experiment. If the
   expected information value is positive and no gate is crossed, call the
   native `kanban_create` tool exactly once with `assignee: "quant"`,
   `parents: [current_task_id]`, `workspace_kind: "worktree"`,
   `workspace_path: "/home/david/nave"`, and a compact reference to
   state/report/review. Also pass a deterministic `idempotency_key` derived
   from the current task id and experiment slug. The explicit repository path
   is required: project stores are per-profile, while this path lets the shared
   dispatcher resolve a fresh child worktree without sharing the parent's
   checkout. Pass the project id only when it resolves in the active profile.
8. **HAND OFF** — call `kanban_complete` for the current task with the report
   and review paths in `artifacts`, and the child id in `created_cards` when a
   child was created. Use the native block/attention semantics for real gates;
   do not create a speculative fan-out.

## Canonical artifacts

- State: `research/nave/state.json`
- Detailed evidence: `docs/analysis/memecoin/` following existing naming
- Compact reviews/contracts: `docs/analysis/memecoin/*.json`
- Large local data: ignored `data/research/pumpapi/` or existing local data
  locations; never commit raw JSONL/Parquet histories.

## Limits and gates

The observed Dune checkpoint is 2,024.104 of 2,500 included credits, with
475.896 remaining. For autonomous NAVE work, target no more than 25 credits
per task, warn at 50, hard-stop at 75, and stop cumulative work at 200 since a
human checkpoint. These are a local research guard and do not authorize
purchases; recheck live provider usage before every call. If the provider
cannot expose a reliable preflight, do not make the call.

Stop and create native human attention for payment/subscription/credentials,
wallet or execution, security-sensitive changes, destructive repository work,
material licensing uncertainty, resource/disk threat, scope expansion, a
strong result ready for operationalization, or three completed iterations with
no meaningful uncertainty reduction. Never turn research into a live filter,
watch, alert, or trade automatically.

## Operator controls

The board is the status surface:

```bash
hermes kanban list --assignee quant --json
hermes kanban show <task-id>
hermes kanban runs <task-id>
hermes kanban dispatch --dry-run
```

Pause a ready/running NAVE task at a genuine gate:

```bash
hermes kanban block <task-id> --kind needs_input "<human decision required>"
```

Resume it after the gate is resolved:

```bash
hermes kanban unblock <task-id> --reason "<decision/evidence supplied>"
```

The gateway's embedded dispatcher will pick up a ready assigned task on its
normal tick. After a restart, inspect `hermes kanban show`, `hermes kanban
runs`, and `hermes kanban diagnostics`; native claims, heartbeats, retries,
and stale-run recovery preserve the chain. Do not start
`hermes kanban daemon` while the gateway is active.
