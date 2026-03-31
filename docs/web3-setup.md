# Web3 Setup — Wallets & Hyperliquid

## Architecture

```
nave/
├── scripts/
│   ├── wallet_vault.py        # Encrypted wallet storage
│   ├── setup_wallets.py       # One-time wallet generator
│   ├── show_mnemonic.py       # Safely reveal seed phrase for Phantom import
│   └── hyperliquid_client.py  # Hyperliquid trading API wrapper
└── docs/
    └── web3-setup.md          # This file
```

Wallet secrets live exclusively in `~/.secrets/nave-wallets/` — never in the repo.

## Wallets

Two EVM wallets (BIP39, 24-word, HD path `m/44'/60'/0'/0/0`):

| Wallet | Purpose | Address |
|--------|---------|---------|
| `ironclaw` | IronClaw executor | `0x3fB31b355b82B6B1421dBb914364c0Ec5e72868F` |
| `openfang` | OpenFang executor | `0x48b6cB6ea38D48304B5bc634294be4F0EFC52b51` |

Both wallets are EVM-compatible (Ethereum, Hyperliquid, Polygon, etc.) and can also be imported into Phantom for Solana by choosing the Ethereum account type.

### Vault storage

```
~/.secrets/nave-wallets/
├── .vault_key      # Fernet encryption key (chmod 400)
├── ironclaw.enc    # Encrypted wallet data (chmod 600)
└── openfang.enc    # Encrypted wallet data (chmod 600)
```

### Commands

```bash
# List all wallets and their public addresses
cd ~/nave && .venv/bin/python scripts/wallet_vault.py list

# Show seed phrase for Phantom import (use in private terminal only)
.venv/bin/python scripts/show_mnemonic.py ironclaw
.venv/bin/python scripts/show_mnemonic.py openfang
```

## Importing into Phantom

1. Open Phantom browser extension → **Add/Connect Wallet** → **Import Wallet**
2. Choose **Ethereum** (for Hyperliquid) or **Solana**
3. Run `show_mnemonic.py <name>` in a private terminal to see the 24-word phrase
4. Type the words into Phantom — **do not paste** on shared systems
5. The terminal auto-clears after 60 seconds

## Hyperliquid Paper Trading

### Setup

```bash
cd ~/nave
.venv/bin/pip install hyperliquid-python eth-account
```

### Usage

```python
from scripts.hyperliquid_client import HyperliquidClient

# Always start on testnet
client = HyperliquidClient(wallet_name="openfang", testnet=True)
client.summary()

# Check prices
mids = client.get_all_mids()

# Open a $100 long on ETH (testnet paper trading)
client.market_open("ETH", side="long", size_usd=100)

# View positions
client.get_open_positions()

# Close position
client.market_close("ETH")
```

### CLI

```bash
.venv/bin/python scripts/hyperliquid_client.py --wallet openfang summary
.venv/bin/python scripts/hyperliquid_client.py --wallet openfang positions
.venv/bin/python scripts/hyperliquid_client.py mids
```

### Testnet funding

Get testnet USDC from the Hyperliquid testnet faucet:
https://app.hyperliquid-testnet.xyz/

Connect with your wallet address, request test funds.

## Phantom MCP (openfang integration)

Phantom MCP lets openfang agents interact with the wallet via natural language.

### Setup

1. Get an App ID from https://phantom.com/portal (create an app)
2. Add `PHANTOM_APP_ID` to `~/.openfang/.env`
3. Uncomment the `[[mcp_servers]]` block in `~/.openfang/config.toml`
4. Restart openfang: `systemctl restart openfang`

The MCP server handles SSO login via browser and persists the session at `~/.phantom-mcp/session.json`.

## Security Rules

- **Never** commit `.enc` files, `.vault_key`, or anything from `~/.secrets/`
- **Never** print or log private keys — use `vault.address()` for display
- **Never** store seed phrases in plaintext anywhere
- Vault key (`~/.secrets/nave-wallets/.vault_key`) should be backed up securely offline
- Rotate wallets if any key material is ever suspected to be exposed
