# Nave Agent Onboarding

How an autonomous agent (Nous Research Hermes, or any MCP-compatible
client) should use the Nave trading tools to run a daily scan and — with
explicit human approval — open a position on Hyperliquid.

This doc is the single entry point for wiring a new agent. It assumes
you've already cloned the repo, installed deps, and have wallets
configured via `WalletVault`.

---

## 1. Transport options

The same integration is exposed three ways. Pick one:

| Transport | Entry point | When to use |
|---|---|---|
| **MCP (stdio)** | `python trading/mcp_server.py` | Hermes, ironclaw, openfang, any MCP client |
| **Gateway JSON** | `HermesNaveIntegration.gateway_invoke({"tool": ..., "arguments": ...})` | In-process agents that can import Python |
| **CLI (daily cron)** | `python scripts/daily_scan.py` | Scheduled execution, no agent in the loop |

All three call the same `HermesNaveIntegration` methods, so the contract
is identical.

## 2. The seven tools

Grouped by purpose. All return structured JSON.

### Context — call once per session

| Tool | Purpose |
|---|---|
| `strategy_context()` | Current theory v2 config (iter 14), pooled backtest metrics, known blind spots (iter 16). Cache the result per session — it does not change mid-day. |
| `cot_report(coins=...)` | Latest COT positioning, bias, and historical percentile. Updated weekly (Fridays). |
| `cot_history(months=N, coins=...)` | Historical COT variation over N months. Use to check whether extreme positioning is new or has persisted. |

### Daily signals — call every trading day

| Tool | Purpose |
|---|---|
| `theory_v2_scan(coins=...)` | **Primary**. Runs the full top-down pipeline and returns the decision trace for each coin: `stage`, `reason`, `bias`, `fired`, and (when fired) full signal geometry. |
| `scan_history(days=N)` | Recent daily scans for drift detection — is today's stand-aside new or the 10th day of extreme COT? |
| `weekly_plan(capital=..., coins=...)` | COT-driven weekly plan with 4H structure. Complementary view to theory_v2_scan — different signal source, use to corroborate. |

### Action — call only when the agent wants to act

| Tool | Purpose |
|---|---|
| `recommend_position(coin_scan, capital_usd, leverage, risk_pct)` | Turn a fired scan entry into a concrete sized order. Returns notional, coin qty, margin required, RR at ZC1/ZC2, and a `suggested_mcp_call` block the agent can hand to `open_position` (dry-run by default). |

### Execution — MCP only, human-gated

Exposed by `trading/mcp_server.py` (not `hermes/integration.py`). These
**default to `dry_run=True`** — the agent must **never** flip this
without explicit human instruction.

| Tool | Purpose |
|---|---|
| `open_position(coin, side, size_usd, dry_run=True, testnet=True)` | Open a market position. |
| `close_position(coin, dry_run=True, testnet=True)` | Close an open position. |
| `list_positions`, `list_orders`, `account_summary`, `get_price`, `list_markets` | Read-only diagnostics. |

## 3. Daily flow

The canonical sequence an agent runs each trading day:

```
1.  strategy_context()                    → prime session, cite in final answer
2.  theory_v2_scan(coins="BTC ETH")       → today's decision trace
3.  scan_history(days=7)                  → is this new or a regime?
4.  For each coin where scan.coins[COIN].fired is True:
     a. Cross-check against strategy_context.known_blind_spots.
     b. recommend_position(coin_scan=<entry>, capital_usd=<user>, leverage=<user>)
     c. Present to the user as: bias, stage, velocity, RR,
        order summary, and — importantly — the reason block so the
        user can sanity-check before approving.
     d. If (and only if) the user approves in the same message,
        call open_position(..., dry_run=False, testnet=<user choice>).
5.  For coins that stood aside:
     - Report stage + reason from the scan in one line per coin.
     - Do NOT recommend a position.
```

## 4. Safety gates (non-negotiable)

- `dry_run=True` is the default for `open_position` and `close_position`.
  The agent must not change this unless the current user message
  explicitly authorizes a live order.
- `testnet=True` is the default. Flipping to mainnet requires explicit
  user instruction in the current message.
- Private keys are never exposed by any tool. Agents see only
  addresses.
- The scan itself is read-only — it cannot place or modify orders.
- `recommend_position` includes a `safety.default_dry_run: true` flag
  in its output. Agents surfacing this to the user should keep it.

## 5. Example Hermes system prompt

```
You are Nave's daily trading scanner, using the nave_trading MCP skill.

Each trading day:
1. Call strategy_context() once per session and cache the result.
2. Call theory_v2_scan(coins="BTC ETH").
3. Call scan_history(days=7) to check for regime persistence.
4. For each fired coin:
   - Cross-check against known_blind_spots from strategy_context.
   - Call recommend_position(coin_scan, capital_usd=<from user>,
     leverage=<from user>, risk_pct=0.01).
   - Present the recommendation with: bias, stage, velocity,
     entry/stop/targets, RR, notional, margin, and a one-paragraph
     "why" that cites both the pipeline stage that fired and any
     known_blind_spots that apply.
5. Stand aside if no coins fired — report each coin's stage and reason.

Hard rules:
- Never call open_position with dry_run=False or testnet=False unless
  the current user message explicitly authorizes live mainnet trading.
- Never fabricate signal numbers. Use only what theory_v2_scan and
  recommend_position return.
- If a tool errors, surface the error and stop — do not guess.
```

## 6. Example output the agent should produce

When a signal fires:

```
BTC — OPEN LONG (recommended)
  Stage fired  : fired (retrace 62% inside entry band)
  Bias         : long (weekly velocity +1.58 ATRs)
  Entry        : $72,000.00
  Stop-loss    : $70,000.00   (risk $100.00 = 1% of $10,000)
  ZC1          : $75,000.00   (+$150.00, RR 1.50)
  ZC2          : $80,000.00   (+$400.00, RR 4.00)
  Size         : 0.050000 BTC ($3,600.00 notional)
  Leverage     : 10x → margin $360.00

  Why: iter 14 momentum gate triggered (velocity > 1.2 ATRs).
  COT positioning within acceptable band (not 95th+ pctile).
  No known blind-spot flags. Approve with "yes, testnet" or
  "yes, mainnet" to submit; otherwise I stand down.
```

When no signals fire:

```
2026-04-21 — stand aside
  BTC: weekly_cot  — COT agrees with long but extreme (pct 95%) — reversal risk
  ETH: weekly_cot  — COT agrees with long but extreme (pct 95%) — reversal risk

  7-day history: both coins have been in weekly_cot all week.
  Not a blip — the market is at extreme positioning and we're
  waiting it out per iter 11 design.
```

## 7. Scheduling

See `ops/com.nave.daily-scan.plist.example` for a macOS launchd template
and `ops/README.md` for Linux cron instructions. Running the scan is
independent of the agent — the agent reads the persisted JSON via
`scan_history(days=1)` if needed.

## 8. Known blind spots the agent should mention

From `strategy_context().known_blind_spots` — cite explicitly when
relevant:

- **cot_extreme_block** (iter 11): weekly COT filter rejects setups when
  speculator positioning is at 95th+ percentile. By design, not a bug.
- **range_breakout_partial** (iter 18): iter 18's range-breakout fallback
  catches consolidation breakouts the momentum gate misses, but only
  when the prior 7-bar range is ≤ 1.5 weekly ATRs. Very deep
  consolidations may still fire late. COT filter still applies.
  **Confirmed by N1 post-mortem (2026-08-25):** the BTC 63k→78k rally
  (Mar–Apr 2026) was a 7-week gradual recovery from a liquidation crash
  with a 3+ ATR wide range. The gate fired only at the peak. No parameter
  modification produced a profitable earlier signal. Requires a new
  regime-transition detector, not a parameter tune.
  **N2 experiment (2026-08-25, REJECTED):** a structural post-crash
  recovery classifier (crash → EMA-20 reclaim + higher-low) was tested as
  a third weekly bias source. It strictly degraded the baseline (−4.28R,
  WR −18.7pp, 78% false-positive rate) and, critically, did NOT catch the
  2026 window (0/26 weekly arming on BTC). The blind spot remains OPEN —
  a naive daily-structure recovery detector is insufficient.

When a fire has `signal.bias_source == "range_breakout"` the agent
should mention that explicitly — the trade is a breakout play, not a
momentum-velocity play, and behaves differently on the first pullback.
