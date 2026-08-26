# Experiment N5 — Volatility squeeze as 4th weekly bias source

**Type:** A/B experiment
**Date:** 2026-08-26
**Branch:** `experiment/n5-squeez-bias`
**Status:** ❌ REJECT — squeeze trades 0% WR (0W/7L), 100% FP, −7.00R

---

## 1. Hypothesis

H6: "Volatility squeeze como bias override para rangos de compresión"

When NAVE returns "no weekly bias" AND the asset is in a daily volatility
squeeze (BB width < p25 of 120d OR < 3.5% for ≥ 7 consecutive days), the
squeeze mode arms and the first breakout bar determines direction. Standard
downstream gates (daily confirm, climax cooldown, chase gate, 4H, 1H) apply.

**Pre-registered conditions** (from 13_n5_squeeze_discovery.md):
1. Squeeze detector: `bb_width_20d < p25_120d` OR `bb_width_20d < 3.5%` for ≥7d
2. Breakout: `close > max[-streak:0] + 0.5 * atr_14` (long), inverse for short
3. Daily confirm: existing NAVE logic
4. Downstream gates: unchanged

**Pre-registered acceptance gates:**
- Pooled R ≥ 27.69 (baseline)
- WR ≥ 85%
- FP ≤ 10%
- Captures BTC 63k→78k rally (OOS)

---

## 2. Implementation

### Files created/modified

| File | Change |
|------|--------|
| `trading/crypto/analysis/squeeze_detector.py` | **NEW** — `SqueezeConfig` + `detect_squeeze(daily, cfg)` → `(bias, diagnostic)` |
| `trading/crypto/theory_v2.py` | Added `squeeze_config` param to `TheoryV2Engine.__init__()`; 4th fallback in `evaluate()` after momentum/range_breakout |
| `scripts/n5_squeeze_ab.py` | **NEW** — A/B harness (control=squeeze OFF vs treatment=squeeze ON, 8 periods) |

### Architecture

The squeeze detector was inserted as the 4th weekly bias source in the
`TheoryV2Engine.evaluate()` cascade:

```
momentum_bias → range_breakout_bias → squeeze_bias → "no weekly bias"
```

When squeeze fires, it replaces the weekly bias (long/short) and the
standard downstream pipeline applies: COT filter → daily confirm →
climax cooldown → chase gate → 4H → 1H entry.

**Production default: OFF** (`squeeze_config=None`). No production
behavior changed.

---

## 3. Results

### Per-period comparison (treatment vs control)

| Period | BTC Δ | ETH Δ | Squeeze fired |
|--------|-------|-------|---------------|
| 2017-bull+2018-bear | −1.00R | 0.00R | 1 (BTC short, LOSS) |
| 2019-recovery | 0.00R | 0.00R | 0 |
| 2020-covid-crash | 0.00R | 0.00R | 0 |
| 2020-recovery+2021-ATH | 0.00R | 0.00R | 0 |
| 2022-bear | −2.00R | 0.00R | 2 BTC + 1 ETH |
| 2023-recovery | −1.00R | −1.00R | 1 BTC + 2 ETH |
| 2024-ETF-approval | 0.00R | 0.00R | 0 |
| 2024-2025-bull | −1.00R | −1.00R | 1 BTC + 1 ETH |

### Pooled results

| Metric | Control | Treatment | Δ |
|--------|---------|-----------|---|
| BTC R | +15.12 | +10.12 | −5.00 |
| ETH R | +11.57 | +9.57 | −2.00 |
| **Total R** | **+26.70** | **+19.70** | **−7.00** |
| BTC WR | 90.9% | 62.5% | −28.4pp |
| ETH WR | 88.9% | 72.7% | −16.2pp |
| Combined WR | 90.0% | 66.7% | −23.3pp |

### Squeeze-specific trades

| Period | Coin | Week | Direction | Entry | Outcome | R |
|--------|------|------|-----------|-------|---------|---|
| 2017-bull+2018-bear | BTC | 2018-02-05 | short | 8229.89 | LOSS | −1.0 |
| 2022-bear | BTC | 2022-03-28 | long | 46920.99 | LOSS | −1.0 |
| 2022-bear | BTC | 2022-07-25 | short | 22320.27 | LOSS | −1.0 |
| 2022-bear | ETH | 2022-08-22 | short | 1610.26 | unresolved | 0.0 |
| 2023-recovery | BTC | 2023-09-25 | short | 26248.17 | LOSS | −1.0 |
| 2023-recovery | ETH | 2023-09-11 | short | 1609.98 | unresolved | 0.0 |
| 2023-recovery | ETH | 2023-10-02 | long | 1724.38 | LOSS | −1.0 |
| 2024-2025-bull | BTC | 2024-10-21 | long | 69160.00 | LOSS | −1.0 |
| 2024-2025-bull | ETH | 2025-03-31 | short | 1786.42 | LOSS | −1.0 |

**0 correct, 7 incorrect, 2 unresolved = 100% FP rate on resolved trades.**

### OOS rally capture

**BTC 63k→78k rally (Aug 2026): NOT captured.** The squeeze detector
identified the compression, but the engine's weekly evaluation cadence
means the breakout bar (Aug 20, +13.3%) was evaluated on the following
Monday — by which point the move was already complete and the downstream
gates (chase gate, climax cooldown) rejected the now-extended entry.

---

## 4. Root cause analysis

### Why 100% FP?

The squeeze detector correctly identifies compression→expansion events
(94.4% precision in the discovery scan). However, the **backtest engine
evaluates weekly (Monday)**, not on the exact breakout day:

1. **Squeeze compresses** for 7-31 days (BB width < p25)
2. **Breakout bar** fires on day X (e.g., Wednesday +13%)
3. **Weekly evaluation** runs on Monday (day X+5)
4. By Monday, the move is **already complete**
5. The squeeze detector sees "squeeze ended + breakout confirmed"
6. But the **downstream gates reject** because:
   - **Climax cooldown**: the breakout bar itself IS a climax (>3× ATR)
   - **Chase gate**: price is at the impulse extreme (0% retracement)
   - **Daily confirm**: may or may not match (direction often reverses)

This is a **fundamental timing mismatch**: the squeeze signal is
intraday/event-driven, but the engine is weekly-cadence.

### Why the discovery scan showed 94.4% precision?

The discovery scan (`_n5_squeeze_v2.py`) measured whether a ≥5% move
occurred within 14 days of squeeze end — it did NOT require the move
to be tradeable via the weekly engine pipeline. The precision metric
measures *occurrence*, not *tradeability through NAVE's gates*.

### Structural issue

The squeeze detector is a **regime identifier** (compression → expansion),
not a **direction signal**. The discovery assumed "first breakout bar
determines direction," but:

- In 73.5% of historical squeezes, the expansion was **downward** (bear
  continuation), not a reversal
- The weekly evaluation catches the tail end, not the initiation
- The downstream gates (designed for pullback entries) are structurally
  incompatible with breakout entries

---

## 5. Acceptance gates

| Gate | Required | Actual | Pass? |
|------|----------|--------|-------|
| Pooled R ≥ 27.69 | ≥ 27.69 | +19.70 | ❌ FAIL |
| WR ≥ 85% | ≥ 85% | 66.7% | ❌ FAIL |
| Squeeze FP ≤ 10% | ≤ 10% | 100.0% | ❌ FAIL |
| Captures 63k→78k rally | yes | no | ❌ FAIL |

**Verdict: REJECT** — all 4 gates failed. The squeeze bias degrades
the baseline by −7.00R and generates exclusively losing trades.

---

## 6. What would make this viable?

The squeeze concept has genuine signal (94.4% historical precision for
occurrence). The failure is architectural, not statistical:

1. **Daily-cadence engine**: if NAVE evaluated daily instead of weekly,
   the squeeze breakout could be caught on the actual breakout bar
   (before the climax/chase gates reject it)

2. **Breakout-specific gates**: the current downstream gates are designed
   for pullback entries (chase gate requires 50-95% retracement). A
   squeeze breakout needs momentum-following gates, not pullback gates.

3. **Intraday trigger**: the 13.3% Aug 20 bar happened in hours. A
   4H or 1H cadence engine could catch it; a weekly engine cannot.

4. **Direction filter**: 73.5% of historical squeezes broke downward.
   A filter for squeeze depth (BB < 3% = higher probability of
   directional follow-through) or regime context (post-crash vs
   mid-trend) could improve direction accuracy.

None of these are within the scope of the current N5 experiment
(weekly-cadence engine with standard downstream gates).

---

## 7. Artifacts

- `trading/crypto/analysis/squeeze_detector.py` — squeeze detector module (kept for reference; not wired to production)
- `scripts/n5_squeeze_ab.py` — A/B harness
- `docs/analysis/raw/n5_squeeze_ab_20260826T194453Z.json` — full results JSON
- Branch: `experiment/n5-squeez-bias` (will be merged with REJECT documentation)

---

## 8. Verdict

**REJECT.** The volatility squeeze detector identifies real compression
events (94.4% historical precision), but the weekly-cadence engine with
pullback-oriented downstream gates cannot trade them profitably. The
timing mismatch between event-driven breakouts and weekly evaluation
produces 100% FP (0W/7L, −7.00R). The concept requires a fundamentally
different engine architecture (daily/intraday cadence + momentum-following
gates) that is out of scope for the current theory_v2 pipeline.
