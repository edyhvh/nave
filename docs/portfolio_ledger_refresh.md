# Portfolio ledger refresh

`/scripts/portfolio_ledger_refresh.py` is a read-only, idempotent Solana refresh for the local human-gated portfolio state.

## Behavior

- Reads the public Solana wallet address from `~/.hermes/state/portfolio_manager/portfolio.json`.
- Discovers SPL and Token-2022 ONDO accounts.
- Uses account signatures and parsed token balance deltas as evidence.
- Records a fill only once, keyed by `signature + mint + side`.
- Requires an ONDO delta and a matching USDC delta for `confirmed_on_chain` cost evidence.
- Keeps events with missing economic payment evidence as `pending_review`.
- Updates current quantities and provisional net cash flow after sales.
- Writes audit and portfolio state atomically outside Git.
- Uses public RPC fallback endpoints and records RPC errors without fabricating fills.

It never signs, submits, buys, sells, or transfers funds.

## Manual verification

From the repository root:

```bash
.venv/bin/python scripts/portfolio_ledger_refresh.py
```

The same command can be repeated safely; a second run should report `new_fill_count: 0` when no new transactions exist.
