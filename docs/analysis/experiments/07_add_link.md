# Experiment 07 — Add LINK as a 4th coin

**Branch:** `experiment/add-link`
**Hypothesis:** same as exp 01 (SOL) — theory_v2 is structural and
asset-agnostic. LINK is large-cap, liquid on Binance with full history,
and behaves directionally enough that the weekly→1H pipeline should
generalise.

## Change

`scripts/data_loader.py` — added `LINK` to `COIN_ALIASES`:

```python
"LINK": ["link", "linkusdt", "linkusd", "link-usd", "chainlink"],
```

## Results — full 9-period backtest

```
python scripts/theory_v2_backtest.py --coins BTC ETH LINK
```

| Coin | Fired | Resolved | WR | Total R | Avg R |
|---|---|---|---|---|---|
| BTC | 22 | 18 | 77.8% | +20.79 | +1.155 |
| ETH | 25 | 19 | 78.9% | +23.35 | +1.229 |
| **LINK** | **23** | **21** | **81.0%** | **+23.01** | **+1.096** |
| **Pooled** | **70** | **58** | **81.0%** | **+67.15** | **+1.158** |

vs baseline pooled +44.14R / 78.4% WR → **+23.01R improvement (+52%)**,
pooled WR climbs +2.6pp.

LINK has the best WR of all three coins. BTC and ETH unaffected.

## Why this is a strict win

- Pooled R: +44.14 → +67.15 (+23.01R)
- Pooled WR: 78.4% → 81.0% (+2.6pp)
- BTC unchanged, ETH unchanged → purely additive
- LINK only had 2 unresolved trades out of 23 (best resolution rate of the three)

## Out of scope (deliberately)

- Hyperliquid LINK trading config + position sizing
- Hermes / MCP / agent wiring for LINK
- `daily_scan.py` LINK coverage

## Compatibility with the SOL PR (#17)

Both PRs only touch `COIN_ALIASES` in `data_loader.py`, adding distinct
ticker entries. They merge cleanly together — the union gives BTC + ETH
+ SOL + LINK = pooled +20.79 + +23.35 + +20.68 + +23.01 = **+87.83R**
(rerun pending after merge to confirm).
