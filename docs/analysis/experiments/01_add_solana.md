# Experiment 01 — Add SOL as a third coin

**Branch:** `experiment/add-solana`
**Hypothesis:** the theory_v2 pipeline is asset-agnostic — pure structural
gates with BTC COT as a market-wide positioning proxy. Adding a high-beta
liquid coin (SOL) should produce additional R without disturbing BTC/ETH.

## Change

`scripts/data_loader.py` — added `SOL` to `COIN_ALIASES`:

```python
"SOL": ["sol", "solusdt", "solusd", "sol-usd", "solana"],
```

That's it. The data_loader gap-fills SOL OHLCV from Binance on first run
and caches under `data/binance_cache/SOL_*.parquet`. The TheoryV2Engine
needs no SOL-specific tuning; the 1H pipeline already supplies BTC COT
history for any non-BTC coin via the live cot provider, matching how ETH
already works.

## Results — full 9-period backtest

```
python scripts/theory_v2_backtest.py --coins BTC ETH SOL
```

| Coin | Fired | Resolved | WR | Total R | Avg R |
|---|---|---|---|---|---|
| BTC | 22 | 18 | 77.8% | +20.79 | +1.155 |
| ETH | 25 | 19 | 78.9% | +23.35 | +1.229 |
| **SOL** | **26** | **20** | **80.0%** | **+20.68** | **+1.034** |
| **Pooled** | **73** | **57** | **78.9%** | **+64.82** | **+1.137** |

vs baseline pooled +44.14R → **+20.68R improvement (+46.9%)**.

### SOL period breakdown

| Period | Fires | Win | Loss | Unr | Total R |
|---|---|---|---|---|---|
| 2017-bull+2018-bear | — | — | — | — | SKIPPED (no SOL data) |
| 2019-recovery | — | — | — | — | SKIPPED |
| 2020-covid-crash | — | — | — | — | SKIPPED (SOL launched Mar 2020, gaps) |
| 2020-recovery+2021-ATH | 11 | 8 | 2 | 1 | **+10.13** |
| 2022-bear | 5 | 1 | 0 | 4 | +1.87 |
| 2023-recovery | 6 | 6 | 0 | 0 | **+8.97** |
| 2024-ETF-approval | 2 | 0 | 1 | 1 | -1.00 |
| 2024-2025-bull | 2 | 1 | 1 | 0 | +0.71 |

The 2024-ETF window (Jan–Jun 2024) is the only negative — only 2 fires,
1 stopped out. Acceptable noise, no systematic regression.

### BTC and ETH unaffected

Identical fire counts, win counts, and total R as the iter 18 baseline.
This change is purely additive.

## Verdict

**SHIP.** Strict improvement: +20.68R pooled, no regression on BTC/ETH,
SOL has the highest WR of all three. Draft PR opened.

## Out of scope (deliberately)

- Agent / MCP / live wiring for SOL (Hermes still loads BTC+ETH only).
  This PR only enables SOL in the backtest harness.
- Hyperliquid SOL trading config + position sizing.
- `daily_scan.py` SOL coverage.

These are follow-ups once the user reviews this PR.
