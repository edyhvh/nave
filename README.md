# NAVE

NAVE is research infrastructure for collecting market data, evaluating
research hypotheses, resolving outcomes, and producing evidence for human
review. It is not an autonomous trading system.

## What NAVE does

- Acquires data from configured providers and records availability and quality.
- Normalizes provider responses into research-friendly contracts.
- Builds candidates and features for crypto, memecoin, equities, and options
  research.
- Evaluates experiments, resolves outcomes, and writes reproducible reports.
- Keeps operational decisions and any eventual action under human control.

## Research philosophy

NAVE is evidence-first and read-only. A candidate, observation, or hypothesis
is not a validated edge. Incomplete provider windows, unavailable hours,
partial event days, and provider errors remain explicit rather than being
silently filled or promoted to complete evidence. Historical experiments are
kept where they help reproduce or audit conclusions. Point-in-time eligibility
must respect whether data was available by the decision time.

## Current focus

The active research surface is memecoin/event analysis, including Stage-1
replication, Dune/PumpApi acquisition, and M3 outcome resolution. The broader
repository also contains shared research infrastructure and crypto, equities,
and options experiments. The canonical research state is currently paused
while notification reliability and state reconciliation are verified; recent
research has not validated a robust edge.

Large memecoin research artifacts are stored separately in the public
[NAVE memecoins dataset on Hugging Face](https://huggingface.co/datasets/jhonnyisaacc/memecoins).
The Git repository contains the code, contracts, tests, reports, and compact
evidence needed to understand and reproduce the research; the dataset contains
the larger PumpApi event archives and local memecoin research artifacts.

## How it works

```text
data acquisition
  → normalization and quality checks
  → point-in-time candidate eligibility
  → research/model evaluation
  → outcome resolution
  → evidence and report
  → human decision
```

Provider availability and completeness are part of the evidence. A missing or
unresolved observation is not treated as a successful or comparable result.

## Current status

- Operating mode: `READ_ONLY_RESEARCH_ONLY_HUMAN_GATED`.
- State: `PAUSED_NOTIFICATION_AND_STATE_RECONCILIATION`.
- No robust edge is currently validated.
- No autonomous orders, trades, wallet signing, swaps, or financial actions
  are enabled.
- Point-in-time helper contracts exist, but complete provider-wide enforcement
  and broader comparable historical coverage remain research milestones.

## Repository structure

- `trading/` — domain models and research logic.
- `research/nave/` — orchestration, state, contracts, and audits.
- `research/memecoin/` — memecoin acquisition and replay helpers.
- `research/dune/` — Dune queries and validation utilities.
- `backend/` — provider acquisition and normalization services.
- `cli/` — command-line entrypoints.
- `scripts/` — deterministic audits, replays, and experiment tooling.
- `tests/` — unit and integration tests.
- `docs/analysis/` — current and historical research evidence.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # fill only the provider credentials you need
```

The repository’s commands are intended to run with the project root on
`PYTHONPATH`:

```bash
PYTHONPATH=. .venv/bin/python cli/main.py --help
```

## Tests

Run the practical local suite from the repository root (excluding tests marked
`integration`, which may require live providers or testnet credentials):

```bash
PYTHONPATH=. .venv/bin/pytest -q -m 'not integration'
```

Tests should use deterministic fixtures unless an integration test explicitly
documents an external provider requirement.

## Running research

Inspect `research/nave/state.json` before running anything. Useful read-only
audits include:

```bash
PYTHONPATH=. .venv/bin/python scripts/nave_stage1_audit.py --help
PYTHONPATH=. .venv/bin/python scripts/nave_outcome_taxonomy_audit.py --help
```

Research commands may read configured provider data, but they do not authorize
or perform external financial actions. Do not enable scheduled continuation or
change the paused state as part of ordinary repository work.

## Safety / action boundary

NAVE does not autonomously trade. It does not submit orders, sign wallet
transactions, swap assets, or move funds. Research outputs are evidence for a
human decision-maker; any action remains outside the research pipeline and
requires explicit human control.

## Research documentation

- [Canonical research state](research/nave/state.json)
- [José Luis Cava daily video research contract](docs/analysis/jose_luis_cava_daily_research.md)
- [Memecoin research plan](docs/analysis/memecoin/plan.md)
- [Stage-1 survival report](docs/analysis/memecoin/nave-stage1-survival-day5-20260901.md)
- [Independent notification/state audit](docs/analysis/memecoin/nave-notification-stage1-independent-audit-20260902.md)
- [M3 statistical signal sanity](docs/analysis/memecoin/m3-statistical-signal-sanity-20260831.md)
- [M3 historical panel](docs/analysis/memecoin/m3-dune-historical-panel-20260831.md)
- [Command documentation](docs/commands/README.md)
- [Historical Hermes runbook](docs/hermes/nave-quant-runbook.md)
- [Raw research artifact policy](docs/analysis/raw/README.md)
