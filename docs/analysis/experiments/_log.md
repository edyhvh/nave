# Autonomous experiment log

Baseline: pooled +44.14R (BTC +20.79R / 77.8% WR, ETH +23.35R / 78.9% WR).
See `00_baseline.md` for the comparison rules every experiment must beat.

## Convention

- This table is the canonical record. Every experiment — shipped *or* skipped —
  gets a row.
- A standalone `NN_<name>.md` file is **only required for shipped (✅) experiments**
  and for the baseline. Skipped experiments (❌) live as a single row here.
- Skipped experiments still need their row to land on a branch that gets merged
  (e.g., the next shipped experiment, or a cleanup PR). Never lose a row just
  because the branch is discarded.
- The "Pooled R" column is the BTC+ETH (+ shipped extras) total from
  `scripts/theory_v2_backtest.py`. "Δ vs base" is relative to the iter-18
  baseline `+44.14R` until a new baseline is declared in `00_baseline.md`.

| # | Branch | Hypothesis | Pooled R | Δ vs base | Verdict | PR |
|---|---|---|---|---|---|---|
