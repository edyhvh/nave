# Current Setup — BTC and ETH

> **Generated:** 2026-06-04 (operator stack: `nave daily` / `crypto position-review`)
> **Canonical entry:** COT + regime thesis + momentum 4H/1H + optional Deribit options
> **Theory v2 trace:** included per coin below — may differ from ENTER/WATCH when regime leads

**Do not use theory_v2 alone for entries.** The unified review can be bearish while
theory card still shows STAND ASIDE on weekly gates, or the reverse during transitions.

## Operator summary

- Enter: **1** · Watch: **1** · Stand aside: **0**

## BTC

```
ACTION    : WATCH
DIRECTION : short
SOURCE    : cot+regime
REGIME    : leg_down
```

- Confidence: **65%**
- Entry zone: $63,969 – $80,787
- Invalidation: —
- Playbook: COT-led bear leg — trail shorts; avoid fresh longs until COT resets.
- COT: **bearish** · Theory stage: `weekly`
- Regime thesis: **holding** (continuation_short, since 2026-06-02)

**Reasons**
- Regime: leg_down — COT-led bear leg — trail shorts; avoid fresh longs until COT resets.
- COT: bearish (conf 65%, P97)
- Fresh 4H breakdown after consolidation
- Options (deribit): call_butterfly [advisory — perp/regime primary]
- Regime thesis holding — prior COT-led leg still valid on structure

**Blockers**
- No momentum setup on 4H/1H
- Theory v2: weekly — no weekly bias (momentum velocity=-0.46 ATRs, no range breakout)
- Ranked call_butterfly failed quality gate: no ranked strategy passed quality gate.

**Instruments**
- Active lanes: `hyperliquid_perp, deribit_options:advisory`

- Deribit options lane: **options advisory**
- Ranked structure: `call_butterfly` (bias bearish)
  - Metrics: POP 59.12%, touch 84.52%, EV 61.94
  - **Advisory only** — quality gate blocked execution (income-first design; high touch / no conservative spread).
  - Ranked call_butterfly failed quality gate: no ranked strategy passed quality gate.
  - Blockers: `no_ranked_strategy_passed_quality_gate`
  - Summary: call_butterfly · EV=61.94 · POP=59.12% · touch=84.52% · advisory

**Theory v2 trace (reference)**
- Stage: `weekly`
- Fired: **False**
- Gate note: no weekly bias (momentum velocity=-0.46 ATRs, no range breakout)

## ETH

```
ACTION    : ENTER
DIRECTION : short
SOURCE    : theory_v2+regime
REGIME    : leg_down
```

- Confidence: **74%**
- Entry zone: $1,794
- Invalidation: $1,915
- Targets: $1,611, $1,490
- Playbook: COT-led bear leg — trail shorts; avoid fresh longs until COT resets.
- COT: **bearish** · Theory stage: `fired`
- Regime thesis: **holding** (leg_down, since 2026-06-02)

**Reasons**
- Regime: leg_down — COT-led bear leg — trail shorts; avoid fresh longs until COT resets.
- COT: bearish (conf 74%, P99)
- Theory v2 fired short
- Options (deribit): bear_put_debit_spread [advisory — perp/regime primary]

**Blockers**
- No momentum setup on 4H/1H
- Ranked bear_put_debit_spread failed quality gate: no ranked strategy passed quality gate.

**Instruments**
- Active lanes: `hyperliquid_perp, deribit_options:advisory`

- Deribit options lane: **options advisory**
- Ranked structure: `bear_put_debit_spread` (bias bearish)
  - Metrics: POP 56.48%, touch 84.93%, EV 4917.92
  - **Advisory only** — quality gate blocked execution (income-first design; high touch / no conservative spread).
  - Ranked bear_put_debit_spread failed quality gate: no ranked strategy passed quality gate.
  - Blockers: `no_ranked_strategy_passed_quality_gate`
  - Summary: bear_put_debit_spread · EV=4917.92 · POP=56.48% · touch=84.93% · advisory

**Theory v2 trace (reference)**
- Stage: `fired`
- Fired: **True**
- Gate note: no confirmed down-leg (permissive pass)

## How to refresh

```bash
nave daily --coins BTC,ETH
# or
python scripts/refresh_current_setup.py
python scripts/daily_scan.py --refresh-setup-doc
```

Writes this file from `review_positions()` plus theory_v2 trace. Regime theses persist in `var/state/regime_theses.json`.
