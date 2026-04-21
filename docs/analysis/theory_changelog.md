# Theory Changelog — Phase 1

> **Date:** 2026-04-08
> **Source:** Full read of `docs/elcriptopanavideos.md` (19,203 lines, 15 videos)
> **Scope:** `docs/technical.yaml`, `docs/cot_integration.yaml`, `docs/terms.yaml`
> **Branch:** `feat/theory_refinement`

This document records every change made to the theory YAML files during Phase 1,
with rationale linked to specific transcript content. Each commit in the
`feat/theory_refinement` branch references back to this file.

---

## Summary of changes

| File | Lines before | Lines after | Net change |
| --- | --- | --- | --- |
| `docs/technical.yaml` | 631 | ~960 | +329 (all additions, no deletions) |
| `docs/cot_integration.yaml` | 34 | ~175 | +141 (full rewrite) |
| `docs/terms.yaml` | 370 | ~560 | +190 (additions only) |
| `docs/analysis/contradictions.md` | (new) | ~230 | new file |
| `docs/analysis/theory_changelog.md` | (new) | this file | new file |

No existing theory content was deleted. All changes are additive or refinements
of wording, so the original framing remains recoverable from git history.

---

## `docs/technical.yaml`

All new sections are appended to the end of the existing file under the
philosophy tree. Rationale for each:

### New: `top_down_timeframe_execution`
Codifies the weekly → daily → 4H → 1H pipeline explicitly. This was implied in
the existing theory but never written as an execution contract. The transcripts
repeatedly emphasize that "a pattern valid on 4H is not automatically valid on
1H" (market makers video, ~minute 55). Each timeframe now has a declared role,
required inputs, and expected output.

**Why it matters:** Phase 2 backtests need an explicit contract to walk the
weekly → 1H pipeline. Without this section the backtest engine has to infer the
pipeline from scattered rules.

### New: `entry_triggers_4h`
Four concrete 4H setup patterns, each with a named trigger and an invalidation
rule:
- `block_rejection_plus_bos`
- `pfq_fractalico`
- `retroceso_75_setup`
- `flip_plus_ben`

**Source:** The "Trading Institucional II" video (around minute 35) walks
through a 4H block rejection + BOS setup step by step. The "Cómo hacen trading
los market makers" video discusses PFQ fractálico and flip+BEN patterns.

### New: `entry_triggers_1h`
Three 1H execution patterns, each requiring a pre-existing 4H setup:
- `flip_confirmation`
- `zc2_sweep_reversal`
- `micro_pfq_on_institutional`

Plus a `discipline` section forbidding 1H entries without a 4H setup.

**Source:** The "Trading Institucional II" video's discussion of 1H execution
inside an established 4H setup (the EUR/CAD example, ~minute 40). Also the
"Cómo colocar una buena posición" coaching session.

### New: `stop_loss_placement_rules`
Explicit SL placement rules per timeframe, plus a list of anti-patterns.

**Source:** Multiple transcripts. The clearest statement is in the "¿Cómo hacer
trading y colocar una posición con análisis fundamental?" video (~minute 18):
> "El Stop no es para confirmarme a mí que yo estaba equivocado — el Stop es
> para que la Gráfica me diga Estás completa y absolutamente equivocado."

This is codified as "SL must prove the premise wrong, not just pop you out".

The existing `stop_loss` field in `risk_management` is preserved. The new
section adds timeframe-specific placement guidance that the old field lacked.

### New: `retracement_entry_zones`
Replaces the single-value "75% retracement" idea with a band:
- 50% = alert only, never entry
- 75% = minimum entry
- 86% = optimal (institutional withdrawal level per BIS)
- 90%+ = deep entry for wide-spread venues

**Source:** Multiple COT/institutional videos. The 86% figure is the explicit
BIS interbank flow study cited in the "Trading Institucional I" video
(~minute 28). The "50% is NOT an entry" is emphasized repeatedly —
"cualquier posición al 50% es una trampa retailer".

**Resolves contradiction:** See `contradictions.md` §3.

### New: `confluence_zones` (ZC1/ZC2)
The existing `confluence_zones` definition under `imbalances` is short. This
new top-level section adds:
- Required factors (at least 3 of 7).
- Explicit ZC1 vs ZC2 distinction.
- Profit-taking behavior on touch (80% at ZC1, 10% at ZC2, trail 10%).

**Source:** The "Cómo hacer trading con análisis fundamental" video explicitly
walks through ZC1 and ZC2 at minute 19 with the NZD/USD position example.

### New: `ben_block_between_levels`
Defines BEN (Bloque Entre Niveles) as the primary construction for turning
fuzzy S/R into a usable entry zone. Provides step-by-step construction and
usage rules.

**Source:** The "Cómo hacer trading con análisis fundamental" video
(~minute 13) introduces BEN explicitly as the zone between a true swing and
the nearest institutional level.

### New: `candle_shape_to_phase`
A quick visual mapping from candle body/wick shape to market phase:
- small body + long wick → volatility / regression / consolidation
- large body + short wick → momentum / expansion
- equal body + equal wick → transition

**Source:** The "Volatilidad y momento" video (~minute 26): "en volatilidad las
velas más veces de las que no tienen cuerpos pequeños y mechas largas; en
momentum tienes velas con cuerpos largos y mechas cortas".

### New: `spread_range_as_market`
Codifies the insight that the bid/ask spread is literally the market, and
defines the spread range as a new setup-validity layer.

**Source:** Market makers video — the entire discussion of "the market is a
thing you sell, a bid price, and an ask price" (~minute 26 onward).

### New: `interbank_reality`
Clarifies that IPDA / ebitda is an EXPLANATORY model, not a literal unified
algorithm. Includes the 86/14 institutional/retail ratio from the BIS study,
with an explicit caveat that this ratio is forex-derived and weaker for
crypto.

**Source:** "Trading Institucional II" video, ~minute 1:25 — Pana explicitly
says "no existe tal cosa como IPDA". Also the "Cómo hacen trading los market
makers" video.

**Resolves contradiction:** See `contradictions.md` §1 and §8.

### New: `pro_trader_mindset`
Encodes the difference between pro trader and retailer mindsets: fixed % return
target, client-focus, 80/20 fundamental/technical split, theta awareness, etc.

**Source:** "Cómo te engañan las academias" video, ~minute 14-15 (discussion of
FINRA Series 57 and the pro trader definition).

### New: `market_phase_discipline`
Explicit statement of the "post-volatility, pre-momentum" positioning doctrine
and the rules that follow from it.

**Source:** This is core nave philosophy present throughout the transcripts,
but was never stated as a bulleted discipline with anti-patterns. Now it is.

### New: `semantics_note`
Short note documenting the "price moves, market does not" distinction. Marks
diagonal trendlines as "visual context only, never a standalone signal".

**Source:** Market makers video (the long discussion about price-vs-market-vs-
chart). Also resolves `contradictions.md` §5.

### Existing sections preserved unchanged
Every section present before Phase 1 is unchanged. This includes the existing
`75_percent_retracement_entry`, `confluence_zones` under `imbalances`,
`mitigation_blocks_deep_dive`, the full `psychology` list, `risk_management`,
`strategy`, `ranges`, `stock_market_dance`, `process_oriented_system_sop`,
`fits_framework`, `institutional_narrative`, `price_as_stochastic_system`,
`volatility_deep_dive`, `new_sr_theory_expanded`, `trading_psychology_expanded`,
and so on.

If future iterations want to deprecate the old single-value `75_percent_retracement_entry`
in favor of the new `retracement_entry_zones` band, they can do so in a later
commit — Phase 1 keeps both to preserve history.

---

## `docs/cot_integration.yaml`

This file was significantly reworked. The 2019-era file treated COT as "the
weekly driver"; the transcripts (COT video, ~1h47m of careful argument) make
clear that COT is a *reference*, not a *driver*.

### Changes
- **Renamed** `cot_as_weekly_driver` → `cot_as_weekly_reference`.
- **Added** `what_cot_actually_is` and `what_cot_is_not` sections to codify
  the boundaries.
- **Added** `how_to_use_cot` with three distinct use cases: trend confirmation,
  reversal warning, model transition.
- **Added** `weekly_decision_order` with explicit precedence:
  rates → monetary mass → macro data → COT → price structure.
  COT is fourth, not first.
- **Added** `how_weekly_bias_filters_to_4h_and_1h` — the top-down pipeline
  from weekly COT all the way to 1H triggers, with explicit NEUTRAL handling
  at every layer.
- **Added** `contrarian_usage` with strict guardrails (half position size,
  macro must still agree).
- **Added** `eth_cot_caveat` acknowledging that ETH COT is weaker than BTC COT
  and may not be worth using at all in Phase 2 backtests.
- **Sharpened** the "commercials move the market" note — the old phrasing was
  misleading. Commercials are *defensive hedgers*, not directional drivers.
- **Kept** the existing `usage`, `alignment_with`, and `notes` sections but
  updated to reference the new structure.

**Source:** The entire COT video (lines 7648–9733 of the transcript file).
The most important quotes are in `contradictions.md` §4.

**Resolves contradictions:** §4, §10, §12 in `contradictions.md`.

---

## `docs/terms.yaml`

Pure additions, no deletions. New terms organized into seven thematic blocks:

### Block 1: Execution and timeframe terms
`Temporalidad mayor`, `Temporalidad menor`, `Top-down`, `Gatillo de entrada`,
`Zona de entrada`, `Cacería de liquidez`, `PFQ fractálico`, `BOS`, `CHoCH`,
`BEN`, `Primera Zona de Confluencia`, `Segunda Zona de Confluencia`, `Flip`,
`Niveles institucionales`.

These close the gap on 4H/1H execution vocabulary — most of these terms appear
throughout the transcripts but were absent from the glossary.

### Block 2: Retracement and phase terms
`Retroceso al 50%`, `75%`, `86%`, `90%`, `Post-momentum`.

Each retracement level has an explicit use-case in its definition so the term
carries its own semantics.

### Block 3: Market structure and order flow
`Libro de órdenes`, `Buy stops`, `Sell stops`, `Buy limits`, `Sell limits`,
`Horquilla`, `Precio bid`, `Precio ask`, `Liquidity provider`, `Aggregator`,
`Dealer`, `Interdealer`, `Cámara de compensación`, `Offset risk`.

Captures the interbank plumbing that the transcripts spend three videos
explaining.

### Block 4: COT and sentiment
`Comerciales`, `No comerciales`, `Reportable`, `Línea cero`.

The `Comerciales` definition explicitly states "defensive, hedgers, operate
against the trend at extremes, provide liquidity" — this corrects the
misreading that commercials drive direction.

### Block 5: Derivatives and instruments
`Contrato futuro`, `Forward`, `Swap`, `CFD`, `Opción financiera`, `Prima`,
`Margen`, `Garantía`, `Apalancamiento`, `Vencimiento`, `Rollover`,
`Subyacente`, `Tamaño del contrato`, `Tick value`, `Costo del carry`,
`Carry trade`, `Precio spot`, `Paridad futuro-spot`, `Contango`, `Backwardation`.

Sets up the vocabulary needed for Phase 2 `trading/execution.py` refactor,
which the transcripts strongly suggest should use futures/perps instead of
spot.

### Block 6: Greeks and risk metrics
`Delta`, `Gamma`, `Theta`, `Vega`, `Alfa`, `Beta`.

Enables discussion of options-based hedging strategies that the transcripts
reference.

### Block 7: Player types
`Hedger`, `Especulador`, `Arbitrador`, `Pro trader`, `Retailer`, `Cliente
premium`, `SIFI`.

### Block 8: Frameworks, algorithms, studies
`Money market`, `Price discovery`, `Interbank market`, `Ebitda / IPDA algorithm`
(with the "EXPLANATORY MODEL, NOT a literal algorithm" caveat baked into the
definition), `Machine engine`, `Aceleración de cash flow`, `Re-pricing`,
`Liquidación a dólar`, `Hoja de balance`, `Risk-on / Risk-off`, `Low volatility
low beta`.

### Block 9: Psychology and discipline
`Francotirador`, `Curva de aprendizaje`, `Plan de contingencia`, `Ejecución
impoluta`, `Consistencia`.

### Block 10: Metaphors
`Ballena`, `Ninfa del bosque`, `Cazador`, `Caminito de hormigas` (already
existed, re-referenced), `Pastilla roja`.

These are the Pana's recurring metaphors — they show up in the transcripts
often enough that codifying them helps future readers decode shorthand.

---

## What was deliberately NOT added

These points came up in the transcripts but were **not** added to the YAML
files in Phase 1, either because they are outside the Phase 1 scope or because
they require a decision the user must make:

1. **Futures-only execution model** — The transcripts strongly argue that
   professional trading uses futures/perps for hedging, not spot. Phase 1
   cannot modify `trading/`, so this is deferred to Phase 2. Flagged in
   `contradictions.md` §7.

2. **Options greeks as a first-class strategy** — The Greeks are in the
   glossary now but no strategy uses them. Deferred to Phase 2 / Phase 3.

3. **Specific broker integrations** — The transcripts discuss BitMEX, Deribit,
   ByBit, FTX (defunct), CME, etc. The nave project uses Hyperliquid and the
   theory should not be tied to a specific venue.

4. **The "five stages of trading" emotional progression** (lose a lot → lose a
   little → break even → win a little → win a lot) — not actionable as YAML.

5. **Reading list** — transcripts recommend the BIS 1996 paper, Nassim Taleb,
   and the Oxford Interbank Market Purpose paper. Not added as YAML but noted
   in `contradictions.md` open questions.

6. **Discussion of the Pana's personal work history** — transcripts include
   autobiographical detail about the Pana's work in FX arbitrage. Not relevant
   to the theory.

---

## Cross-references

- **Contradictions log:** `docs/analysis/contradictions.md`
- **Transcripts source:** `docs/elcriptopanavideos.md`
- **Phase workflow:** `AGENTS.md`
- **Phase 2 kick-off:** after this Phase 1 is committed and approved, the user
  will trigger the iteration loop for the 9 historical periods.

---

## Phase 1 → Phase 2 handoff notes

For whoever picks up Phase 2:

1. The new `top_down_timeframe_execution` section is the execution contract
   the backtest engine should implement. `scripts/theory_backtest.py`
   already stubs out weekly/daily/4H/1H loading; Phase 2 needs to make the
   stub logic actually match this contract.

2. `retracement_entry_zones` is a **zone**, not a point. The backtest engine's
   current heuristic in `_one_h_entry` uses a fixed 2R target; that should be
   replaced with ZC1/ZC2 targeting.

3. `weekly_decision_order` in `cot_integration.yaml` implies the Phase 2
   engine should rank inputs in priority order and NEUTRAL out when high-
   priority inputs disagree with lower-priority ones. The current macro
   loading in `theory_backtest.py` treats all inputs symmetrically.

4. The `interbank_reality` section's warning that "there is no single
   algorithm" should inform how the Phase 2 engine models institutional
   behavior — it should simulate **uncoordinated but correlated** reactions,
   not a single unified algo.

5. The ETH COT caveat is important — if Phase 2 backtests show ETH COT
   underperforming, remove it entirely rather than patching it.
