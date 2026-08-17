# Read-only EVM and Solana wallet audit

NAVE can inspect public wallets without Moralis, paid APIs, private keys, or transaction signing.

## Libraries

- `web3.py` for Ethereum, BNB Chain, and other EVM networks;
- `solana-py` and `solders` for Solana JSON-RPC and public-key types;
- Solana SPL and Token-2022 accounts are discovered through public RPC;
- recent signatures and parsed transaction balance deltas are stored as evidence;

Install the project dependencies inside the local virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## EVM example

```python
from trading.crypto.chain_audit import EvmRpcClient

client = EvmRpcClient("https://bsc-dataseed.binance.org", chain="bsc")
address = "0xPUBLIC_ADDRESS"

if not client.is_connected():
    raise RuntimeError("RPC unavailable")

native = client.get_native_balance(address)
print(native.chain, native.amount)

# Query a known ERC-20 contract when its address is already verified.
# balance = client.get_erc20_balance(address, "0xTOKEN_CONTRACT")
```

EVM JSON-RPC can verify balances, contract metadata, logs, blocks, and transaction
receipts. It does not provide a complete wallet transaction index by address on its
own; transfer history requires scanning logs by block range or an explorer/indexer.

## Solana example

```python
from trading.crypto.chain_audit import SolanaRpcClient

client = SolanaRpcClient("https://api.mainnet-beta.solana.com")
address = "PUBLIC_SOLANA_ADDRESS"

native = client.get_native_balance(address)
print(native.sol)

# Token accounts and signatures are read-only.
# token_accounts = client.get_token_accounts(address)
# signatures = client.get_signatures(address, limit=100)
```

## Safety boundaries

- Wallet addresses are input only; they are not stored by this module.
- No mnemonic, private key, signer, transfer, swap, or transaction submission is
  implemented.
- RPC URLs are configurable so public endpoints can be replaced by a local node.
- ONDO validation remains a separate step using official contracts/metadata and
  on-chain verification.
- Current balances are not fills or cost basis. Reconstructing fills requires
  transaction receipts, token-transfer events, router/DEX events, and gas data.

Public RPCs may rate-limit or omit historical indexing. The adapter should report
RPC failures rather than inventing an empty wallet state.

## CLI

The read-only command accepts a public address and does not write a file unless
`--snapshot-path` is supplied:

```bash
PYTHONPATH=. .venv/bin/python cli/main.py wallet audit \
  --chain bsc \
  0xPUBLIC_EVM_ADDRESS \
  --snapshot-path ~/.hermes/state/chain_audit/bsc.json

PYTHONPATH=. .venv/bin/python cli/main.py wallet audit \
  --chain solana \
  PUBLIC_SOLANA_ADDRESS
```

Supported chains are `ethereum`, `bsc`, and `solana`. RPCs can be overridden
with `--rpc-url`. The CLI never accepts or loads private keys.
