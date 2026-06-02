# Web3 & Trading Setup

This document covers the wallet setup and Hyperliquid integration for nave's
automated trading strategies.

## Architecture

```
nave/
├── trading/                  ← Python package (import from here)
│   ├── vault.py              ← Encrypted wallet storage (Fernet/AES)
│   ├── client.py             ← Hyperliquid REST + SDK client
│   ├── signals.py            ← Signal types and aggregation
│   └── strategy.py           ← BaseStrategy + example strategy
└── scripts/
    ├── setup_wallets.py      ← One-time wallet generation
    └── show_mnemonic.py      ← Reveal seed phrase (for cold storage backup)
```

```
                    ┌──────────────────────────────┐
    Macro signals   │  nave / OpenBB data scripts  │
    (RRP, AAII,     └──────────────┬───────────────┘
     VIX, ETF flows)               │ indicators dict
                                   ▼
                    ┌──────────────────────────────┐
                    │   trading/signals.py          │
                    │   MacroSignalProducer         │
                    │   SignalAggregator            │
                    └──────────────┬───────────────┘
                                   │ list[Signal]
                                   ▼
                    ┌──────────────────────────────┐
                    │   trading/strategy.py         │
                    │   BaseStrategy.execute()      │
                    └──────────────┬───────────────┘
                                   │ market_open / market_close
                                   ▼
                    ┌──────────────────────────────┐
                    │   trading/client.py           │  ← signs with eth-account
                    │   HyperliquidClient           │  ← no MetaMask needed
                    └──────────────┬───────────────┘
                                   │ signed JSON-RPC
                                   ▼
                       Hyperliquid testnet / mainnet
```

**No MetaMask, no browser automation.** The private key is loaded from the
encrypted vault at signing time and discarded immediately after. All trading
is server-side via the Hyperliquid Python SDK.

---

## Wallet Setup

> ⚠️ Run setup once per environment. If wallets already exist, the script skips them.

```bash
cd ~/nave
direnv allow  # preferred; enables plain `python` and `pip` in this repo
# or fallback: source .venv/bin/activate
python scripts/setup_wallets.py
```

This generates two EVM wallets — `ironclaw` and `openfang` — using 24-word
BIP39 mnemonics derived via `m/44'/60'/0'/0/0`. They are stored **encrypted**
at `~/.secrets/nave-wallets/` and **never committed to git**.

### Vault files (local only, never in git)

| File | Permissions | Contents |
|------|-------------|----------|
| `~/.secrets/nave-wallets/.vault_key` | `400` | Fernet encryption key — back up offline |
| `~/.secrets/nave-wallets/ironclaw.enc` | `600` | Encrypted wallet data |
| `~/.secrets/nave-wallets/openfang.enc` | `600` | Encrypted wallet data |

### Viewing wallet addresses (safe)

```bash
python scripts/wallet_vault.py list
```

### Revealing seed phrase (for cold storage / hardware wallet import)

```bash
python scripts/show_mnemonic.py openfang
```

> Displays the 24-word phrase for 60 seconds, then clears the terminal.
> Only run in a private terminal session. Never pipe to a file or log.

---

## Hyperliquid Client

### Paper trading (testnet)

```python
from trading import HyperliquidClient

client = HyperliquidClient("openfang", testnet=True)
client.summary()                            # print account state
client.get_markets()                        # list all perp markets
client.get_mid("ETH")                       # current ETH mid price
client.market_open("ETH", "long", 50.0)    # open $50 long (paper)
client.market_close("ETH")                 # close position
```

### CLI shortcuts

```bash
# Account summary
python -m trading.crypto.client summary --wallet openfang

# Live prices
python -m trading.crypto.client mids --wallet openfang

# Open positions
python -m trading.crypto.client positions --wallet openfang
```

### Testnet vs mainnet

| | Testnet | Mainnet |
|--|---------|---------|
| URL | `api.hyperliquid-testnet.xyz` | `api.hyperliquid.xyz` |
| Funds | Mock USDC (requires testnet deposit) | Real funds |
| Default | ✅ Yes | ❌ No — pass `testnet=False` |

> **Never set `testnet=False` unless you have confirmed the strategy is
> profitable on testnet and you accept the risk of real losses.**

---

## Signals & Strategy

### Running the example strategy (dry-run)

```bash
python -m trading.crypto.strategy --wallet openfang --coins BTC ETH --max-usd 50
```

Output shows computed signals and what orders *would* be placed. No orders are
submitted in dry-run mode.

### Implementing a real strategy

```python
from trading import HyperliquidClient, BaseStrategy, Signal, Direction

class MyStrategy(BaseStrategy):
    def compute_signals(self) -> list[Signal]:
        # Pull data from nave's OpenBB scripts:
        # from scripts.openbb_tools import ...
        return [
            Signal(coin="BTC", direction=Direction.LONG, confidence=0.8, source="macro/rrp"),
        ]

client = HyperliquidClient("openfang", testnet=True)
strategy = MyStrategy(client, max_position_usd=100, dry_run=True)
strategy.run_once()
```

### Signal sources (nave indicators)

| Indicator | Signal logic |
|-----------|-------------|
| RRP weekly change | Rising RRP drains liquidity → SHORT |
| AAII sentiment | Extreme bearishness → contrarian LONG |
| VIX spike (>25) | Risk-off → CLOSE positions |
| BTC ETF net flows | (TODO) Positive flows → LONG BTC |

See `trading/signals.py` → `MacroSignalProducer` for implementation.

---

## Funding a testnet wallet

Hyperliquid testnet requires a small mainnet deposit to unlock the faucet
(`/drip`). Options:

1. **Mainnet first**: deposit ~$10 USDC on HL mainnet with the same wallet
   address, then claim 1000 mock USDC on testnet.
2. **Bridge from another chain**: send USDC via Arbitrum or Base bridge.
3. **Request from team**: for internal testing, reach out to the HL team.

Wallet addresses:
- `ironclaw`:  `0x3fB31b355b82B6B1421dBb914364c0Ec5e72868F`
- `openfang`:  `0x48b6cB6ea38D48304B5bc634294be4F0EFC52b51`

---

## Security rules

- 🔒 Private keys are **never** stored in env vars, config files, or git.
- 🔒 The vault key (`~/.secrets/nave-wallets/.vault_key`) must be backed up
  **offline** (e.g. password manager or USB). If lost, wallets cannot be recovered
  from the `.enc` files.
- 🔒 Seed phrases shown by `show_mnemonic.py` should only be viewed in a
  private terminal session. Auto-clears after 60 seconds.
- 🔒 `testnet=True` is the default. Live trading requires an explicit opt-in.
