# Iter 18 — Range-breakout fallback for the iter 16 blind spot

> **Date:** 2026-04-21
> **Scope:** Theory addition. Iter 16 identified range-breakout patterns
> as the momentum gate's structural blind spot. Iter 18 implements the
> "A. Range-breakout detector" option from that iter as a fallback bias,
> gated behind the existing `momentum_bias` so it only fires when the
> primary gate stays neutral.

---

## Why this iteration exists

Iter 14 converged the momentum gate but left one documented blind spot
(iter 16): a 4–8-week flat consolidation followed by a breakout. The
4-week momentum window cancels over the consolidation, so the gate only
fires 1–2 weeks *after* the breakout — too late. The Apr 2026 BTC rally
was the motivating example ($76,361 vs $72,963 ideal, ~4.5% late).

Iter 16 recommended a separate range-breakout gate that can fire
alongside the momentum gate. Iter 17 was productization (agent wiring);
this iter is the theory addition.

## What changed

### `trading/theory_v2.py` — new gate function

`range_breakout_bias(weekly, ...)` returns `(bias, diagnostic)`:

- Looks at the last 7 weekly closes (excluding the current bar) and
  computes high-low range, normalized by weekly ATR-8.
- If the prior range is ≤ 1.5 ATRs wide → considered "flat".
- If the current close breaks above `range_high + 0.5 × ATR` → long.
- Symmetric for short.
- Otherwise neutral, with a diagnostic explaining why.

### `TheoryV2Engine.evaluate` — fallback wiring

```python
bias, velocity = momentum_bias(weekly)
bias_source = "momentum"
breakout_diag = None
if bias == "neutral":
    rb_bias, breakout_diag = range_breakout_bias(weekly)
    if rb_bias != "neutral":
        bias = rb_bias
        bias_source = "range_breakout"
    else:
        return TheoryV2Decision(... "no weekly bias ...")
```

The momentum gate still has priority — if velocity is strong enough,
use it (and its velocity reading). The fallback only activates when
momentum is silent. Both paths then go through the same
`weekly_cot_filter / daily / climax / chase / 4H / 1H` sequence, so
execution geometry is unchanged.

`bias_source` and the `range_breakout` diagnostic are surfaced in the
signal metadata so the agent can tell which gate fired.

### Tests

`tests/test_theory_v2.py` gains 5 new cases for `range_breakout_bias`:
empty frame, wide prior range, fresh breakout long, breakdown short,
flat-no-breakout.

## Backtest validation — strict Pareto improvement

Re-ran `scripts/theory_v2_backtest.py` on the full 9-period window
(BTC + ETH). Result vs iter 14 baseline:

| Metric | Iter 14 | Iter 18 | Δ |
|---|---|---|---|
| BTC fires | 21 | **22** | **+1** |
| BTC WR | 76.5% | **77.8%** | **+1.3pp** |
| BTC total R | +19.19 | **+20.79** | **+1.60R** |
| BTC avg R/trade | +1.13 | **+1.155** | +0.025 |
| ETH fires | 25 | 25 | 0 |
| ETH WR | 78.9% | 78.9% | 0 |
| ETH total R | +23.35 | +23.35 | 0 |
| **Pooled total R** | **+42.54** | **+44.14** | **+1.60R** |

One extra BTC trade, it wins, and WR ticks up — no ETH change, no
regressions in any existing regime period. This is the cleanest possible
"add a gate" result.

**Raw:** `docs/analysis/raw/theory_v2_validation_20260421T200957Z.json`

## Why ETH is unchanged

The iter 16 diagnosis was BTC-specific (Apr 2026 rally was a BTC range
breakout). ETH's momentum gate was already catching its move set; ETH
did not have a flat-consolidation-then-breakout in the backtest window
that the range gate could add. That's fine — iter 18 is strictly
additive, not a replacement.

## Caveats / remaining blind spots

Renamed the iter 16 blind spot to `range_breakout_partial` in
`strategy_context`:

- **`max_range_atrs=1.5` is a hard floor.** Very deep or extended
  consolidations that span a wider range (say, 2+ ATRs) still won't
  satisfy the "flat" test. Tightening is possible (iter 19 candidate)
  but risks false positives.
- **COT filter still applies.** A range breakout during 95th-percentile
  speculator positioning still gets blocked at `weekly_cot` — by design.
  The iter 16 Apr-2026 BTC case was ultimately blocked by COT, not by
  the momentum gate; iter 18 doesn't change that outcome for extreme
  COT regimes.

## Updated `strategy_context`

Version bumped to `theory_v2.iter_18`. Pooled metrics updated. New
`range_breakout` parameters section. `range_breakout_partial` replaces
`range_breakout` in `known_blind_spots` with clearer scope.

## Decision

**Ship.** Strict improvement. Integrated with the existing agent
wiring — no tool signatures change, the agent just sees the new
`bias_source` and `range_breakout` fields in `signal` metadata when the
fallback fires.

## Follow-ups (not in this iter)

- **iter 19 candidate:** sweep `max_range_atrs` ∈ {1.2, 1.5, 2.0} and
  `breakout_buffer_atrs` ∈ {0.3, 0.5, 0.8}. Might squeeze more out, but
  1.5 / 0.5 already ship cleanly.
- **iter 20 candidate:** daily cron scheduling (ops/ templates are
  ready, just needs the user to install the plist).
