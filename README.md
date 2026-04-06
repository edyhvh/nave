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

### Working with the Environment

```bash
# Activate environment (automatic with direnv, or manual)
source .venv/bin/activate

# Run scripts easily
./run.sh openbb_tools  # Interactive menu for all OpenBB operations

# Check environment
python --version  # Python 3.12.x
pip list          # See installed packages
```

## Project Structure

```
nave/
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

## Trading on Hyperliquid

Nave integrates with [Hyperliquid](https://hyperliquid.xyz) for futures paper
trading. Wallets are managed locally via an encrypted vault — no MetaMask or
browser required.

### Quick start

```bash
# 1. Generate wallets (one-time)
python scripts/setup_wallets.py

# 2. Check account state on testnet
python -m trading.client summary --wallet openfang

# 3. Run a strategy in dry-run mode (no real orders)
python -m trading.strategy --wallet openfang --coins BTC ETH
```

### Weekly COT Analysis (feat/cot_grok)

COT is now the **main weekly driver** for trading setups.

```bash
# Run weekly analysis (Sunday)
python scripts/weekly_cot_analysis.py --capital 2000 --paper

# Backtest mode analysis
python scripts/weekly_cot_analysis.py --capital 2000 --backtest

# Or with live execution (careful!)
python scripts/weekly_cot_analysis.py --capital 2000 --live --wallet openfang

# Unified CLI
nave trading run --paper --strategy cot-weekly
nave trading run --backtest --strategy cot-weekly
```

**Features**:

- Fetches latest CME COT for BTC (133741) and ETH
- Compares setups using F.I.T.S. + IPDA philosophy (75% retracement, order blocks, etc.)
- Recommends best asset + capital allocation, leverage, SL/TP
- Scans other Hyperliquid perps for liquidity/funding opportunities
- Dry-run by default

See `docs/technical.yaml` for full philosophy and `trading/cot/` for implementation.

## Roadmap after PR #8

- PR #8 (merged): COT as main weekly driver + robust backtesting framework
- Next PR: Strategy Testing Engine + Automatic Setup Learning + Paper Trading execution

### Wallets

Two EVM wallets are pre-generated for the trading agents:

| Agent      | Address                                      |
| ---------- | -------------------------------------------- |
| `openfang` | `0x48b6cB6ea38D48304B5bc634294be4F0EFC52b51` |
| `ironclaw` | `0x3fB31b355b82B6B1421dBb914364c0Ec5e72868F` |

Private keys and seed phrases are encrypted in `~/.secrets/nave-wallets/`
and never committed to this repository.

For full setup instructions see **[docs/web3-setup.md](docs/web3-setup.md)**.

## Unified CLI

After setup (`python setup.py`), use the professional `nave` CLI (powered by Typer):

```bash
nave --help
nave version
nave trading run-strategy --wallet openfang --dry-run
nave api start --reload
nave mcp
nave cot analyze --coins BTC ETH
nave data fetch aaii
```

This unifies all previous scripts, strategies, MCP, and backend. Legacy `./run.sh` and `python -m trading.*` still work.

## Troubleshooting

### Environment Issues

```bash
# Rebuild environment
rm -rf .venv
python setup.py
```

### Dependency Issues

```bash
source .venv/bin/activate
pip install -r requirements.txt --upgrade
```

### Python Version Issues

```bash
mise install python@3.12
rm -rf .venv
python setup.py
```
