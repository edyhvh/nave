# Nave

A BTC/ETH trading copilot built on OpenBB macro data, with a stocks workflow
on top. Crypto entries flow through a top-down weekly → daily → 4H → 1H
pipeline (`trading.crypto.theory_v2`), and the same engine is exposed to
Hermes/MCP agents. Stocks use an ISM-driven sector screener with FMP
fundamentals.

## What's in here

- **Crypto trading (`trading/crypto/`)** — `theory_v2` engine (iter 18:
  pooled +44.14R / 78% WR over 9.5y backtest), Hyperliquid integration,
  weekly COT gate, encrypted wallet vault.
- **Stocks workflow (`trading/stocks/`)** — ISM-driven sector ranking,
  FMP fundamentals, EPS/revenue-growth screener, paper-trading via
  Alpaca/Ondo broker stubs.
- **Macro indicators (`backend/app/services/`, `extensions/openbb_*`)** —
  20+ indicators across liquidity, sentiment, debt, on-chain, bonds,
  inflation/employment, and CBDC tracking. Used as gates for the trading
  engines, not as a standalone product.
- **Agent integration (`hermes/`, `trading/crypto/mcp_server.py`)** —
  Hermes/MCP tool surface (`daily_scan`, `theory_v2_scan`,
  `strategy_context`, `recommend_position`, `cot_report`, `weekly_plan`).
- **CLI (`cli/`)** — unified `nave` Typer entrypoint covering trading,
  stocks, COT, Hermes, MCP, and data ops.

## Installation

### Quick Setup (One Command)

```bash
git clone <repo-url>
cd nave
python setup.py
```

That's it! The setup script will:

- Install Python 3.12 via mise (if available)
- Create a virtual environment
- Install all dependencies (OpenBB + extensions)
- Configure the environment
- Install a reliable `nave` CLI shim into `.venv/bin`
- Add `.venv/bin` PATH automation to your active shell rc (`.zshrc` or `.bashrc`)

### Manual Setup (If needed)

If the automatic setup fails:

```bash
# Install Python 3.12
mise install python@3.12

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Optional: make nave command available in this shell
export PATH="$(pwd)/.venv/bin:$PATH"
```

## CLI Troubleshooting

If `nave --help` returns `command not found`:

```bash
# Ensure setup completed at least once
python setup.py

# Reload shell config where setup added PATH automation
source ~/.zshrc   # or: source ~/.bashrc

# Verify command resolution
which nave
nave --help
```

Quick fallback (always works from repo root):

```bash
PYTHONPATH=. python cli/main.py --help
```

## API Key Setup

### FRED API Key

**Why we need it:** Many indicators rely on Federal Reserve Economic Data (FRED), including TGA, RRP, interest rates, employment, and inflation data. An API key is required to access this data through OpenBB.

**Setup:**

1. Get your free API key at: https://fred.stlouisfed.org/docs/api/api_key.html
2. Create a `.env` file in the project root and add your credentials:
   ```bash
   FRED_API_KEY=your_fred_api_key_here
   ```
3. Configure OpenBB with your key:

   ```bash
   python -c "from openbb import obb; obb.user.credentials.fred_api_key.set('your_fred_api_key_here'); obb.account.save()"
   ```

   Or use the interactive setup:

   ```bash
   python -c "from openbb import obb; print('FRED Setup:'); key=input('Enter FRED API key: '); obb.user.credentials.fred_api_key.set(key); obb.account.save(); print('✅ FRED key saved')"
   ```

**Note:** The `.env` file is in `.gitignore` and will never be committed to the repository.

## Usage

### One-time shell setup for direnv

```bash
# bash
echo 'eval "$(direnv hook bash)"' >> ~/.bashrc

# zsh
echo 'eval "$(direnv hook zsh)"' >> ~/.zshrc
```

### Working with the Environment

```bash
# Preferred: auto-activate local .venv in this folder
direnv allow

# Run scripts easily
./run.sh openbb_tools  # Interactive menu for all OpenBB operations

# Check environment
python --version  # Python 3.12.x
pip list          # See installed packages
```

If you don't use direnv, run one of:

```bash
source .venv/bin/activate
# or
./scripts/dev_shell.sh
```

## Project structure (crypto + stocks)

The `trading/` package is organized by asset class so that strategies and
broker integrations can live side by side without mixing concerns:

```
trading/
├── base/           # Asset-agnostic abstractions
│   ├── broker.py   # BaseBroker ABC, BrokerResponse envelope
│   ├── strategy.py # AbstractStrategy (compute → execute)
│   └── journal.py  # BaseJournal scoped to an AssetClass
├── brokers/
│   ├── hyperliquid.py  # adapter over trading.crypto.client
│   ├── alpaca.py       # stub (equities, integration pending)
│   └── ondo.py         # stub (RWA/DeFi, integration pending)
├── crypto/         # Hyperliquid + COT + theory-v2 stack
├── stocks/         # ISM + FMP fundamentals workflow
│   ├── ism_scraper.py     # httpx+BS4 primary; Playwright fallback
│   ├── data_provider.py   # FMP REST + cache-backed fundamentals client
│   ├── screener.py        # PE-vs-sector + EPS-growth ranking
│   ├── strategy.py        # ISMSectorStrategy
│   └── journal.py         # StockJournal (tags asset_class=stock)
└── journal/        # Shared journal — asset_class aware
```

Back-compat: the legacy top-level paths (`trading.client`, `trading.signals`,
`trading.cot.cot_analyzer`, …) keep working via `sys.modules` aliases set up
by `trading/_compat.py`, so scripts/, tests/, cli/, and hermes/integration.py
continue to import the crypto stack unchanged.

## Stocks workflow (ISM + FMP)

```bash
# 1. Install extra deps
pip install -r requirements.txt

# 2. Add your FMP API key to .env
FMP_API_KEY=your_key

# Optional: override the cache / budget controls
FMP_CACHE_TTL_SECONDS=86400

# 3. Fetch the latest ISM Manufacturing report
nave stocks ism-scan --kind manufacturing
nave stocks ism-scan --kind services --json

# 4. Run the full screener (ISM → fundamentals → ranked plan)
nave stocks screen --kind manufacturing --top-n 5 --capital 10000
nave stocks screen --kind manufacturing --top-n 5 --max-pe 28 --min-eps-growth 8
nave stocks screen --kind manufacturing --top-n 5 --max-pe 28 --min-eps-growth 8 --min-confidence 0.7

# 4b. Services mode — long-term revenue growth + PE-relative filter
nave stocks screen --kind services --mode services --top-n 5
nave stocks ism-report --kind services --mode services --sheet

# 5. Override the ticker universe (keep it lean to respect the 250-call/day cap)
nave stocks screen --universe-json '{"Industrials": ["GE","CAT"]}'

# 6. Build complete ISM report (hottest/worst industries + filtered picks)
nave stocks ism-report --kind manufacturing --top-n 5 --max-pe 28 --min-eps-growth 8
nave stocks ism-report --kind manufacturing --top-n 5 --max-pe 28 --min-eps-growth 8 --min-confidence 0.7
nave stocks ism-report --json
nave stocks ism-report --sheet
nave stocks ism-report --json --sheet

# Default report view targets up to 10 longs + 10 shorts, but may return fewer
# after confidence and valuation filters.
# Output now includes company industry, driver ISM industry, confidence,
# industry/sector PE context, and EPS source metadata.
nave stocks ism-report --kind manufacturing
nave stocks ism-report --kind manufacturing --min-confidence 0.5

# 7. Stock-only journal stats (crypto trades excluded)
nave stocks journal-stats
```

**ISM data sources**: default path uses `httpx + BeautifulSoup` against
the public ISM press releases — no browser dependency. Pass
`--playwright` to `stocks ism-scan` for a JS-rendered mirror (requires
`pip install playwright && python -m playwright install chromium`).

**Fundamentals data source**: ISM stock screening now uses Financial Modeling
Prep via `FMP_API_KEY`. The client keeps a persistent cache under `var/fmp_cache/`
so repeat CLI/Hermes/MCP runs do not burn the 250 calls/day quota unnecessarily.

### Screening modes

The screener supports two ranking strategies via `--mode` (defaults to the
value of `--kind`):

- **`--mode manufacturing`** *(default)* — ranks purely by EPS growth
  next year. Confidence = `0.6 × ISM industry-match + 0.4 × EPS confidence`.
  Unchanged from the original flow.
- **`--mode services`** — ranks by **long-term revenue growth forecast**
  (FMP analyst-estimate CAGR, yfinance trailing `revenueGrowth` as
  fallback) and drops names where `company PE ≥ sector average PE`
  (a secondary PE-relative check). No other scoring.

Example Services-mode output (truncated):

```
ISM Services — March 2026
Mode: services
Criteria: mode=services, top_n=5, min_eps_growth=None, min_conf=0.3

Top longs (hottest sectors)
┃ Symbol ┃ Name    ┃ Side ┃ Sector                 ┃ Rev LT % ┃ Rev src                 ┃ Score ┃
│ GOOGL  │ Alphabet│ long │ Communication Services │   18.0   │ fmp_analyst_estimate    │ +0.180│
│ META   │ Meta    │ long │ Communication Services │   12.0   │ fmp_analyst_estimate    │ +0.120│
│ DIS    │ Disney  │ long │ Communication Services │    6.0   │ yfinance_trailing_...   │ +0.060│
```

**Brokers**: `AlpacaBroker` and `OndoBroker` are stubs. All read/write
methods raise `NotImplementedError` until the real integrations land,
which is safe because the strategy defaults to `dry_run=True`.

### Professional CLI behavior (Typer)

The CLI uses a custom `ProfessionalTyper` wrapper that prints command
start/success/fail status lines (to stderr) with elapsed time.

```bash
# Disable status lines for clean script logs
NAVE_CLI_STATUS=0 nave stocks ism-report --json

# Re-enable (default)
NAVE_CLI_STATUS=1 nave stocks ism-report --json
```

Typer itself does not automatically render JSON as a table. In Nave, use
`--sheet` for human-readable terminal tables and `--json` for machine output.

For stocks reports, `--min-confidence` defaults to `0.7`. Lower it if you want
to inspect weaker matches, but the stricter default is intended to block false
positives where a company shares a broad sector with an ISM industry but does
not actually belong to that industry.

The same confidence filter now applies to `nave stocks screen`, so strategy
plans and reports use the same false-positive guardrail by default.

## Trading on Hyperliquid

Nave integrates with [Hyperliquid](https://hyperliquid.xyz) for futures paper
trading. Wallets are managed locally via an encrypted vault — no MetaMask or
browser required.

### Quick start

```bash
# 1. Generate wallets (one-time)
python scripts/setup_wallets.py

# 2. Check account state on testnet
python -m trading.client summary --wallet hermes

# 3. Run a strategy in dry-run mode (no real orders)
python -m trading.strategy --wallet hermes --coins BTC ETH
```

### Weekly COT Analysis

COT is now the **main weekly driver** for trading setups.

```bash
# Run weekly analysis (Sunday)
python scripts/weekly_cot_analysis.py --capital 2000 --paper

# Historical variation report (last 3 calendar months)
python scripts/weekly_cot_analysis.py --capital 2000 --cot-history 3

# Or with live execution (careful!)
python scripts/weekly_cot_analysis.py --capital 2000 --live --wallet hermes

# Unified CLI
nave trading run --paper --strategy cot-weekly
```

**Features**:

- Fetches latest CME COT for BTC (133741) and ETH
- Compares setups using F.I.T.S. + IPDA philosophy (75% retracement, order blocks, etc.)
- Recommends best asset + capital allocation, leverage, SL/TP
- Scans other Hyperliquid perps for liquidity/funding opportunities
- Dry-run by default

See `docs/technical.yaml` for full philosophy and `trading/crypto/cot/` for
the COT pipeline implementation. The full theory-refinement workflow that
produced theory_v2 is described in `AGENTS.md`.

### Wallets

Two EVM wallets are pre-generated for the trading agents:

| Agent      | Address                                                 |
| ---------- | ------------------------------------------------------- |
| `openfang` | `0x48b6cB6ea38D48304B5bc634294be4F0EFC52b51`            |
| `ironclaw` | `0x3fB31b355b82B6B1421dBb914364c0Ec5e72868F`            |
| `hermes`   | Generated locally via `python scripts/setup_wallets.py` |

Private keys and seed phrases are encrypted in `~/.secrets/nave-wallets/`
and never committed to this repository.

For full setup instructions see **[docs/web3-setup.md](docs/web3-setup.md)**.

## Unified CLI

After setup (`python setup.py`), use the professional `nave` CLI (powered by Typer):

```bash
nave --help
nave version
nave trading run-strategy --wallet hermes --dry-run
nave trading run --strategy cot-weekly --paper
nave api start --reload
nave mcp run
nave cot analyze --coins BTC ETH
nave data fetch aaii
nave hermes tools
nave hermes call --tool cot_report --args-json '{"coins": "BTC ETH"}'
nave stocks ism-report --kind manufacturing --top-n 5 --min-confidence 0.7 --sheet
```

This unifies all previous scripts, strategies, MCP, and backend. Legacy `./run.sh` and `python -m trading.*` still work.

## Hermes Agent Integration

Nave now exposes a dedicated Hermes integration layer designed for MCP and
gateway workflows with structured JSON outputs.

### Skill/Tool Discovery

```bash
nave hermes tools
```

### Direct Tool Calls

```bash
# Latest COT report (JSON)
nave hermes call --tool cot_report --args-json '{"coins": "BTC ETH"}'

# Historical COT variation (last 3 months)
nave hermes call --tool cot_history --args-json '{"months": 3, "coins": "BTC ETH"}'

# Weekly execution plan
nave hermes call --tool weekly_plan --args-json '{"capital": 2000, "wallet": "hermes"}'
```

### Gateway-Compatible Invocation Payload

```bash
nave hermes gateway-invoke '{"tool": "cot_report", "arguments": {"coins": "BTC ETH"}}'
```

### MCP Server Tools Available to Hermes

`trading/mcp_server.py` now includes COT and weekly-plan oriented tools:

- `cot_report`
- `cot_history`
- `weekly_plan`
- plus existing account and execution tools (`account_summary`, `open_position`, etc.)

### Optional FMP Remote MCP

FMP also exposes its own remote MCP server. If you want direct vendor tools in
an MCP-capable client, configure this URL:

```bash
nave mcp fmp-connector
```

That command prints the remote connector URL built from `FMP_API_KEY`. Keep in
mind FMP MCP calls count against the same vendor quota as REST calls.

## Troubleshooting

### Environment Issues

```bash
# Rebuild environment
rm -rf .venv
python setup.py
```

### Dependency Issues

```bash
# Preferred
direnv allow

# Or manual
source .venv/bin/activate
pip install -r requirements.txt --upgrade
```

### Python Version Issues

```bash
mise install python@3.12
rm -rf .venv
python setup.py
```
