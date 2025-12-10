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
├── .venv/               # Virtual environment (auto-created)
├── scripts/             # Analysis and utility scripts
├── docs/               # Documentation and configuration
├── extensions/         # OpenBB extensions
├── setup.py            # One-command environment setup
├── .envrc             # Direnv configuration (optional)
├── mise.toml          # Python version management
└── requirements.txt   # Python dependencies
```

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
