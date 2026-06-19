<p align="center">
	<img src="design/assets/logo_round.png" alt="NAVE logo" width="140" />
</p>

<h1 align="center">NAVE</h1>

Nave is a **terminal-first trading copilot**: one CLI, structured JSON for agents, and
documented theory you can refine over time. It is built for operators who want a clear
**enter / watch / stand aside** verdict—not another charting app.

## Vision

Nave applies a **top-down multi-timeframe** process (see [AGENTS.md](AGENTS.md) and
[docs/technical.yaml](docs/technical.yaml)):

| Timeframe | Role |
| --------- | ---- |
| **Weekly** | Macro bias and COT positioning (direction filter) |
| **Daily** | Trend confirmation and key swing levels |
| **4H** | Setup formation and entry zone |
| **1H** | Precise trigger and execution timing |

Three asset surfaces share the same CLI and Hermes contracts:

| Surface | What it does |
| ------- | ------------ |
| **Crypto** | BTC/ETH perps on Hyperliquid + Deribit options; COT, regime, momentum |
| **Stocks** | ISM-driven sector workflow, FMP fundamentals, Congressional disclosures, optional X interest |
| **Options** | Equity income setups (S&P universe), per-ticker playbook registry, hidden gems |
| **Agents** | Hermes tools and MCP—same logic as the CLI, JSON in / JSON out |

**Execution is human-gated.** Strategies and MCP tools default to dry-run / paper. The
operator decides when to go live on Hyperliquid.

**Code layout:** new work uses `trading.crypto.*` (COT, momentum, client, strategy).
Legacy `trading.*` imports still resolve via `trading/_compat.py`.

---

## Operator workflow

Typical cadence from the terminal:

```bash
# Every trading day — primary command
nave daily
nave daily --coins BTC --no-options    # faster
nave daily --json                      # cron / agents

# Weekly macro (Sunday or before sizing)
nave cot report --coins "BTC ETH"
python scripts/weekly_cot_analysis.py --capital 2000 --paper

# Equity options — daily income scan (~30d, congress + ranked setups)
nave options daily
nave options daily --limit 40 --top 10 --json
nave options track --mark --offsets 1,3,5,7

# Deep dive on one name from the shortlist
nave options analyze --ticker MSFT --days-to-exp 30

# Stocks (ISM release days)
nave stocks ism-report --kind manufacturing --sheet
nave congress                              # new STOCK Act filings since last run
```

| You want… | Start here |
| --------- | ---------- |
| BTC/ETH entry today | `nave daily` |
| Momentum scan (stricter default) | `nave crypto scan` |
| Momentum scan (config threshold) | `nave crypto momentum-scan` |
| One-symbol playbook | `nave crypto playbook --symbol BTCUSDT --side long` |
| Daily equity income (~30d) | `nave options daily` |
| S&P options rank scan | `nave options analyze --sp500-scan --sp500-limit 40` |
| Under-the-radar income + X | `nave options gems --limit 40 --top 10` |
| Per-ticker learned setups | `nave options registry show --ticker MSFT` |
| Registry research loop (slow, weekly) | `nave options registry iterate` |
| Agent / automation | `nave hermes tools`, `nave mcp run`, or [docs/agent_onboarding.md](docs/agent_onboarding.md) |

Deeper command lists: [docs/commands/README.md](docs/commands/README.md).

---

## Quick setup

```bash
git clone https://github.com/edyhvh/nave.git
cd nave
python setup.py
source ~/.zshrc   # or ~/.bashrc — reload after setup
nave --help
nave version
```

`python setup.py` creates `.venv`, installs deps, adds a `nave` shim, and runs
`direnv allow` when available.

Fallback if the shim is not on `PATH`:

```bash
PYTHONPATH=. python cli/main.py --help
```

### Environment keys

Copy `.env.example` → `.env`.

| Key | Required for |
| --- | ------------ |
| `FRED_API_KEY` | Macro / OpenBB data |
| `FMP_API_KEY` | Stocks ISM screen, `nave congress` |
| `MASSIVE_API_KEY` | Optional fundamentals (stocks workflow) |
| `X_BEARER_TOKEN` or twscrape | `nave stocks x-analyze`, options gems X boost |
| `HELIUS_API_KEY` | `nave memecoin` scanner only |

Hyperliquid wallets: `python scripts/setup_wallets.py` — see [docs/web3-setup.md](docs/web3-setup.md).

---

## Crypto: daily entry

**`nave daily`** is the single operator command for BTC/ETH. It runs the unified stack in
`trading/crypto/analysis/` (`crypto_analysis_v4`): COT permission, bear/bull regime phases,
momentum on 4H/1H, active regime thesis, and optional Deribit options.

```bash
nave daily
nave crypto daily              # alias
nave crypto position-review    # same stack
nave daily --coins BTC
nave daily --no-options
nave daily --json
python scripts/refresh_current_setup.py
python scripts/crypto_thesis_check.py
```

Each coin reports: action, direction, confidence, regime phase, 4H zone, stop, momentum
score, optional spread line, and playbook reasons. Trade **ENTER**; optionally stalk **WATCH**.

### Research and backtest

```bash
nave crypto scan --symbols BTCUSDT,ETHUSDT --tf 4h,1h --json
# Default operator scan (score threshold 90)

nave crypto momentum-scan --json
# Same engine; threshold from momentum config (typically 78)

nave crypto playbook --symbol BTCUSDT --side long --json
python scripts/unified_backtest.py --fast --coins BTC ETH
python scripts/theory_v2_backtest.py --coins BTC ETH
```

Agents bundling review + theory: `python scripts/daily_scan.py` (see
[docs/agent_onboarding.md](docs/agent_onboarding.md)). Operators should still prefer
**`nave daily`** for entries.

### Backtest snapshot (unified, `--fast`)

185 trades, **78.9%** win rate, **+1.83R** pooled expectancy, **8/8** regimes with trades at
period rollup. Label: **medium** confidence—2017 window has partial 4H/1H coverage;
pre-2022 lacks historical COT replay.

Artifact:
[`docs/analysis/raw/unified_backtest_20260601T222143Z.json`](docs/analysis/raw/unified_backtest_20260601T222143Z.json)

Re-run after material threshold changes:

```bash
python scripts/unified_backtest.py --fast --coins BTC ETH
```

---

## Options: equity and crypto

### Daily income scan (start here)

One command for **today’s ~30-day income setups**: refreshes congressional filings
(needs `FMP_API_KEY`), scans the S&P universe, ranks executable strategies, and boosts
names politicians recently disclosed.

```bash
nave options daily
nave options daily --limit 40 --top 10 --days-to-exp 30 --sheet
nave options daily --no-refresh-congress    # skip FMP if you already ran nave congress
nave options daily --json
nave options daily --strict-filters         # old replay-tuned gates (fewer names)
```

Daily mode uses relaxed gem filters (~30d income). Output includes per-ticker **position
detail panels** (legs, bias, thesis, risk metrics, decision, deep-dive command). If no gems
pass, you still get a **watchlist** and **scan picks** with full position context.

Equivalent manual steps:

```bash
nave congress
nave options gems --limit 40 --top 10 --days-to-exp 30 --with-congress
```

**Not for daily use:** `nave options registry iterate` — slow walk-forward + journal
merge (weekly/monthly research). Use `registry list` / `registry show` to read what
was already learned.

### Single ticker

```bash
nave options analyze --ticker MSFT --days-to-exp 30
nave options analyze --ticker MSFT --days-to-exp 30 --terminal --llm-prompt
nave options analyze --ticker MSFT --strategy bull-put \
  --short-put 395 --long-put 390 --expiration 2026-06-18
nave options analyze --ticker MSFT --json
```

Human tables: `--sheet`. Terminal charts: `--terminal` (alias `--ascii`).

### Universe scan

Scans S&P names, keeps only executable `trade_candidate` setups, ranks by score / EV / PoP:

```bash
nave options analyze --sp500-scan --sp500-limit 100 --top-trades 3
nave options analyze --sp500-scan --scan-workers 8 --terminal
```

Implementation: `options/universe_scan.py` (shared by CLI and Hermes).

### Hidden gems

Same engine as `nave options daily`, without auto-running congress first:

```bash
nave options gems --limit 40 --top 10 --days-to-exp 30 --sheet
nave options gems --fetch-x 3 --json
```

(`--sp500-limit` is an alias for `--limit` on `gems` and `daily`, matching `analyze --sp500-scan`.)

### Playbook registry (S&P top 40)

Per-ticker learned strategies from replay and walk-forward merge gates:

```bash
nave options registry build --limit 40
nave options registry learn --ticker WFC
nave options registry list
nave options registry show --ticker WFC
nave options registry iterate              # slow: walk-forward → journal → rebuild (weekly)
```

### BTC/ETH (Deribit)

```bash
nave options analyze BTC --source deribit --days-to-exp 30
nave options opportunities --coins BTC,ETH --source deribit --sheet
```

---

## Stocks and Congress

ISM-driven screening (manufacturing EPS growth vs services revenue-growth modes):

```bash
nave stocks ism-scan --kind manufacturing
nave stocks screen --kind manufacturing --top-n 5 --capital 10000
nave stocks ism-report --kind manufacturing --top-n 5 --min-confidence 0.7 --sheet
nave stocks ism-report --telegram-markdown-v2
nave stocks journal-stats
nave stocks x-analyze --tickers AAPL,MSFT
```

**Congress** (STOCK Act, new since last run):

```bash
nave congress
nave congress --json
```

Requires `FMP_API_KEY`. State: `var/politicians_cache/seen.json`.

Brokers (`AlpacaBroker`, `OndoBroker`) are stubs; strategies default to `dry_run=True`.

---

## Agents: Hermes and MCP

### CLI discovery

```bash
nave hermes tools
nave hermes call --tool cot_report --args-json '{"coins": "BTC ETH"}'
nave hermes call --tool position_review --args-json '{"coins": "BTC ETH"}'
nave hermes call --tool momentum_scan --args-json '{"symbols": "BTCUSDT,ETHUSDT"}'
nave hermes call --tool options_scan --args-json '{"ticker": "MSFT", "days_to_exp": 30}'
nave hermes call --tool hidden_gems_scan --args-json '{"limit": 40, "top": 5}'
nave hermes gateway-invoke '{"tool": "theory_v2_scan", "arguments": {"coins": "BTC ETH"}}'
nave mcp run
```

Local MCP exposes repo-native tools; `nave mcp fmp-connector` is optional vendor FMP access.

Full agent daily flow: [docs/agent_onboarding.md](docs/agent_onboarding.md) ·
[docs/hermes_integration.md](docs/hermes_integration.md).

### Cron-friendly bundle

```bash
python scripts/daily_scan.py
python scripts/daily_scan.py --out var/reports/daily_scan.json
```

---

## Hyperliquid execution

```bash
python scripts/setup_wallets.py
python -m trading.crypto.client summary --wallet hermes
python -m trading.crypto.strategy --wallet hermes --coins BTC ETH   # dry-run default

nave trading run --strategy cot-weekly --paper --capital 2000
nave trading run-strategy --wallet hermes --dry-run
```

Weekly COT driver:

```bash
python scripts/weekly_cot_analysis.py --capital 2000 --paper
python scripts/weekly_cot_analysis.py --capital 2000 --cot-history 3
nave cot analyze --coins BTC ETH
```

Wallets are encrypted under `~/.secrets/nave-wallets/` — never committed. Details:
[docs/web3-setup.md](docs/web3-setup.md).

---

## Unified CLI reference

```bash
nave --help
nave version
nave daily
nave congress
nave crypto --help
nave options --help
nave stocks --help
nave cot --help
nave trading --help
nave data fetch all
nave api start --reload
```

**Output modes:** human terminal (default), `--json` for automation, `--sheet` for tables,
`--telegram-markdown-v2` where supported. Disable Typer status lines in scripts:

```bash
NAVE_CLI_STATUS=0 nave stocks ism-report --json
```

---

## Testing

```bash
pytest -q
pytest tests/test_trading_imports.py tests/test_options_cli.py \
  tests/test_momentum_engine.py tests/test_hermes_integration.py -q
```

---

## Troubleshooting

```bash
python setup.py && source ~/.zshrc && which nave
PYTHONPATH=. python cli/main.py --help
rm -rf .venv && python setup.py
```

---

## Further reading

| Doc | Contents |
| --- | -------- |
| [docs/commands/README.md](docs/commands/README.md) | Full command reference |
| [docs/agent_onboarding.md](docs/agent_onboarding.md) | Hermes daily flow and tools |
| [docs/hermes_integration.md](docs/hermes_integration.md) | Integration contracts |
| [docs/analysis/current_setup.md](docs/analysis/current_setup.md) | Live BTC/ETH setup (`python scripts/refresh_current_setup.py`) |
| [docs/analysis/btc_eth_historical_review.md](docs/analysis/btc_eth_historical_review.md) | Historical theory review |
| [docs/technical.yaml](docs/technical.yaml) | Patterns, IPDA, F.I.T.S. |
| [docs/cot_integration.yaml](docs/cot_integration.yaml) | COT logic and sizing |
| [AGENTS.md](AGENTS.md) | Theory refinement loop for contributors |
| [docs/web3-setup.md](docs/web3-setup.md) | Wallets and Hyperliquid |
