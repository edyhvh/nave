STAGE-1 SURVIVAL MATERIAL PROGRESS

# NAVE notification hygiene and Stage-1 scale audit — 2026-09-01

## EXECUTIVE STATUS

The existing Hermes notifier was corrected at its central Kanban notification
layer. Routine task completion is now internal-only, completion artifacts are
not uploaded by default, and only an explicitly marked current RESULT can
produce a completion notification. The per-subscription durable cursor and
atomic claim path remain in use for idempotency and reconnect safety.

NAVE is active on the existing quant chain. Aug 31 is now complete as the
fourth comparable event-level day; the parent exceeded its bounded runtime
after producing the panel, and exactly one current child task, `t_81a4fb08`,
is ready for the next predeclared day. No second dispatcher, daemon, gateway, NAVE chain,
trading path, wallet action, purchase, or scanner change was introduced.

## STALE MESSAGE ROOT CAUSE

The late message was a historical Kanban `completed` event that remained
eligible for user delivery. The notifier already had a per-task
`last_event_id` cursor, but completion classification did not distinguish a
routine old completion from a meaningful current RESULT. Reconnect/startup or
delayed consumption could therefore surface an old task transition as if it
were current.

## t_db6c87dd TRACE

Task `t_db6c87dd` was created at Unix time 1788284582 and completed at
1788285058. Its completion event was event 2549, with a routine summary and
local report/review/JSON artifact paths. The notifier subscription for quant
channel `1514695031901126727` now has `last_event_id=2549`. There is no new
task transition associated with the late user-facing message; it was an old
completion consumed by the notifier under the former visibility policy.

The same pattern was present for the older `t_f23e05ae` completion (event
2511). Legacy events without the new opt-in field are deliberately treated as
internal, not replayed as results.

## DISCORD ROUTING

The configured quant route is Discord channel `1514695031901126727` (`#quant`),
mapped to profile `quant` by the existing multiplex profile route. The gateway
is active after a controlled restart and the existing quant worker remained
alive. No profile mapping was changed.

## `[default] @quant` EXPLANATION

The old string was a formatter combining the default board tag with the task
assignee; it was not evidence that the Discord destination had changed to the
default profile. The new explicit RESULT formatter uses the quant identity
without the misleading board/task-completion prefix. This is a presentation
correction in the existing watcher, not a new route.

## NOTIFICATION PRODUCERS

The authoritative user-facing Kanban path is the existing
`gateway/kanban_watchers.py` route through `gateway/attention_policy.py`.
Routine lifecycle events remain internal. `blocked`, `review_requested`, and
human-gate states retain attention semantics; terminal failures retain
failure semantics. The worker can request a meaningful current RESULT through
`notify_user=true` on `kanban_complete`. The quant SOUL received a surgical
clarification matching this central policy.

## HISTORICAL REPLAY BUG

This was a semantic visibility bug, not proof that the durable cursor was
absent. `add_notify_sub` snapshots the current event high-water mark and
`claim_unseen_events_for_sub` atomically advances it, with delivery failure
rewind behavior. The missing rule was that a legacy or routine `completed`
event must be consumed silently. The fix adds that rule while retaining the
existing cursor and delivery idempotency.

## ATTACHMENT ROOT CAUSE

The watcher previously called its artifact delivery routine for every
completed event. Completion payloads can contain the locally persisted report,
review, JSON, CSV, or other artifact paths, so those paths were eligible for
Discord uploads even though the research artifacts themselves were correct.

## FIX

Hermes commit `821a00845c108dfaf7208c4f3f03e0f5b1420b6e` makes both behaviors
opt-in:

* routine `completed` events classify as INTERNAL unless
  `notify_user=true` is present;
* completion artifact upload occurs only when `notify_attachments=true` is
  explicitly present;
* an explicit completion RESULT is concise and does not expose an internal
  Kanban `done` card by default;
* existing local artifact persistence and Kanban history are unchanged.

## IDEMPOTENCY

The existing per-subscription event cursor remains the stable delivery
identity: subscription/task plus event ID. Claiming advances the cursor
atomically and failed delivery rewinds it for attention-required cases. The
new policy means old routine events may be consumed once without creating a
late user message. Explicit current results still pass through the existing
claim/delivery path.

## HIGH-WATER/CURSOR

The live database contains `kanban_notify_subs.last_event_id`. The old NAVE
subscriptions are at their historical completion high-water marks; the active
chain subscription is at its creation event 2550 and the Aug 31 child is at
its creation event 2582. No stale NAVE notification backlog was found after
cursor reconciliation. Research artifacts and Kanban history were not
deleted.

## RECONNECT POLICY

After restart the gateway is active and the quant worker continues. Routine
old completions are now silently consumed rather than replayed. Existing
ACTION_REQUIRED events remain durable under the attention policy; delivery
failure retains/rewinds those events. The only startup warnings observed were
pre-existing unresolved multiplex secret-scope checks for optional tools, not
Discord route loss or a notifier flood.

## CONTROLLED TEST

The focused notifier suite passed routine-completion silence, explicit RESULT
delivery, ACTION_REQUIRED delivery, wake scope, old-event handling, and
attachment opt-in behavior. The broader affected Hermes suite passed
`192 passed, 1 skipped` in 70.81 seconds. A fresh concise text-only RESULT was
sent once through the existing Hermes Discord send path to `#quant`; it used
no MEDIA reference and no attachment.

The automated coverage verifies that a legacy completed event is consumed
without text delivery, explicit RESULT is delivered once, ACTION_REQUIRED is
retained, and artifact delivery is opt-in. A native live Discord send was
accepted successfully. No synthetic task was left in the live Kanban graph.

## STALE QUEUE CLEANUP

No pending stale NAVE notification requiring deletion was present after the
cursor audit. The safe cleanup was policy-based supersession: old routine
events remain in history but cannot become user-visible under the new rule.
No Discord history, Kanban history, research artifact, credential, or
unrelated queue entry was deleted.

## NAVE CURRENT STATE

The parent NAVE task is `t_5432bed0`, now archived after exceeding its
1,800-second bounded runtime after completing Day-5 artifacts. Its isolated worktree is at
`/home/david/nave/.worktrees/t_5432bed0` on `research/nave-stage1-scale`,
commit `48e95f8`. It records four comparable event-level days: Aug 28, Aug 29,
Aug 30, and Aug 31. The stale duplicate Aug-31 task `t_6070cb2f` was archived;
the sole current child is `t_81a4fb08` for 2026-09-01.

## FROZEN EXPERIMENT

The Stage-1 A/C contract remains unchanged: 10-minute primary decision,
five-minute post-horizon activity window, deterministic 1,000-launch daily
sample selected before replay, frozen Model A state features, frozen Model C
precursor features, explicit migration/right-censor/provider-gap handling,
and token-clustered uncertainty. The Day-4 comparison was exploratory: C
outperformed A directionally on Aug 30, but its bootstrap interval crossed
zero; no edge or economic claim follows. Participant B/D remain deferred.

## CANONICAL CONTINUATION TASK

`t_5432bed0` is the completed-but-time-bounded parent record. Its Day-5
artifacts were committed at `48e95f8` before the timeout. The stale duplicate
child `t_6070cb2f` is archived, and `t_81a4fb08` is the sole ready continuation:
acquire and validate predeclared 2026-09-01 with the same frozen targeted replay
architecture, then continue one day at a time toward the 5–7 day checkpoint if
quality and resource gates remain satisfied.

## AUG 30 STATUS

Aug 30 is complete: 24/24 PumpApi archive hours, 1,000 frozen sample mints,
294,446 retained normalized event rows, zero provider gaps, maximum three
replay workers, no raw decompressed archive retained, and approximately
11.35 GB compressed streamed. The final Parquet is approximately 43 MB. The
Day-4 and Day-5 reports classify the A/C results as preliminary/unstable and
keep the edge flag false. Day 5 contains 555,201 retained rows and zero
provider gaps.

## 5–7 DAY PLAN

Continue 2026-09-01, then use the predeclared/outcome-independent historical
date rule one validated day at a time. Keep internal chunk/child progress silent.
At 5–7 comparable days, produce the per-day matrix, clustered uncertainty,
calibration, temporal stability, Stage-2 readiness, Runner readiness, and the
10–14 day information-value decision. Do not tune C after a day-level result.

## RESOURCE GUARDS

At the notification-fix checkpoint Dune usage was 2,027.345 / 2,500 included
credits; the current verified snapshot is 2,028.729 / 2,500, leaving 471.271
after the running quant continuation's bounded research query. The
notification-fix work itself made no Dune query and used 0 new Dune credits.
Disk has
approximately 52 GiB free and memory reports approximately 6.1 GiB
available, above the existing NAVE disk guard. PumpApi remains the preferred
historical source; no purchase, upgrade, or new provider was used.

## REMAINING LIMITATIONS

The parent task timed out after completing Day-5 acquisition and analysis; the
artifacts are preserved in commit `48e95f8` and the main checkout in
`0bac49d`. The stale duplicate was archived, the parent was archived as a
completed historical record, and the sole Sep-1 child `t_81a4fb08` was spawned
by the existing dispatcher. Runner coverage is
descriptive and not an executable-profit result; all-migrant continuation and
participant history remain incomplete. Gateway startup still logs unrelated
optional-tool secret-scope warnings that should not be conflated with Discord
notification hygiene.

## CONCLUSION

The notification recurrence path is fixed at the correct central layer and
validated by focused plus affected-suite tests. NAVE has already advanced to
three comparable event days and one native quant child for Aug 31. The correct
user-facing behavior is now quiet internal continuation, one concise current
RESULT at meaningful checkpoints, and durable ACTION_REQUIRED/ALERT/FAILURE
only when genuinely relevant. `EDGE_VALIDATED` remains false.
