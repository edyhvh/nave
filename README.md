# Nave

A financial data analysis platform that tracks macroeconomic indicators and cryptocurrency market data using OpenBB. The project focuses on monitoring liquidity, monetary policy, sentiment, debt metrics, and crypto-specific indicators to predict market movements and assess fiat currency health.

## Project Overview

This project analyzes 20+ economic and financial indicators across 8 categories:

- **Liquidity and Monetary Policy**: TGA, RRP, Fed injections, interest rates
- **Sentiment and Market Psychology**: AAII surveys, risk appetite (VIX)
- **Debt, Deficit, and Fiat Currency Value**: Debt/GDP ratios, purchasing power
- **Crypto-Specific and Global Flows**: Market cap, ETF flows, capital flows
- **Inflation and Employment**: CPI/PCE, unemployment rates
- **Bond and Commodity Markets**: Yield curves, commodity prices
- **Global Activity and On-Chain**: PMI indices, blockchain metrics
- **Risk and Digital Currencies**: Geopolitical risk, CBDC tracking

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

## Project Structure

```
nave/
├── cli/                 # Unified Typer CLI
│   ├── main.py          # Entrypoint and command group registration
│   ├── commands/        # Modular command groups
│   └── utils.py         # Shared CLI prompt helpers
├── core/                # Cross-cutting app primitives
│   ├── config.py        # Typed defaults and shared configuration
│   ├── exceptions.py    # Domain-level exceptions
│   └── logger.py        # Logger bootstrap helpers
├── hermes/              # Hermes Agent integration contracts
│   └── integration.py   # Tool registry + dispatch + gateway payload handling
├── trading/             # Trading integration package
│   ├── vault.py         # Encrypted wallet storage (Fernet/AES)
│   ├── client.py        # Hyperliquid REST + SDK client
│   ├── signals.py       # Signal types and macro signal producers
│   └── strategy.py      # BaseStrategy + example strategy
├── scripts/             # Analysis and utility scripts
│   ├── setup_wallets.py # One-time EVM wallet generation
│   ├── show_mnemonic.py # Reveal seed phrase securely (60s auto-clear)
│   └── openbb_tools.py  # OpenBB data fetching helpers
├── docs/               # Documentation and configuration
│   └── web3-setup.md   # Wallet setup and trading integration guide
├── extensions/         # OpenBB extensions
├── setup.py            # One-command environment setup
├── .envrc             # Direnv configuration (optional)
├── mise.toml          # Python version management
└── requirements.txt   # Python dependencies
```

## Multi-asset architecture (crypto + stocks)

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
├── stocks/         # ISM + Massive.com fundamentals workflow
│   ├── ism_scraper.py     # httpx+BS4 primary; Playwright fallback
│   ├── data_provider.py   # Massive.com REST (rate-limited: 5 rpm)
│   ├── screener.py        # PE-vs-sector + EPS-growth ranking
│   ├── strategy.py        # ISMSectorStrategy
│   └── journal.py         # StockJournal (tags asset_class=stock)
└── journal/        # Shared journal — asset_class aware
```

Back-compat: the legacy top-level paths (`trading.client`, `trading.signals`,
`trading.cot.cot_analyzer`, …) keep working via `sys.modules` aliases set up
by `trading/_compat.py`, so scripts/, tests/, cli/, and hermes/integration.py
continue to import the crypto stack unchanged.

## Stocks workflow (ISM + Massive.com)

```bash
# 1. Install extra deps
pip install -r requirements.txt

# 2. Add your Massive API key to .env (free tier = 5 rpm)
MASSIVE_API_KEY=your_key

# 3. Fetch the latest ISM Manufacturing report
nave stocks ism-scan --kind manufacturing
nave stocks ism-scan --kind services --json

# 4. Run the full screener (ISM → fundamentals → ranked plan)
nave stocks screen --kind manufacturing --top-n 5 --capital 10000
nave stocks screen --kind manufacturing --top-n 5 --max-pe 28 --min-eps-growth 8

# 5. Override the ticker universe (free tier is rpm-bound — stay lean)
nave stocks screen --universe-json '{"Industrials": ["GE","CAT"]}'

# 6. Build complete ISM report (hottest/worst industries + filtered picks)
nave stocks ism-report --kind manufacturing --top-n 5 --max-pe 28 --min-eps-growth 8
nave stocks ism-report --json

# 7. Stock-only journal stats (crypto trades excluded)
nave stocks journal-stats
```

**ISM data sources**: default path uses `httpx + BeautifulSoup` against
the public ISM press releases — no browser dependency. Pass
`--playwright` to `stocks ism-scan` for a JS-rendered mirror (requires
`pip install playwright && python -m playwright install chromium`).

**Brokers**: `AlpacaBroker` and `OndoBroker` are stubs. All read/write
methods raise `NotImplementedError` until the real integrations land,
which is safe because the strategy defaults to `dry_run=True`.

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

### Weekly COT Analysis (feat/cot_grok)

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

See `docs/technical.yaml` for full philosophy and `trading/cot/` for implementation.

## Roadmap after PR #8

- PR #8 (merged): COT as main weekly driver
- PR #9 (this branch): modular COT pipeline with real-data-only execution planning

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
nave api start --reload
nave mcp
nave cot analyze --coins BTC ETH
nave data fetch aaii
nave hermes tools
nave hermes call --tool cot_report --args-json '{"coins": "BTC ETH"}'
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
