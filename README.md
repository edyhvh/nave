# Nave

A quantitative trading system integrating OpenBB financial data with Hyperliquid perpetual futures execution. Built with the Nave Philosophy for systematic, risk-managed trading.

## Features

- **OpenBB Integration**: Access comprehensive financial data (stocks, crypto, macro, forex)
- **Hyperliquid Trading**: Direct integration with Hyperliquid DEX for perpetual futures
- **Secure Wallet Management**: Fernet-encrypted wallet storage (never in env vars)
- **COT Analysis**: CME Commitment of Traders as primary weekly sentiment driver
- **F.I.T.S. Framework**: Fundamental + Intermarket + Technical + Sentiment analysis
- **Risk Management**: Position sizing based on risk, not position size

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/edyhvh/nave.git
cd nave

# Install dependencies
pip install -r requirements.txt

# Set up wallet encryption (one-time)
python -c "from trading.vault import WalletVault; WalletVault().setup_interactive()"
```

### Weekly COT Analysis (Sunday Driver)

The primary weekly workflow analyzes CME COT reports to generate trading setups:

```bash
# Dry run (recommended for testing)
./run.sh weekly-cot

# With custom capital
./run.sh weekly-cot --capital 5000

# Live trading mode (requires wallet setup)
./run.sh weekly-cot --live
```

**What it does:**
1. Fetches latest COT data for BTC (133741) and ETH (138741)
2. Compares setups using FITS framework (Fundamental + Intermarket + Technical + Sentiment)
3. Selects best asset (BTC or ETH) based on COT bias + confluence
4. Generates position sizing with risk-based allocation
5. Scans Hyperliquid perps for additional opportunities
6. Outputs comprehensive markdown report with recommendations

## Trading on Hyperliquid

### Wallet Setup

```python
from trading import WalletVault

vault = WalletVault()
vault.store_wallet("openfang", "your-private-key")

# Verify
print(vault.address("openfang"))
```

### Basic Trading

```python
from trading import HyperliquidClient

# Connect to testnet (default)
client = HyperliquidClient("openfang", testnet=True)
client.summary()

# Open a position
client.market_open("ETH", "long", size_usd=100.0)

# Close position
client.market_close("ETH")
```

### Using the COT Strategy

```python
from trading import HyperliquidClient, CotWeeklyStrategy

client = HyperliquidClient("openfang", testnet=True)
strategy = CotWeeklyStrategy(
    client=client,
    capital_usd=2000.0,
    risk_pct=0.10,
    dry_run=True
)

# Generate weekly report
report = strategy.weekly_report()
print(report)

# Or run full analysis
result = strategy.run_weekly_analysis()
print(f"Best asset: {result['best_asset']}")
print(f"Position size: ${result['sizing'].size_usd:,.0f}")
```

## Nave Philosophy

### F.I.T.S. Framework

All trading decisions integrate four pillars:

1. **Fundamental**: ETF flows, network metrics, on-chain data
2. **Intermarket**: VIX, TGA, RRP, DXY, yields (liquidity conditions)
3. **Technical**: IPDA market structure, 75% retracements, FVG, confluence
4. **Sentiment**: COT as primary driver (smart money positioning)

### IPDA Market Structure

- **Expansion**: COT extreme + price breakout
- **Retracement**: Pullback into value (75% level)
- **Regression**: Mean reversion within trend (primary setup)
- **Consolidation**: Range-bound (use options or reduce size)

### Risk Management

- **Position Sizing**: Risk amount / Stop distance
- **Stop Loss**: At invalidation point (structure break)
- **Take Profit**: Minimum 2:1 R:R, scale out at targets
- **Leverage**: 1-10x scaled by confidence (max 10x)
- **Risk per Trade**: 8-12% of capital

### Key Setups

- **75% Retracement**: Entry on deep pullback in trend
- **Mitigation Blocks**: Previous resistance becomes support
- **Fair Value Gaps**: Imbalance fills as entry zones
- **Confluence Zones**: Institutional levels (00/20/50/80) + structure

## Project Structure

```
nave/
├── trading/                 # Core trading module
│   ├── __init__.py         # Public API exports
│   ├── client.py           # Hyperliquid client
│   ├── vault.py            # Encrypted wallet storage
│   ├── signals.py          # Signal generation (COT, Macro, Technical)
│   ├── strategy.py         # Strategy implementations
│   ├── mcp_server.py       # Model Context Protocol server
│   └── cot/                # COT integration
│       ├── __init__.py
│       ├── cot_fetcher.py  # CME COT data fetching
│       └── cot_analyzer.py # COT signal generation
├── scripts/
│   ├── openbb_tools.py     # OpenBB integration tools
│   └── weekly_cot_analysis.py  # Sunday COT analysis CLI
├── docs/
│   ├── technical_philosophy.yaml  # Core philosophy
│   └── cot_integration.yaml       # COT configuration
├── extensions/
│   └── openbb_treasury/    # OpenBB treasury extension
├── run.sh                  # CLI entry point
└── requirements.txt        # Python dependencies
```

## Configuration

### COT Integration (`docs/cot_integration.yaml`)

```yaml
cot_integration:
  assets:
    BTC: {code: "133741", name: "CME Bitcoin Futures"}
    ETH: {code: "138741", name: "CME Ether Futures"}
  
  risk_management:
    capital_default: 2000
    risk_per_trade_pct: 0.10
    max_leverage: 10
  
  timeframes:
    primary: "4H"
    entry: "1H"
    cot: "1W"
```

## CLI Commands

```bash
# Weekly COT analysis
./run.sh weekly-cot

# OpenBB tools
./run.sh openbb_tools

# Trading (dry run)
./run.sh trading

# Direct Python usage
python -m trading.client summary
python -m trading.client positions --wallet openfang
```

## Environment Variables

```bash
# Optional: OpenBB Hub credentials for extended data
OPENBB_HUB_USERNAME=your_username
OPENBB_HUB_PASSWORD=your_password

# Optional: Custom wallet directory
NAVE_WALLET_DIR=/custom/path
```

## Security

- **Private keys**: Never stored in code or environment variables
- **Encryption**: Fernet (AES-128) with password-derived keys
- **Storage**: `~/.secrets/nave-wallets/` (user home directory)
- **Memory**: Keys loaded only at transaction time, then discarded

## Dependencies

- `openbb>=4.0.0` - Financial data platform
- `hyperliquid-python-sdk>=0.22.0` - Hyperliquid trading
- `cot-reports>=0.4.0` - CME COT data
- `eth-account>=0.11.0` - Ethereum wallet management
- `cryptography>=42.0.0` - Encryption
- `rich>=13.0.0` - Terminal formatting (optional)

## Testing

```bash
# Run weekly analysis in dry-run mode
./run.sh weekly-cot --capital 2000

# Test with plain output
./run.sh weekly-cot --plain

# Verify COT data fetch
python -c "from trading.cot import CotFetcher; print(CotFetcher().latest_btc())"
```

## Troubleshooting

**Import errors**: Ensure you're in the virtual environment with all dependencies installed.

**Wallet not found**: Run wallet setup first: `python -c "from trading.vault import WalletVault; WalletVault().setup_interactive()"`

**COT data unavailable**: The `cot-reports` library fetches from CFTC. Check internet connection or use cached data.

**Hyperliquid connection**: Testnet is default. Use `--mainnet` flag only when ready for live trading.

## License

MIT License - See LICENSE file for details.

## Disclaimer

This software is for educational purposes only. Trading cryptocurrencies carries significant risk. Never trade with money you cannot afford to lose. Always verify signals and understand the strategy before executing trades.
