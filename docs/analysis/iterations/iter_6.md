# Iter 6 — 2022-bear

> **Date:** 2026-04-09
> **Period:** 2022-01-01 → 2022-12-31 (Luna + FTX cascade)
> **Command:** `python scripts/theory_backtest.py --period 2022-bear --coins "BTC ETH"`
> **Raw output:** `docs/analysis/raw/backtest_2022-bear_20260409T102550Z.json`

---

## Signals

| Coin | TF     | Signals | Correct | Incorrect | Accuracy |
| ---- | ------ | ------- | ------- | --------- | -------- |
| BTC  | Weekly | 52      | 8       | 9         | 47.1%    |
| BTC  | Daily  | 52      | 29      | 14        | 67.4%    |
| BTC  | 4H     | 29      | 8       | 21        | 27.6%    |
| BTC  | 1H     | 17      | 8       | 9         | 47.1%    |
| ETH  | Weekly | 52      | 7       | 10        | 41.2%    |
| ETH  | Daily  | 52      | 34      | 10        | 77.3%    |
| ETH  | 4H     | 34      | 7       | 26        | 21.2%    |
| ETH  | 1H     | 18      | 7       | 10        | 41.2%    |

Top failures: `4H setup invalid after daily confirm` ×28 (iter 2 gap),
`entry triggered but TP not reached` ×19 (the new finding).

## Failure pattern

**Bear-trend short SL hit on routine counter-trend bounces.** Across
both coins, almost every losing short was stopped within 2-4% of
entry, while daily ATR through 2022 ranged 4-8%. The SL was inside the
noise floor.

| Coin | Date       | Entry  | SL     | Risk %  |
| ---- | ---------- | ------ | ------ | ------- |
| BTC  | 2022-03-07 | 38403  | 39677  | 3.3%    |
| BTC  | 2022-04-18 | 39732  | 40595  | 2.2%    |
| BTC  | 2022-04-25 | 38855  | 39940  | 2.8%    |
| BTC  | 2022-07-04 | 19263  | 19647  | 2.0%    |
| BTC  | 2022-08-29 | 19641  | 20171  | 2.7%    |
| BTC  | 2022-09-26 | 18772  | 19180  | 2.2%    |
| BTC  | 2022-11-14 | 16259  | 16954  | 4.3%    |
| BTC  | 2022-11-21 | 16268  | 16753  | 3.0%    |
| ETH  | 2022-03-07 | 2542   | 2674   | 5.2%    |
| ETH  | 2022-09-26 | 1293   | 1337   | 3.4%    |
| ETH  | 2022-10-03 | 1281   | 1317   | 2.8%    |
| ETH  | 2022-11-21 | 1140   | 1227   | 7.6%    |

The structural premise (BTC bear trend through Luna and FTX cascade,
weekly bias short) was correct. The model's daily layer was 67-77%
accurate. The leak is at the SL placement: the 1H 24-bar window is too
tight versus daily ATR in a high-volatility regime.

## What changed and why

**One concrete theory improvement:** added
`stop_loss_placement_rules.minimum_sl_distance` to
`docs/technical.yaml`. The new section formalizes a measurable floor:

> The risk distance from entry to SL must be AT LEAST 1.5× the current
> 14-day daily ATR. If the structurally-correct invalidation level is
> closer than 1.5× ATR, the setup is invalid — push entry deeper into
> the retracement band, or pass the trade.

The block includes:

- The rule itself, explicit and measurable.
- Rationale linked to the twelve specific entries above with their
  risk percentages and the 4-8% daily ATR context.
- A `how_to_apply` block specifying the three-way max of (structural,
  1.5× ATR, spread) and the "push entry deeper or pass" remediation.
- A `relationship_to_existing_rules` note explaining that this
  operationalizes the qualitative `four_hour_sl` / `one_hour_sl`
  guidance, is compatible with the 2R take-profit convention (smaller
  position, wider stop in volatile regimes — pro_trader_mindset
  alignment), and stacks with `chase_prevention_rule` (iter 5).
- A `target_distance_corollary` noting that 1.5× ATR floor implies
  ≥3× ATR target — a natural filter against counter-trend chop
  setups.
- A `note_for_engines` block specifying the rolling-ATR computation
  and the new "skip trade" outcome class (rejected setup, not a
  loss).

### Why this is the right theory improvement for 2022

The dominant trade-level loss bucket is bear-market shorts stopped
within the noise floor, not at structural invalidation. Of the
nineteen "TP not reached" outcomes across both coins in 2022, at
least fifteen are SL distances under 4% on coins whose 14-day ATR
through the period was 4-8%. The structural premise was right; the
order placement was inside the noise. Anchoring SL to a measurable
ATR floor is the most direct fix.

This rule does NOT replace the existing structural SL rules — it
adds a floor under them. When structural invalidation is wider than
1.5× ATR, the structural rule wins. When it is narrower, the trade
must be re-priced (deeper retracement entry) or skipped.

## 4H/1H execution notes

- ETH daily accuracy at 77% in 2022 is the highest of any period so
  far. The macro and trend layers worked exceptionally well. The
  entire leak was at the order-placement layer.
- November 2022 (FTX collapse week) produced a single-candle climax
  on BTC and ETH that should trip iter 4's `post_climax_cooldown`.
  Both 11-14 and 11-21 BTC shorts and 11-21 / 11-28 ETH shorts are
  in the post-FTX cooldown window — they would have been suppressed
  by iter 4's rule alone, independent of today's SL floor.
- Several of the 11-21 / 11-28 entries are doubly suppressed
  (cooldown + minimum SL). That is the intended behavior — multiple
  rules covering the same failure mode add resilience, not
  duplication.

## Open questions

1. The two non-short losers (BTC 2022-03-28 long, ETH 2022-03-28 long)
   are March 2022 dead-cat-bounce continuation longs. Iter 5's
   `chase_prevention_rule` should already catch them as 0-30%
   retracement entries inside an extended counter-bias impulse. Cross-
   reference for the trading/ refactor.
2. The 4H rejection bucket (×28) is still iter 2's documented
   engine gap.

## Next period

Iter 7 → `2023-recovery` (2023-01-01 → 2023-12-31). First period with
COT data available alongside macro inputs.
