# Raw backtest artifacts

JSON output from `scripts/theory_v2_backtest.py` and `scripts/theory_backtest.py`.

## Commit policy

Only commit a file here when it is **referenced from a doc** (e.g.,
`docs/analysis/iterations/iter_N.md`, `docs/analysis/experiments/00_baseline.md`,
or a per-experiment `NN_*.md`). Exploration runs that informed but did not
land an iteration / experiment should stay local.

Rule of thumb: if no `.md` file links to it, it doesn't belong here.

Existing files predating this policy are kept for history; the rule applies
to *new* runs going forward.
