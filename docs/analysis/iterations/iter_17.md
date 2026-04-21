# Iter 17 — Agent wiring: expose theory v2 to Hermes

> **Date:** 2026-04-21
> **Scope:** Productization. No theory change. Iter 14 converged on the
> research side; this iter makes the engine reachable by the autonomous
> agent (Nous Research Hermes) so it can run a daily scan, cite the
> strategy context, and (with safety gates) recommend positions.

---

## Why this iteration exists

The user's ultimate goal: an agent that "is aware of everything on our
strategy, testing, theory" and can daily "scan the market and tell if we
should submit a position." As of end of iter 16 the research side was
ready (iter 14 converged, iters 15–16 documented blind spots) but the
engine was unreachable from the agent surface:

- `hermes/integration.py` exposed 3 tools: `cot_report`, `cot_history`,
  `weekly_plan`. Zero theory_v2 references.
- `trading/theory_v2.py::evaluate_coin_live` and `build_signals_for_coins`
  existed but had no MCP/gateway wrapper.
- No daily-cadence entry point.

The agent literally could not see the momentum gate we spent iter 13–14
building.

## What changed

### 1. Two new Hermes tools

`hermes/integration.py` gains:

- **`theory_v2_scan(coins="BTC ETH")`** — calls `build_signals_for_coins`
  and returns structured JSON with per-coin decision trace: `bias`,
  `stage` (weekly / weekly_cot / daily / climax_cooldown / chase_gate /
  4H / 1H / fired), `reason`, and, when fired, full signal geometry
  (entry, stop, targets, zc1_rr, velocity, daily_atr_14, retrace).
  Includes a `summary` block with `fires`, `fire_count`, and
  `evaluation_errors`.

- **`strategy_context()`** — static summary of iter 14: pipeline order,
  parameters (`min_velocity=1.2`, `lookback=4`, chase 50–95%, climax 3×
  ATR), pooled backtest metrics (WR 77.8%, avg R +1.18, total R +42.54,
  per-coin and regime breakdown), and `known_blind_spots` (range
  breakouts from iter 16; extreme-COT blocks from iter 11).

Both are registered in `list_tools()` and `dispatch_tool_call()` so
Hermes auto-discovers and gateway invocation works.

### 2. MCP server registration

`trading/mcp_server.py` gets two new `@mcp.tool()` wrappers that delegate
to the same `HermesNaveIntegration` instance. Any MCP client (ironclaw,
openfang, Hermes) sees both tools.

### 3. Daily-scan CLI

`scripts/daily_scan.py` — single-command entry point for cron/launchd:

```
python scripts/daily_scan.py --coins "BTC ETH" --out var/reports/daily_scan.json
```

Returns the combined payload (scan + context) and, in human mode,
prints a per-coin one-liner plus any fires.

### 4. Tests

`tests/test_hermes_integration.py` gains 4 new cases covering:

- `theory_v2_scan` happy path (BTC fires, ETH stage=weekly) with
  monkeypatched `build_signals_for_coins`
- `theory_v2_scan` rejects empty coin list
- `strategy_context` surface (version, params, metrics, blind spots)
- `dispatch_tool_call` routes both new tools

Existing tests updated to assert the new tool names in `list_tools()`.

### 5. Docs

`docs/technical.yaml` gains an `agent_integration` section that
documents both tool contracts, the daily-scan CLI, and the safety gates
(MCP trading tools default to dry_run=True; scan is read-only).

## Usage pattern (what the agent does each day)

```
1. strategy_context()             → cache iter 14 config + edge + blind spots
2. theory_v2_scan(coins=...)      → get decision trace
3. For each fired coin:
   a. Inspect signal geometry (entry, stop, zc1_rr, velocity).
   b. Cross-reference known_blind_spots — is this a regime the gate
      is known to mis-fire in?
   c. If confident, stage a dry-run open_position call or flag for
      human approval.
   d. Otherwise stand aside, citing stage + reason from the scan.
4. Never flip dry_run=False without explicit human instruction.
```

## Test results

```
pytest tests/test_hermes_integration.py  → 8 passed
pytest --ignore=extensions/openbb_treasury  → 88 passed
```

(The `openbb_treasury` collection error is pre-existing, unrelated to
this iter — confirmed by stashing these changes and reproducing.)

## Decision

**Ship.** Iter 14 (theory) + iter 17 (agent wiring) are the minimum
viable ready-state for the daily-scan goal. Merge `feat/theory_refinement`
→ `main`.

## Out of scope (future iters)

- **iter 18 candidate:** range-breakout detector from iter 16 — would
  recover the Apr-2026 BTC rally miss. Separate gate, not a tune.
- **iter 19 candidate:** daily scheduling — launchd/cron plist that
  invokes `scripts/daily_scan.py` and pipes the result to Hermes. Can
  live outside the repo as infra.
- **iter 20 candidate:** `open_position_from_signal(scan_result)` helper
  so the agent can act on a scan payload in one tool call instead of
  re-marshaling. Deferred until the human+agent workflow is proven.
