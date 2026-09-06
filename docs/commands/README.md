# Nave Commands Reference

This directory documents command-line usage for the entire project.

Run all commands from the repository root unless stated otherwise.

## 1) Environment Setup

```bash
python setup.py
```

What setup now automates:

- Creates `.venv`
- Installs dependencies
- Installs a `nave` shim at `.venv/bin/nave`
- Adds `.venv/bin` to your shell rc (`~/.zshrc` or `~/.bashrc`)

After setup, reload shell config once:

```bash
source ~/.zshrc
# or
source ~/.bashrc
```

Manual setup:

```bash
mise install python@3.12
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Useful environment helpers:

```bash
source .venv/bin/activate
./scripts/dev_shell.sh
./scripts/dev_shell.sh python --version
./scripts/dev_shell.sh pytest -q
```

Read-only stock-short research:

```bash
nave stocks short scan --input-file snapshots.json --json
```

The scanner requires multiple non-macro factors, retains rejected candidates,
and emits research results only. Quant job migration declarations are kept in
`ops/quant_nave_jobs.json` with `PREPARE_ONLY` and disabled by default.

## 2) Unified CLI (`nave`)

If `nave` is not available in your shell, use:

```bash
PYTHONPATH=. python cli/main.py --help
```

Troubleshooting sequence:

```bash
python setup.py
source ~/.zshrc   # or source ~/.bashrc
which nave
nave --help
```

Main help/version (research examples require the corresponding PRs #42–#49 in the served checkout):

```bash
nave --help
nave version

# NAVE-owned structured intelligence
nave intel cava daily --json
nave intel context latest --json

# Human-gated portfolio research
nave portfolio review --json
nave portfolio candidates --ism-file ism.json --json
nave portfolio ism --ism-file ism.json --json
nave portfolio watch --watch-file watches.json --prices-file prices.json --json

# Normalized public financial disclosures
nave disclosures sync --congress-file congress.json --executive-file executive.json --json

# Point-in-time memecoin research (local/cached input)
nave memecoin discover --input-file snapshot.json --json
nave memecoin evaluate --outcomes-file outcomes.json --json
nave memecoin missed-moves --outcomes-file outcomes.json --json
nave memecoin backtest --discover-file discovery.json --outcomes-file outcomes.json --json
nave memecoin status --json
```

Data commands:

```bash
nave data fetch all
nave data fetch aaii
nave data fetch onchain
nave data fetch onchain_btc
nave data fetch rrp
nave data fetch tga
```

Trading commands:

```bash
nave trading run-strategy --wallet hermes --dry-run
nave trading run-strategy --wallet hermes --coins "BTC ETH" --dry-run
nave trading run-strategy --wallet hermes --mainnet

nave trading run --strategy cot-weekly --paper --capital 2000
nave trading run --strategy cot-weekly --backtest --capital 2000
nave trading run --strategy cot-weekly --backtest --learn --capital 2000
nave trading run --strategy cot-weekly --paper --live --wallet hermes --capital 2000
```

API and MCP:

```bash
nave api start --host 127.0.0.1 --port 8000 --reload
nave mcp run
```

COT commands:

```bash
nave cot analyze --coins "BTC ETH"
nave cot report
nave cot report --coins "BTC ETH" --capital 2000
nave cot report --json
nave cot report --report-type futures_only
```

Note: `nave cot report` now prints both `Futures Only` and `Futures+Options`
metrics for each asset. The `--report-type` option controls which dataset is
used as the primary bias source.

Read-only options research:

```bash
nave options crypto scan --input-file snapshots.json --json
nave options stocks scan --input-file snapshots.json --json
nave strategy evaluate crypto_iv_rv_defined_risk --domain crypto --input-file outcomes.json --json
```

The options research commands only consume supplied snapshots/outcomes. They
record point-in-time availability, keep crypto (BTC/ETH) and equity options
separate, and classify strategies as `EXPERIMENTAL`, `PROMISING`, `VALIDATED`,
or `REJECTED`. They never create orders or broker actions.

## 3) Python Module CLIs

Hyperliquid client module:

```bash
python -m trading.crypto.client summary --wallet hermes
python -m trading.crypto.client positions --wallet hermes
python -m trading.crypto.client orders --wallet hermes
python -m trading.crypto.client mids --wallet hermes
python -m trading.crypto.client markets --wallet hermes

# Existing BTC/ETH momentum scan with an appended current-universe research view
PYTHONPATH=. .venv/bin/python cli/main.py crypto momentum-scan \
  --include-universe-discovery --universe-size 100 --json

# Research-only point-in-time top-100 plus liquid-perpetual replay (offline)
PYTHONPATH=. .venv/bin/python cli/main.py crypto universe-momentum-scan \
  --fixture tests/fixtures/crypto_momentum_replay.json \
  --start 2026-08-25T00:00:00Z --end 2026-09-01T00:00:00Z \
  --cadence 6h --symbols ARB,CAKE,CRV,TWT,EDGE,PONS --json

# Structured crypto futures lifecycle over an explicit point-in-time fixture
PYTHONPATH=. .venv/bin/python cli/main.py crypto futures scan \
  --fixture tests/fixtures/crypto_momentum_replay.json \
  --start 2026-08-25T00:00:00Z --end 2026-09-01T00:00:00Z \
  --cot-regime neutral --json
PYTHONPATH=. .venv/bin/python cli/main.py crypto futures evaluate \
  --outcomes-file outcomes.json --json
PYTHONPATH=. .venv/bin/python cli/main.py crypto futures missed-moves \
  --outcomes-file outcomes.json --json
PYTHONPATH=. .venv/bin/python cli/main.py crypto futures status --json
python -m trading.crypto.client summary --wallet hermes --mainnet
```

Trading strategy module:

```bash
python -m trading.crypto.strategy --wallet hermes --coins BTC ETH
python -m trading.crypto.strategy --wallet hermes --coins BTC ETH --max-usd 50
python -m trading.crypto.strategy --wallet hermes --mainnet --live --coins BTC ETH --max-usd 50
```

COT modules:

```bash
python -m trading.crypto.cot.cot_fetcher
python -m trading.crypto.cot.cot_analyzer
```

MCP module:

```bash
python -m trading.mcp_server
```

Backend module:

```bash
python -m backend.app.main
```

## 4) Weekly COT / Backtest Workflows

Weekly analysis script:

```bash
python scripts/weekly_cot_analysis.py --capital 2000 --paper
python scripts/weekly_cot_analysis.py --capital 2000 --backtest
python scripts/weekly_cot_analysis.py --capital 2000 --backtest --learn
python scripts/weekly_cot_analysis.py --capital 2000 --live --wallet hermes
python scripts/weekly_cot_analysis.py --capital 2000 --setups 75_retracement order_block fvg liquidity_sweep breaker_block
```

Backtest runner:

```bash
python tests/backtest/run_backtests.py --objective setup-discovery
python tests/backtest/run_backtests.py --objective strategy-validation
python tests/backtest/run_backtests.py --objective setup-learning
python tests/backtest/run_backtests.py --objective setup-learning --timeframe weekly --capital 2000
python tests/backtest/run_backtests.py --objective setup-learning --timeframe 4h --capital 2000
python tests/backtest/run_backtests.py --objective setup-learning --timeframe 1h --capital 2000
python tests/backtest/run_backtests.py --all
python tests/backtest/run_backtests.py --report
```

Backtest cleanup:

```bash
python scripts/clean_backtest_files.py
python scripts/clean_backtest_files.py --output-dir trade_journal --archive-dir backtest_archive/invalid
python scripts/clean_backtest_files.py --delete
```

Fetch intraday Hyperliquid candles for 1H/4H backtests:

```bash
python scripts/fetch_hyperliquid_snapshots.py --coins BTC ETH SOL --intervals 1h 4h --max-history --out-dir data/hyperliquid_snapshots --mainnet
python scripts/fetch_hyperliquid_snapshots.py --coins BTC ETH --intervals 4h --out-dir data/hyperliquid_snapshots
```

## 5) Wallet and Vault Commands

Generate local wallets:

```bash
python scripts/setup_wallets.py
```

Show mnemonic (sensitive):

```bash
python scripts/show_mnemonic.py ironclaw
python scripts/show_mnemonic.py openfang
python scripts/show_mnemonic.py hermes
```

Wallet vault helper:

```bash
python scripts/wallet_vault.py list
python scripts/wallet_vault.py address hermes
```

Compatibility shim for Hyperliquid client:

```bash
python scripts/hyperliquid_client.py summary --wallet hermes
```

## 6) Data and Validation Scripts

OpenBB menu tool:

```bash
python scripts/openbb_tools.py
```

AAII scraper:

```bash
python scripts/check_aaii.py
```

Indicator batch validation:

```bash
python scripts/batch_test_indicators.py
```

On-chain quick verification:

```bash
python scripts/verify_onchain_simple.py
```

CBDC API validation:

```bash
python scripts/validate_cbdc_api.py
```

Tariff API validation:

```bash
python scripts/test_tariff_api.py
```

## 7) API Server Commands

Via CLI:

```bash
nave api start --host 127.0.0.1 --port 8000 --reload
```

Direct uvicorn:

```bash
uvicorn --app-dir=backend app.main:app --host 127.0.0.1 --port 8000 --reload
```
nave cot report
```

Weekly research + backtest workflow:

```bash
source .venv/bin/activate
python scripts/fetch_hyperliquid_snapshots.py --coins BTC ETH --intervals 4h --max-history --out-dir data/hyperliquid_snapshots --mainnet
python tests/backtest/run_backtests.py --objective setup-learning --timeframe 4h --capital 2000
nave cot report
```

Paper trade workflow:

```bash
source .venv/bin/activate
python scripts/setup_wallets.py
python -m trading.crypto.client summary --wallet hermes
nave trading run --strategy cot-weekly --paper --capital 2000
```
