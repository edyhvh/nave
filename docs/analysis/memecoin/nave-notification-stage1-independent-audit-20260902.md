# EXECUTIVE VERDICT

**AUDIT FAIL — AUTONOMY SHOULD REMAIN PAUSED.**

The report is not an accurate description of the currently served Hermes implementation. The gateway is healthy as one multiplexed process and current NAVE cursors have no unseen terminal events, but the claimed notification fix is absent from the served Hermes checkout. The live watcher still sends every `completed` event and then uploads every valid referenced non-image file. The exact `t_db6c87dd` message was sent six seconds after its completion event, not resurrected by reconnect.

The local Stage-1 contract, four provider-complete Parquet row counts, frozen sample metadata, and existing A/C result artifacts are broadly supported. The canonical NAVE state and Kanban disagree about the current continuation, and the database contains five nonterminal NAVE-related blocked cards rather than one sole live continuation. No files were sent to Discord and no research continuation was performed by this audit.

# AUDIT SCOPE

Read-only audit on 2026-09-02. Inspected the audited report and companion JSON/review, NAVE Git history/worktrees, served Hermes source/configuration, systemd/process state, retained gateway logs, live Kanban SQLite in read-only mode, SOUL files, local Parquet metadata/manifests, and Stage-1 source/tests.

No code, config, SOUL, Kanban, state, queue, dataset, contract, or worktree was modified. No service was restarted; no Discord message, provider call, archive acquisition, model fit, or NAVE continuation was performed.

# REPORT UNDER AUDIT

Audited artifact: `docs/analysis/memecoin/nave-notification-hygiene-and-stage1-scale-20260901.md`. Its same-base JSON and review were also read.

Material claims include: central Hermes fix; silent routine completion; opt-in attachments; semantic stale-event suppression; persistent idempotency; one current NAVE child; Aug-31 completion; and frozen Stage-1 continuation readiness. The review itself records `semantic_freshness_missing: true`, which limits its stronger conclusion.

# IMPLEMENTATION COMMIT

NAVE report commit: `64da019b0ddf38b458a42271fab95b49256e9319`; parent `fcf10f8d4e94105642c644b0394e0f30f0674790`; branch `fix/m3-malformed-pair-resolution`; worktree `<repo-root>`.

That commit added the report/companions and modified `research/nave/state.json`. It did not contain Hermes source, configuration, SOUL, notification, or dispatcher changes. Later NAVE commits updated research artifacts/state and the Stage-1 script, not the served Hermes tree.

The claimed Hermes hash `821a00845c108dfaf7208c4f3f03e0f5b1420b6e` is absent from the active Hermes Git object database. The served Hermes checkout is clean at `180291162ff4df0d42b5dc4fecd08005cf7cebf9` on `main`. A separate development worktree contains a generic `gateway/attention_policy.py`, but it is not served and is not imported by its Kanban watcher.

# LIVE HERMES STATE

`hermes-gateway.service` is active with PID `1896193`, started 2026-09-02 04:43:59 CEST, executing `hermes_cli.main gateway run`. Configuration has `kanban.dispatch_in_gateway: true` and a 60-second dispatcher interval.

There is no active separate `hermes-kanban-dispatcher.service`. `hermes-gateway-quant.service` is disabled/failed with status 78 because a second inbound gateway would double-bind multiplexed credentials. The process tree shows one Hermes gateway and no second Hermes/dispatcher daemon. The single-gateway topology is PASS; it does not make the notification policy safe.

# DISCORD STATE

Persisted gateway state says Discord `connected`, last updated 2026-09-02 02:44:14 UTC, `needs_attention: false`, with the current process as writer. Logs show repeated disconnect/reconnect cycles, WebSocket health failures, slash-command sync timeouts, cron jobs reporting `platform 'discord' not configured/enabled`, and lost thread targets. Thus the adapter is connected now but not uniformly healthy across all producer/profile paths.

Configured multiplex routing maps channel `1514695031901126727` to profile `quant`. Quant's own Discord platform is disabled because the shared primary gateway owns the connection.

# t_db6c87dd FORENSIC TRACE

| Item | Observed |
|---|---|
| Task | `t_db6c87dd`, NAVE survival observability panel/Runner continuation |
| Profile/assignee | quant / quant |
| Created | Unix `1788284582` = 2026-09-01 19:43:02 UTC |
| Started/completed | `1788284713` / `1788285058` = 19:45:13 / 19:50:58 UTC |
| Completion event | event `2549`, kind `completed`, run `211` |
| Workspace | `<repo-root>/.worktrees/t_db6c87dd`, branch `wt/t_db6c87dd` |
| Subscription | Discord `1514695031901126727`, notifier profile quant, mode notify, cursor 2549 |
| Payload | routine summary plus Markdown, review JSON, and report JSON paths |
| Delivery | log 19:51:04.095/19:51:04.508 UTC; Discord message `1544404239600844980` |
| Attachments | Markdown at 19:51:04.742; two JSON files at 19:51:05.178 and 19:51:05.516 |
| Immediate reconnect | none; nearest reconnect was 21:46 UTC |

Root cause: the live watcher treated a routine `completed` event as visible, called `adapter.send`, and then called artifact delivery. This was immediate normal completion delivery, not a historical event released by reconnect. The report's concrete root-cause claim is FAIL.

# `[default] @quant` ROUTING

The live formatter builds the board prefix from the board slug and the assignee prefix from `task.assignee`. Here `[default]` is the Kanban board tag and `@quant` is the task assignee. The actual destination was the quant Discord channel and the subscription profile was quant. Classification: CONFUSING BUT CORRECT DISPLAY, not a routing bug.

# NOTIFICATION PRODUCER MAP

The actual Kanban path is:

```text
kanban_complete / kanban_block / dispatcher transition
  -> task_events in <hermes-kanban-db>
  -> kanban_notify_subs.last_event_id claim
  -> embedded gateway Kanban watcher
  -> profile-aware adapter
  -> adapter.send(text)
  -> for every completed event: path extraction -> send_document/media
```

Other user-facing producers remain separate: agent final/stream sends, generic `send_message` media sends, cron delivery obligations, slash-command responses, and wake self-posts. The Kanban watcher is authoritative for a Kanban subscription, but there is not one global notification producer and no cross-producer delivery ledger. Classification: DUPLICATE RISK.

# ROUTINE DONE POLICY

FAIL. In served `gateway/kanban_watchers.py:266`, `completed` is in `TERMINAL_KINDS). Lines 581–604 unconditionally construct `✔ [board] @assignee Kanban <id> done`; lines 742–745 unconditionally call `adapter.send`. No `notify_user` lookup exists in served Hermes.

The quant SOUL says to pass `notify_user=true`, but the current `kanban_complete` implementation neither defines nor consumes that field. Routine NAVE completion spam remains possible and was observed for `t_db6c87dd`.

# HISTORICAL REPLAY PROTECTION

The actual mechanism is numeric event ordering: `task_events.id > kanban_notify_subs.last_event_id`, filtered by event kind and ordered ascending. New subscriptions snapshot the current maximum event ID. Claims advance atomically before send; failed sends can rewind by CAS.

This prevents replay of an already advanced event under the same subscription. It does not distinguish a new transition from an old transition whose cursor is behind, reset, recreated, or absent. There is no event freshness/supersession check and no durable per-message delivery ledger. Classification: STILL POSSIBLE for the report's stronger claim.

# CURSOR / HIGH-WATER PERSISTENCE

The cursor is a persistent SQLite integer. `claim_unseen_events_for_sub` uses `BEGIN IMMEDIATE` and CAS, so it survives gateway/worker restart and serializes concurrent watchers. This is PASS for persistence, PARTIAL for semantics.

The cursor rewinds after failures and the subscription can be dropped after 12 in-memory send failures. Persistent high-water is not exactly-once delivery and is not semantic freshness.

# IDEMPOTENCY

Classification: PARTIAL. Persistent cursor plus event ID provides same-subscription dedupe across restart/process/reconnect. There is no outbound message ID/key ledger; send success followed by process failure is ambiguous, failures rewind, and the failure threshold can remove the subscription. Tests prove cursor mechanics, not provider-level exactly-once delivery.

# RECONNECT SEMANTICS

| Condition | Current behavior |
|---|---|
| Routine completed task | If adapter is absent, watcher skips before claim; if cursor remains behind, current code sends after reconnect. |
| Old RESULT/completed event | Same as any completed event if ID is above cursor; no age check. |
| Unresolved ACTION_REQUIRED | Blocked event remains eligible while adapter is absent and can send after reconnect, subject to ownership/failure handling. |
| Resolved ACTION_REQUIRED | Already advanced event does not replay; an old blocked event with a behind cursor can still send after resolution. |
| FAILURE/gave_up/non-retry timeout | Current source sends it; retry semantics are not centrally classified by this watcher. |

The prior runtime logged some “attention policy suppressed internal” events, but that integration is absent from the served source and did not suppress the t_db6 completion.

# PENDING STALE QUEUE

Current NAVE-specific pending count: **0**. The three NAVE subscriptions have cursors 2549, 2499, and 2668; no newer notifier-terminal event exists for any. The NAVE `pending_messages` path is empty. Root `state.db` has 182 `delivery_obligations`, all `delivered`, with no pending/nonterminal row.

This is an empty current backlog, not proof old messages can never fire: the producer still accepts any event above a cursor and old event history remains.

# ATTACHMENT PATH

FAIL. Served watcher lines 762–779 call `_deliver_kanban_artifacts` for every completed event. The helper scans `event_payload['artifacts']`, paths in the summary, and legacy `task.result`; it then sends every valid non-image/non-video path through `send_document`. There is no exclusion for JSON, Markdown, CSV, Parquet, or report files.

The old gateway log records exactly one Markdown and two JSON uploads after the t_db6 text. The desired text-only NAVE RESULT policy is not centrally enforced.

# ATTACHMENT BYPASS AUDIT

**CONFIRMED BYPASS.** The default completion path is the bypass: `kanban_complete(artifacts=[...])` places paths in the event payload and the watcher uploads them. Summary path extraction and legacy `task.result` are additional paths. Generic `send_message` has independent media-send behavior.

# ACTION_REQUIRED RELIABILITY

Classification: PARTIAL. Blocked events are subscribed and sent; the earlier `t_e8a16517` blocked event was logged as delivered, and adapter-offline skip leaves ordinary events eligible. But the claimed `notify_user` central implementation is absent, no durable Kanban delivery obligation is tied to event identity, repeated send failure can remove a subscription, and resolved gates are not semantically superseded.

# GLOBAL PROFILE IMPACT

The unsafe completion/attachment logic is in the shared watcher and has no quant/NAVE branch. The quant route is correctly selected, but default, dev, emunah, sofia, work, and other subscriptions can encounter the same behavior. Logs also contain unrelated “Normal final-send NOT suppressed … possible duplicate send” warnings for dev/sofia/quant. No NAVE report commit changed those profiles, but global impact cannot be certified absent.

# TEST QUALITY

Classification: FALSE-CONFIDENCE RISK.

Current focused Hermes tests: **47 passed in 51.49 seconds**. They cover cursor claims, retry/reopen, wake metadata, and skipping missing artifact files. They do not cover the claimed `notify_user`/ `notify_attachments` policy because those fields are absent from served source. One test explicitly expects a real PDF path to be uploaded by the notifier, opposite to the claimed default text-only policy.

NAVE tests, run with the existing Hermes virtualenv and no provider access: **25 passed in 0.19 seconds**. They cover label boundaries, censoring, migration/provider gaps, data-root safety, and resource guards. They do not integrate live Kanban/Discord or prove persistent ACTION_REQUIRED recovery. The test covers `decision_time_eligible`, but the Stage-1 audit script does not call that helper when building features.

The report's “focused 83” and “affected 192 passed, 1 skipped” totals were not reproducible from the current served checkout. No live Discord test was run.

# NAVE KANBAN GRAPH

Current main chain:

```text
t_e8a16517 (done ACTION_REQUIRED gate)
  -> t_f23e05ae (done bounded quality proof)
      -> t_94b561e8 (blocked: next three clean days)
      -> t_db6c87dd (done routine panel)
          -> t_5432bed0 (archived after timeout/gave_up)
              -> t_6070cb2f (archived Aug-31 child)
              -> t_81a4fb08 (blocked transient Sep-1 continuation)
```

Separate older proof branches remain:

```text
t_ab98aadd (done) -> t_b0fdb800 (blocked hold)
t_ce7db486 (done) -> t_177b76c5 (blocked hold)
t_89fda005 (blocked) -> t_8ef06fd7 (archived)
```

Every title-matching nonterminal NAVE task is blocked: t_b0fdb800, t_89fda005, t_177b76c5, t_94b561e8, and t_81a4fb08. The report's one-current-child statement is false. t81 is the only current Sep-1 child in the Day-5 chain, but it is blocked, not ready/running.

# DUPLICATE CONTINUATION RISK

Classification: MATERIAL risk, but no simultaneous active duplication observed. Old proof/recovery cards remain nonterminal, auto-decomposition is enabled, and multiple held branches exist. Current blocked status prevents them running now; releasing more than the intended branch could duplicate research.

# CANONICAL NAVE STATE

Main `research/nave/state.json` says `NEXT_BOUNDED_EXPERIMENT`, calls t81 the sole running continuation, and names 2026-09-01 as next. Live Kanban says t81 is blocked with no current run after a transient PumpApi-unavailable gate.

The isolated t81 state correctly records `BLOCKED_BY_PROVIDER_UNAVAILABLE`, 21/24 complete hours, hours 21–23 HTTP 404, no outcomes, and no Day-6 admission. Its Day-6 artifacts remain uncommitted in the t81 worktree. Canonical state is CONFLICTING/STALE relative to live continuation state.

# STABLE DATA ROOT

`research/nave/data_root.py` resolves linked worktrees to `<repo-root>/data`, honors `NAVE_DATA_ROOT`, and rejects escape paths. Acquisition manifests and Parquet files use that root. Stable data root is supported; task reports can still be stranded in worktrees, as t81 demonstrates.

# STAGE-1 CONTRACT

`docs/analysis/memecoin/nave-stage1-survival-contract-20260901.json` is schema `nave.stage1-survival-contract.v1`, frozen 2026-09-01 20:55Z. It defines 15m/30m/60m primary windows as valid BUY/SELL activity in left-open/right-closed `(launch_time+horizon, launch_time+horizon+5m]`, requires complete intervals, and preserves provider gaps, right censoring, and migration unknown.

`research/nave/stage1.py` implements boundary/status precedence and the NAVE tests pass. Contract is FROZEN. Limitation: the main audit script hardcodes `provider_complete=True` and does not apply `available_at <= decision_time`. The checked selected tapes had no observed `available_at > event_time` and no selected pre-decision rows available after the decision cutoff for Aug 29–31, so no realized leakage was found there.

# MODEL A FREEZE

Current Model A features are exactly: `age_seconds`, `log_return_to_decision`, `curve_progress`, `buy_volume_sol_raw`, `sell_volume_sol_raw`, `trade_count_raw`, `unique_buyers_raw`, and `migration_state`. The later script diff only adds an `evaluation_day` parameter. Classification: FROZEN.

# MODEL C FREEZE

Model C adds exactly: `new_buyer_acceleration`, `buy_volume_acceleration`, `sell_pressure`, and `trade_size_concentration`. No feature drift was found. Classification: FROZEN.

# EXPERIMENT DRIFT

Classification: DOCUMENTED_VERSION_CHANGE, not silent drift. Window, samples, missingness semantics, features, one-token/10m primary row, and clustered bootstrap remain consistent. The documented change is evaluation of the unchanged train-on-2026-08-28 comparison on later days. The point-in-time availability helper remains an enforcement gap.

# AUG 28 / AUG 29 DATA CHECK

Local Parquet metadata verifies:

| Day | Rows | SHA-256 | Local evidence |
|---|---:|---|---|
| 2026-08-28 | 254,522 | `8dbed19d...a91092b7` | 1,000-sample artifact; no launch manifest at canonical path |
| 2026-08-29 | 353,030 | `15933e1d...b0a0c4` | 24/24; 1,000-row frozen manifest; denominator 39,415 |
| 2026-08-30 | 294,446 | `9767abcd...22ff5ee` | 1,000-row frozen manifest; denominator 36,161 |
| 2026-08-31 | 555,201 | `e7233b7e...a6c6847` | 24/24; 1,000-row frozen manifest; denominator 37,540 |

Aug-28/Aug-29 expected counts are verified. Aug-28 has weaker local selection auditability because its launch manifest is absent. Aug-29/30/31 manifests record SHA-256 selection seeds and frozen-before-replay flags; Aug-29 and Aug-31 contain selection hashes sorted ascending.

# A VS C REPRODUCTION

No fresh model fit was run because this audit explicitly forbade fitting or research continuation. Existing Day-3 artifacts record A PR-AUC 0.3219880, C 0.2586926, C−A −0.0632954. Day-5 records A 0.2464115, C 0.2220270, C−A −0.0243845, with token-cluster intervals crossing zero. Current code confirms one 10m row per token and token-resampled bootstrap. Classification: NOT RUN INDEPENDENTLY; persisted values are supported but not freshly recertified.

# AUG 30 STATUS

**COMPLETE** locally: 24/24, 1,000 frozen sample mints, 294,446 normalized rows, canonical Parquet present, and zero provider gaps in the persisted Stage-1 artifact.

# AUG 31 STATUS

**COMPLETE** locally for the provider-complete day: 24/24, 1,000 frozen sample mints, 555,201 normalized rows, canonical Parquet/manifest present, zero recorded provider gaps. The next day, 2026-09-01, is **PARTIAL / NOT ADMITTED**: t81 records 21/24 and hours 21–23 unavailable; no outcomes or A/C result was computed.

# SAFETY BOUNDARIES

NAVE state/reports retain `NO EDGE VALIDATED`, research-only language, and no operational trading inference. Reports reject profitable, executable, BUY/SELL, and live-filter conclusions. The report commit changed no trading or wallet code. The NAVE checkout has unrelated dirty user files, including trading/backend files; they are not attributable to the report commit and were not modified by this audit.

The resource guard is fail-closed with 25-credit target, 50 warning, 75 hard stop, 200 checkpoint cap, and 15 GiB disk floor. Cached local state records 2,028.729/2,500 Dune credits used and 471.271 remaining; no live balance was queried. Deterministic acquisition chunks count as progress only when they genuinely add verified coverage; incomplete t81 coverage was correctly not admitted.

# FINDINGS BY SEVERITY

## P1

1. Claimed Hermes fix commit is absent from served checkout; routine completed notifications remain enabled.
2. t_db6 was delivered immediately as a normal completion, disproving the report's stale-reconnect RCA.
3. Completion handling uploads Markdown/JSON/other referenced files by default; text-only opt-in is absent.
4. Multiple nonterminal NAVE branches remain, while canonical state says the sole continuation is running and live Kanban says blocked.

## P2

1. Cursor persistence lacks semantic freshness and a durable delivery ledger.
2. Tests do not prove the claimed RESULT/ACTION_REQUIRED/attachment policy; report totals are not reproducible.
3. Discord has repeated reconnect/rate-limit/profile-specific warnings; `[default] @quant` is confusing but correct.
4. Feature code does not enforce the available-at helper, although no realized local violation was found.

## INFO

1. Current NAVE terminal backlog above subscription cursors is zero.
2. Single gateway/embedded dispatcher topology is confirmed.
3. Four local provider-complete Stage-1 Parquet artifacts and frozen contract are present.

# CLAIM-BY-CLAIM MATRIX

| Claim | Expected evidence | Observed evidence | Verdict | Severity |
|---|---|---|---|---|
| Routine NAVE done is silent | served watcher gates completed on explicit flag | watcher sends every completed event; t_db6 delivered | FAIL | P1 |
| Old NAVE notifications cannot replay | persistent cursor plus semantic freshness | persistent numeric cursor, no freshness check | PARTIAL | P1 |
| t_db6 was stale reconnect delivery | send after reconnect without new event | completion 19:50:58; send 19:51:04; reconnect later | FAIL | P1 |
| Artifacts are opt-in | central notify_attachments gate | completed path always uploads valid paths | FAIL | P1 |
| Idempotency is durable/exact | persistent delivery identity/ledger | persistent cursor; no delivery ledger | PARTIAL | P2 |
| ACTION_REQUIRED is reliable | offline persistence and resolved supersession | blocked path exists; no durable obligation/supersession | PARTIAL | P1 |
| `[default] @quant` is not misrouting | formatter and profile route agree | default board + quant assignee; quant channel route | PASS | INFO |
| Exactly one notification path exists | all producers converge with dedupe | watcher plus final/send_message/cron/wake paths | PARTIAL | P2 |
| One current NAVE child exists | enumerate all nonterminal NAVE tasks | five title-matching cards blocked; t81 not running | FAIL | P1 |
| Canonical state is current | state matches live DB/worktree | main says running; DB says blocked; t81 partial | FAIL | P1 |
| Stable data root is canonical | resolver/manifests use shared root | `<repo-root>/data`; tests pass | PASS | INFO |
| Stage-1 contract is frozen | contract/code/tests agree | contract/stage1.py agree; helper enforcement gap | PASS | INFO |
| Model A is frozen | exact feature list unchanged | eight features; only eval-day plumbing changed | PASS | INFO |
| Model C is frozen | exact four precursor features unchanged | exact four features; no drift | PASS | INFO |
| A/C is independently reproduced | fresh frozen-code local replay | not run; fresh fit prohibited; artifacts persist | NOT_VERIFIABLE | P2 |
| Aug-28/Aug-29 counts are real | local metadata/manifests | Parquet rows and Aug-29 manifest verified | PASS | INFO |
| Aug-30/Aug-31 are complete | 24/24 evidence and Parquet | both complete locally; Sep-1 partial | PASS | INFO |
| No unrelated behavior was affected | diff/runtime review | report commit docs/state only; global warnings remain | PARTIAL | P2 |
| Resource boundary is safe | fail-closed guard and no audit calls | guard/tests pass; no provider calls by audit | PASS | INFO |

# AUTONOMY GO / NO-GO

**NO-GO.** ABI/QUANT should not continue NAVE autonomously toward 5–7 days until a separate repair/reconciliation session establishes the claimed policy in the actually served Hermes checkout, adds persistent semantic delivery tests, and reconciles the extra NAVE branches and canonical state.

# RECOMMENDED NEXT ACTION

Keep autonomous NAVE paused. In a separate repair session, deploy and verify one served notification policy with explicit RESULT/ACTION_REQUIRED semantics and text-only default, add offline/reconnect/idempotency tests, then reconcile the five blocked NAVE cards and main state before releasing only the predeclared Sep-1 retry.
