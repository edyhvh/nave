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
