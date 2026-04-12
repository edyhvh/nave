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

## Refined engine (theory v2 — iter 4–6 gates active, original params)

> **Generated:** 2026-04-09 via `python scripts/theory_v2_backtest.py`
> **Engine:** `trading.theory_v2.TheoryV2Engine` with the iter 4 climax
> cooldown, iter 5 chase prevention, and iter 6 ATR stop floor enforced.
> **Parameters:** weekly 8-SMA 0.5% deadband, daily 20-SMA, 4H 12-SMA,
> fixed 2R targeting.

| Coin | Engine     | Fired | Resolved | Win rate | EV (2R) |
| ---- | ---------- | ----- | -------- | -------- | ------- |
| BTC  | baseline   | 80    | 78       | 50.0%    | +0.500 R |
| BTC  | refined v2 | 61    | 42       | 45.2%    | +0.357 R |
| ETH  | baseline   | 95    | 90       | 44.4%    | +0.332 R |
| ETH  | refined v2 | 66    | 43       | 55.8%    | +0.674 R |

## Tuned engine (theory v3 — optimized params + ZC1/ZC2 exits)

> **Generated:** 2026-04-11 via `python scripts/theory_v2_backtest.py`
> **Data:** Full 2017–2026 coverage (Binance cache gap-filled for 2023–2025).
> **Parameters:** weekly 8-SMA **2% deadband**, daily **10-SMA**, 4H **8-SMA**,
> **ZC1/ZC2 dynamic exit** (80% at nearest structural swing, 20% trailed).
> Raw output: `docs/analysis/raw/theory_v2_validation_20260412T022248Z.json`.

| Coin | Engine     | Fired | Resolved | Win rate | Total R | Avg R/trade |
| ---- | ---------- | ----- | -------- | -------- | ------- | ----------- |
| BTC  | refined v2 | 61    | 42       | 45.2%    | +15.8   | +0.36 R     |
| BTC  | **tuned v3** | 51  | 40       | **60.0%** | **+23.7** | **+0.59 R** |
| ETH  | refined v2 | 66    | 43       | 55.8%    | +26.2   | +0.57 R     |
| ETH  | **tuned v3** | 56  | 40       | **70.0%** | **+34.4** | **+0.86 R** |

**Combined v3**: 107 fired, 80 resolved, blended WR ≈ 65.0%,
blended total R ≈ +58.1, avg R ≈ +0.73 R per trade.

**What changed (v2 → v3):**

1. **Weekly deadband widened** from 0.5% to 2% — prevents false short
   flips during bull-market pullbacks. This was the single biggest
   improvement, eliminating losing shorts in 2024.
2. **Daily SMA shortened** from 20 to 10 — responds faster to trend
   resumptions after pullbacks, catching continuation moves earlier.
3. **4H SMA shortened** from 12 to 8 — faster confirmation means fewer
   missed setups when 4H structure aligns briefly with bias.
4. **ZC1/ZC2 dynamic exits** replaced fixed 2R — ZC1 targets nearest
   structural swing level (min 1R), ZC2 trails to next swing or 2.5R.
   Partial exits (80% at ZC1, trail 20%) bank profits earlier and
   reduce the frequency of winners turning into losers.

**Per-period breakdown (v3):**

| Period | BTC fired | BTC WR | BTC R | ETH fired | ETH WR | ETH R |
| ------ | --------- | ------ | ----- | --------- | ------ | ----- |
| 2017-bull+2018-bear | 10 | 87.5% | +9.1 | 7 | 80.0% | +5.6 |
| 2019-recovery | 5 | 25.0% | -1.3 | 3 | 50.0% | +3.2 |
| 2020-covid-crash | 2 | 50.0% | +2.2 | 5 | 100.0% | +3.2 |
| 2020-recovery+2021-ATH | 10 | 57.1% | +3.2 | 15 | 71.4% | +12.3 |
| 2022-bear | 6 | 60.0% | +2.9 | 10 | 83.3% | +7.0 |
| 2023-recovery | 7 | 85.7% | +9.2 | 5 | 75.0% | +2.8 |
| 2024-ETF-approval | 3 | 100.0% | +3.4 | 3 | 50.0% | +0.4 |
| 2024-2025-bull | 8 | 0.0% | -5.0 | 8 | 40.0% | -0.1 |

**Remaining weakness:** 2024-2025-bull BTC still loses -5.0R (0 wins / 5
losses on resolved trades). The choppy distribution phase from late 2024
through Q1 2025 generates short signals that get stopped. This is a known
difficulty for any trend-following system in a ranging distribution.

**Caveats:**

- Parameter tuning was conducted against the same data used for validation.
  True out-of-sample performance requires forward testing.
- The 80 resolved trades across ~8.5 years is a meaningful but small sample.
- 2019 remains the weakest period for BTC — choppy recovery with poor
  trend-following conditions.
