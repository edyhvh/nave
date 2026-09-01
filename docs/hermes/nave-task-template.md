# NAVE Kanban task template

Use this body for one bounded NAVE research iteration. Create it on the
existing `default` Kanban board, assign it to `quant`, and link the next task
as a child of the current task. This is a prompt/template, not a new workflow
engine.

```text
PROJECT: NAVE
PROFILE: quant

OBJECTIVE:
<one bounded research question>

CURRENT_RESEARCH_STATE:
Read /home/david/nave/research/nave/state.json and only the latest report,
review, and frozen contracts it references.

PRIMARY_HYPOTHESIS:
<one hypothesis; distinguish FACT / INFERENCE / HYPOTHESIS / UNKNOWN>

EXPERIMENT:
<predeclared method, chronological boundary, and one primary comparison>

DATA:
<sources, fields, point-in-time rule, missingness and outcome coverage>

RESOURCE_BUDGET:
Historical/read-only only. Check existing provider usage first. No purchases.
Honor the NAVE Dune guard: target <=25 credits, warn at 50, hard stop at 75,
and cumulative <=200 since the human checkpoint. Prefer recovery of completed
executions and compact server-side queries.

PREDECLARED_METRICS:
<sample, coverage, uncertainty, cost/slippage, temporal and concentration checks>

FALSIFICATION:
<what would classify this as reject, inconclusive, contaminated, or blocked>

STOP_CONDITIONS:
<resource, data-safety, scope, human-gate, and diminishing-return stops>

REQUIRED_REPORTS:
Write one detailed Markdown research report and one compact JSON skeptical
review. Persist or attach both artifacts and update state.json compactly.

NEXT_TASK_POLICY:
After the review, create exactly one next NAVE task assigned to quant with
`kanban_create` only if expected information value remains positive and no
human gate is present. Make it a child of the current task. Then complete the
current task with the child id in `created_cards`. Otherwise complete with the
durable next state or use native human-attention/block semantics.

SAFETY:
No wallet, signing, order, swap, execution, live alert, paid provider,
subscription, credit purchase, or live behavior change. No edge claim.
```

Suggested native CLI creation shape for an operator:

```bash
hermes kanban create "NAVE: <bounded objective>" \
  --assignee quant --project nave-memecoin \
  --workspace worktree --max-runtime 1800 --max-retries 1 --goal \
  --goal-max-turns 20 --body "<template filled in>" --json
```

The dispatched worker uses the existing `kanban_create` and
`kanban_complete` tools for continuation; no shell loop or daemon is involved.
