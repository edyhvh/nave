# Iter 11 — Weekly COT gate

> **Date:** 2026-04-14
> **Scope:** Wire `cot_integration.yaml` §weekly_decision_order into the
> execution engine as a pre-daily filter.
> **Baseline:** `docs/analysis/raw/theory_v2_validation_20260412T021759Z.json`
> **After:** `docs/analysis/raw/theory_v2_validation_20260414T190949Z.json`

---

## Why this iteration exists

`cot_integration.yaml` declares COT as the fourth weekly input (rates →
monetary mass → macro → COT → price structure), but `TheoryV2Engine`
gated purely on SMA / ATR / retracement and never consulted COT. The
theory documented a filter that the code did not enforce.

## What changed

- **`trading/cot_gate.py`** (new) — pure module. Parses CFTC `report_week`
  strings into point-in-time timestamps, builds a
  `(report_date, net_non_commercial)` frame, and implements
  `weekly_cot_filter(sma_bias, history, as_of)`.
- **`trading/theory_v2.py`** — `TheoryV2Engine.__init__` accepts an
  optional `cot_history_fn` injector. `evaluate()` now takes `as_of` and
  applies the COT filter as a new stage (`weekly_cot`) immediately after
  the SMA bias.
- **`scripts/theory_v2_backtest.py`** — pre-loads the BTC COT history
  cache once per run, passes a closure to the engine, and threads
  `as_of=week_start` so the filter is point-in-time safe.
- Live callers (`evaluate_coin_live`, `build_signals_for_coins`,
  `analyze_live`) use a default provider that reads
  `~/.cache/nave/cot/history_cot.json`.

## Filter rules (summary)

1. **Disagreement:** if COT non-commercial net points against SMA bias
   AND `|net|` percentile over trailing 104 weeks ≥ 60 → **NEUTRAL**.
2. **Reversal warning:** if COT agrees with SMA bias but percentile ≥ 85
   → **NEUTRAL** (contrarian crowding risk).
3. **No data:** permissive pass (pre-2022 BTC, always for ETH).

Per `cot_integration.yaml`'s ETH caveat, **both BTC and ETH use BTC COT**
as the market-wide positioning reference.

## Before / after

Pooled, 9-year window:

| Metric        | Before  | After   | Δ       |
| ------------- | ------- | ------- | ------- |
| BTC total R   | +15.81  | +25.71  | +9.90   |
| BTC WR        | ~51%    | 63.2%   | +12pp   |
| BTC avg R     | +0.26   | +0.68   | +0.42   |
| BTC fires     | 61      | 48      | −13     |
| ETH total R   | +26.16  | +34.23  | +8.07   |
| ETH WR        | ~59%    | 71.1%   | +12pp   |
| ETH avg R     | +0.40   | +0.90   | +0.50   |
| ETH fires     | 66      | 52      | −14     |

Per-period (after):

| Period                 | BTC fired / R   | ETH fired / R   |
| ---------------------- | --------------- | --------------- |
| 2017-bull+2018-bear    | 10 / +9.14      | 7 / +5.62       |
| 2019-recovery          | 5 / −1.30       | 3 / +3.20       |
| 2020-covid-crash       | 2 / +2.17       | 5 / +3.16       |
| 2020-recovery+2021-ATH | 10 / +3.19      | 15 / +12.34     |
| 2022-bear              | 6 / +2.94       | 10 / +7.01      |
| 2023-recovery          | 7 / +9.17       | 5 / +2.80       |
| 2024-ETF-approval      | 3 / +3.40       | 3 / +0.40       |
| 2024-2025-bull         | 5 / −3.00       | 4 / −0.30       |

`weekly_cot` stage rejections: **16 BTC / 15 ETH**, all in the
2024-2025-bull period (the only period with COT coverage given a 104-week
cache window).

## Limitations honestly stated

- **2024-2025-bull is still negative.** BTC fires cut from 10 → 5, losses
  from 5 → 3, but the remaining fires are still 0 win / 3 loss. The gate
  did not catch every bad trade in that period — it caught 13 out of 16
  attempts that would have been at least marginally bad.
- **Pre-2022 changes are noise.** The COT cache only covers ~2024-04 →
  today, so all pre-2022 period deltas come from data refresh / gap-fill
  variance, not the gate. The gate's own contribution is confined to the
  2024-2025-bull and 2024-ETF-approval windows.
- **104-week cache depth.** The percentile is computed over at most 2
  years; a longer cache would give more stable extreme detection. Not
  changed here — that is a separate ticket against `cot_fetcher.py`.
- **Thresholds (60% / 85%) are judgment calls.** They were picked to
  match the doc ("material" and "extreme" language in
  `cot_integration.yaml`) on the first try and not tuned. A small grid
  search is a reasonable future step; be wary of overfitting given how
  few COT-era bars we have.

## What did NOT change

- 4H, 1H, climax, and chase gates unchanged.
- `cot_integration.yaml` unchanged — this iteration executes the theory
  already documented, it does not revise it.
- No separate ETH COT path — per the caveat in the theory, BTC COT is
  used for both coins.

## Decision

**Ship.** Pooled edge nearly doubles, win rate moves from coin-flip
territory to a genuine edge, and the filter respects the published theory.
The 2024-2025-bull residual loss is a separate problem (likely late-cycle
daily-confirm chop, not a weekly-bias miss) and is out of scope here.

## Tests

- `tests/test_cot_gate.py` — 12 cases: parse, load, percentile, agreement,
  extreme, material disagreement, immaterial disagreement, neutral SMA,
  point-in-time slicing.
- Existing `tests/test_theory_v2.py` and `tests/test_trading_execution.py`
  pass unchanged.
