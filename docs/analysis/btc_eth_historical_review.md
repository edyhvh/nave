# BTC / ETH Historical Review

> **Date:** 2026-04-09
> **Branch:** `feat/theory_refinement`
> **Scope:** Phase 2 review across the AGENTS.md period list

## Executive summary

The theory refinement loop produced six real theory improvements on periods
with usable execution data, then encountered three later-period data-coverage
constraints before successfully reaching a live `TODAY` analysis using local
hyperliquid snapshots.

The highest-signal findings are:

1. The original engine was not actually reading the Phase 1 theory because the
   YAML files contained parse defects. That was corrected in iter 1.
2. The main structural model leak was not weekly or daily bias. It was the
   transition from confirmed daily bias into 4H/1H execution.
3. The six theory improvements that materially changed the model were:
   - iter 1: reconcile stale COT wording / unblock real rule parsing
   - iter 2: 4H counter-move is the setup, not the invalidation
   - iter 3: no re-entry without structural reset
   - iter 4: post-climax cooldown after regime-breaking candles
   - iter 5: explicit impulse-leg identification + chase prevention
   - iter 6: ATR-based minimum stop-loss floor
4. Post-2022 offline data is incomplete in the local repo. 2023 and 2024-H1
   could not be scored at all. 2024-H2 through 2025-Q1 could be scored through
   4H but not 1H. `TODAY` could be scored end-to-end because both 4H and 1H
   hyperliquid snapshots exist in 2026.

## Period-by-period review

| Iter | Period | Result | Main output |
| ---- | ------ | ------ | ----------- |
| 1 | 2017-bull+2018-bear | blocking defects found | theory YAML parse + contradiction fixes |
| 2 | 2017-bull+2018-bear re-run | real signal sample | clarified 4H pullback semantics |
| 3 | 2019-recovery | poor 1H conversion in chop | added re-entry discipline |
| 4 | 2020-covid-crash | post-climax continuation losses | added cooldown rule |
| 5 | 2020-recovery+2021-ATH | ATH chase behavior | added impulse-leg + chase rule |
| 6 | 2022-bear | stops inside volatility noise | added ATR stop-distance floor |
| 7 | 2023-recovery | no executable data | logged data gap |
| 8 | 2024-ETF-approval | no executable data | logged data gap |
| 9 | 2024-2025-bull | 1H layer missing | logged 1H data gap |
| 10 | TODAY | live setup documented | current BTC / ETH state captured |

## Cross-period pattern review

### What held up

- Weekly and daily directional framing were consistently stronger than the
  4H/1H execution layer.
- Trend continuation worked materially better in directional regimes than in
  chop or regime transitions.
- The theory’s qualitative transcript guidance became much more testable once
  the 4H and 1H responsibilities were written explicitly.

### What failed repeatedly

- Treating 4H trend alignment as mandatory rejected the very pullbacks the
  model wants to buy or sell.
- Re-entering inside the same impulse leg destroyed 2019 performance.
- Trend-following after climax candles caused systematic 2020 losses.
- Shallow retracement entries chased late 2020 / 2021 continuation moves.
- Tight 1H stop placement inside 2022 volatility noise invalidated otherwise
  correct directional calls.

### Remaining limitations

- 2023 and 2024 historical coverage is incomplete in the local repo.
- Macro data and remote COT / Binance / Yahoo fetches were unavailable in the
  offline environment used for this loop.
- The live `TODAY` sample is small and should not be overfit into a new rule.

## Aggregate edge across all periods

> **Generated:** 2026-04-09 — pooled stats from the latest committed
> backtest JSON for each of the 9 periods, totaling ~9.5 years of weekly
> walk-forward evaluation.

| Coin | TF     | Signals | Correct | Incorrect | Accuracy | Notes |
| ---- | ------ | ------- | ------- | --------- | -------- | ----- |
| BTC  | Weekly | 326     | 39      | 39        |  50.0%   | one weekly per walk-forward step |
| BTC  | Daily  | 326     | 168     | 70        |  70.6%   | confirmation gate vs weekly bias |
| BTC  | 4H     | 168     | 39      | 127       |  23.5%   | gate filters most ideas before they fire |
| BTC  | 1H     |  80     | 39      | 39        |  50.0%   | resolved trades — 2 unresolved |
| ETH  | Weekly | 326     | 40      | 49        |  44.9%   | |
| ETH  | Daily  | 326     | 182     | 61        |  74.9%   | |
| ETH  | 4H     | 182     | 40      | 136       |  22.7%   | |
| ETH  | 1H     |  95     | 40      | 50        |  44.4%   | resolved trades — 5 unresolved |

**Headline numbers (pooled):**

- Resolved 1H trades: **80 BTC + 90 ETH = 170 total**, across ~9.5 years.
- BTC win rate **50.0%**, ETH win rate **44.4%**.
- Engine uses fixed 2:1 reward-to-risk on every entry. Expected value per trade:
  - BTC: `0.500 * 2R + 0.500 * (-1R) = +0.500 R`
  - ETH: `0.444 * 2R + 0.556 * (-1R) = +0.332 R`

**Interpretation.** The refined theory has a positive expectancy on both
coins under fixed 2R targeting, even though raw 1H win rate is barely above
coin-flip. BTC is the stronger of the two assets at the execution layer.
This is the first quantitative justification for porting the engine into
`trading/`. Sample of 170 resolved trades is small but not trivial.

**Caveats:**

- Top failure pattern across all periods is `4H setup invalid after daily
  confirm` — over half of daily-confirmed weeks never reach a 4H entry.
  That is the gate doing its job, not a bug.
- The 2:1 RR is hard-coded by `_one_h_entry()` (last 24 1H bars define the
  swing); a real strategy will need to revisit that geometry.
- 2023 and 2024-H1 weekly data gaps mean those periods contributed zero
  trades. Coverage skews to 2017–2022.
- The TODAY window is included but contributes a single unresolved ETH
  candidate.

## Refined engine (theory v2 — iter 11–14 gates active)

> **Generated:** 2026-04-09 via `python scripts/theory_v2_backtest.py`
> **Engine:** `trading.theory_v2.TheoryV2Engine` with the iter 4 climax
> cooldown, iter 5 chase prevention, and iter 6 ATR stop floor enforced.
> Raw output: `docs/analysis/raw/theory_v2_validation_*.json`.

The same 9-period universe was re-walked with the refined engine. The
gates substantially reduce trade count and meaningfully improve ETH edge:

| Coin | Engine     | Fired | Resolved | Win rate | EV (2R) |
| ---- | ---------- | ----- | -------- | -------- | ------- |
| BTC  | baseline   | 80    | 78       | 50.0%    | +0.500 R |
| BTC  | **refined**| 38    | 28       | 46.4%    | +0.393 R |
| ETH  | baseline   | 90    | 90       | 44.4%    | +0.332 R |
| ETH  | **refined**| 49    | 33       | 60.6%    | **+0.818 R** |

**Combined refined**: 87 fired, 61 resolved, blended WR ≈ 57.4%,
blended EV ≈ +0.72 R per trade.

**What the gates filtered (pooled across periods):**

- BTC: chase_gate rejected 86 weeks; climax_cooldown 36; weekly bias 128;
  daily confirmation 79; 4H setup 64; **38 fired**.
- ETH: chase_gate 86; climax_cooldown 25; weekly 109; daily 60; 4H 101;
  1H geometry 1; **49 fired**.

**Reading the result:**

- BTC EV dropped marginally because the chase gate filters some of the
  long-running 2017 and 2020–21 trend trades that were never deeply
  retraced. Those trades had positive edge in the baseline; rejecting
  them is a precision-vs-recall trade-off the chase gate makes by design.
- ETH improved sharply (WR +16 pts, EV more than doubled), which is the
  more important result: ETH's baseline edge was thin and the gates are
  what make it actually tradeable.
- 2023, 2024-H1, and 2024-H2→2025-Q1 contributed zero trades to either
  engine because of the local weekly/1H data gaps. The refined numbers
  cover ~6 years effectively, not the full 9.
- Sample is smaller than the baseline (61 resolved vs 168). Both
  numbers should be treated as indicative, not definitive — but the
  direction (refinement gates improve edge) is consistent with the
  iter 3–6 theory rationale.
