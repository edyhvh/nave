# NAVE Hermes Attention & Continuation Audit — 2026-09-01

## ROOT CAUSE

NAVE paused correctly at a persisted human gate, but the autonomous worker had
no inbound Discord session context when it created the gate tasks. Native
`kanban_create` therefore returned `subscribed: false`, and neither task had a
row in `kanban_notify_subs`. The embedded notifier consequently had no event
subscription to claim: no Discord send was attempted, no destination existed,
and no separate outbound-attention record was created. This was primarily a
notification-request/routing defect, not a Discord delivery failure.

The affected events were:

- `t_177b76c5`: blocked event `2466`, created 2026-09-01 02:53:37 UTC,
  parent `t_ce7db486`.
- `t_e8a16517`: blocked event `2483`, created 2026-09-01 03:00:11 UTC,
  root continuation task, `needs_input`, owner `quant`.

## DISCORD STATE

The single systemd gateway remained alive during the observed Discord outage.
At 10:22:42–10:22:58 CEST the Discord websocket exceeded its latency limit,
was forced to reconnect, and reconnected as `Abi#0465` at 10:23:02 CEST.
This was a temporary transport degradation and did not coincide with the NAVE
gate events. Slash-command synchronization also encountered timeouts/429 rate
limits; those affected command sync only and did not kill the adapter.

An older default/dev duplicate-credential refusal is present in historical
logs. The current multiplexed deployment avoids duplicate Discord sessions by
using the single primary adapter; no token rotation or bot recreation was
performed. The live gateway is connected and serves `default`, `dev`,
`emunah`, `quant`, `sofia`, and `work`.

## QUANT ROUTING

The configured Discord route maps channel `1514695031901126727` to runtime
profile `quant`. The quant profile intentionally does not run a second Discord
poller; the default-owned adapter is the shared transport. The notifier had
been treating `notifier_profile=quant` as requiring a separate quant adapter,
so even a manually added quant subscription could be skipped. The repair now
accepts the shared primary adapter only for an exact configured profile-route
match, preserving fail-closed behavior for unrelated profiles/channels.

## MISSED ACTION_REQUIRED TRACE

Both tasks were created, promoted, claimed, and blocked by quant workers. Their
blocked payloads and run summaries recorded the NAVE human gate, but before
repair both had no notification subscription, no attention table row, no
outbound Discord attempt, no destination, and no retry state. This classifies
the incident as “Abi failed to request/register attention,” not “Hermes failed
to deliver a requested attention event.”

## FIX

The repair stays inside the existing Kanban/notifier architecture:

1. A genuine NAVE quant human gate resolves the configured quant Discord
   profile route and inserts a native notification subscription before the
   blocked/triage event is appended.
2. Multiplexed notification delivery recognizes the shared primary adapter for
   an exact routed channel.
3. ACTION_REQUIRED send failures rewind the existing event cursor and retain
   the pending subscription through a Discord outage; the 5-second native
   watcher cadence retries without dropping the gate.
4. Successful notifier sends now log the native adapter message acknowledgment
   ID. Event cursors remain the idempotency/deduplication mechanism.
5. The quant SOUL explicitly requires persisting the gate and using the
   existing Hermes attention path; it does not introduce a webhook or new
   scheduler.

## CONTROLLED TEST

Created harmless synthetic task `t_16d03993`, subscribed it to the quant
Discord route, and generated a `needs_input` ACTION_REQUIRED event. Hermes
delivered it successfully at 2026-09-01 14:01:50 CEST with message ID
`1544316351907242157`, as recorded by the gateway notifier. The task was then
archived using native Kanban semantics and its subscription was removed by the
notifier. No research, trading, wallet, or provider action was involved.

The recovered NAVE gate events were also delivered through the same path:

- `t_e8a16517` → Discord channel `1514695031901126727`, message ID
  `1544316216561246260`.
- `t_177b76c5` → Discord channel `1514695031901126727`, message ID
  `1544316218675298326`.

## NAVE TASK GRAPH CLEANUP

The canonical live continuation is `t_e8a16517`, identified by
`research/nave/state.json` as the current ACTION_REQUIRED task. The obsolete
controlled-proof chain was not deleted:

- `t_177b76c5`, `t_b0fdb800`, and `t_89fda005` remain safely blocked.
- `t_8ef06fd7` was archived because it was the only obsolete proof artifact
  still `todo`/eligible. Historical task and event data remain preserved.
- Completed proof parents `t_ab98aadd` and `t_ce7db486`, plus the completed
  recovery task `t_06296271`, were not changed.

## RESUME ACTION

Human decision supplied through native `kanban unblock`:

> Continue NAVE research using the smallest highest-information recovery path;
> recover already-paid results first, resolve the smallest outcome-coverage
> blocker, run a bounded PumpApi-vs-Dune overlap proof only if Dune remains
> inefficient, scale only after gates pass, and preserve all safety, cost,
> data-quality, no-trading, and no-purchase boundaries.

`t_e8a16517` transitioned from `blocked` to `ready`, remained assigned to
`quant`, and was claimed/spawned as exactly one active worker (`run 207`) in
its existing workspace `/home/david/.hermes/kanban/workspaces/t_e8a16517`.
No competing NAVE worker was launched. A concise “research resumed” message
was sent through native `hermes send` to the same configured Discord channel
and acknowledged successfully (message ID `1544316995942752338`).

At the final audit check, `t_e8a16517` had completed safely and had created
exactly one native child, `t_f23e05ae`, with parent `t_e8a16517`. That child is
running under `quant` in `/home/david/nave/.worktrees/t_f23e05ae` for the
bounded PumpApi-vs-Dune quality proof and has inherited the quant Discord
attention subscription.

## RESOURCE GUARDS

NAVE state and guards are unchanged: read-only historical research, no
purchases or paid-plan changes; per-task Dune target 25 credits, warning 50,
hard stop 75, cumulative human checkpoint 200. Existing “check execution
status before retry” and disk/resource checks remain in force.

## REMAINING LIMITATIONS

- Discord command synchronization remains subject to the historical rate-limit
  behavior; ordinary message delivery is currently connected and validated.
- The canonical task uses its pre-existing scratch workspace; the NAVE runbook
  and absolute repository/state paths remain authoritative for this continuation.
- The native notifier has event-cursor deduplication. As with any remote API,
  an adapter failure after Discord accepts a message but before Hermes receives
  an acknowledgment can still require an operator to inspect the channel.
