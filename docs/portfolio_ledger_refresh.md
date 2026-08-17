# Portfolio ledger refresh

`trading/stocks/portfolio_ledger.py` is the read-only, idempotent Solana
refresh. `scripts/portfolio_ledger_refresh.py` is a thin CLI over that module.

## Behavior

- Reads the public Solana wallet address from `~/.hermes/state/portfolio_manager/portfolio.json`.
- Discovers SPL and Token-2022 ONDO accounts, including unmapped `*ondo` mints.
- Uses account signatures and parsed transaction token balance deltas as evidence.
- Deduplicates fills by canonical signature + mint + side, and by mint/side/qty/time.
- Attributes USDC only when exactly one ONDO mint moved in the transaction.
- Requires that ONDO + USDC pair for `confirmed_on_chain` cost evidence.
- Keeps unknown mints and unattributed cash events as `pending_review`.
- Updates quantities on existing book names only; it does not create positions or overwrite `thesis_status`.
- Stores remaining `cost_basis_usd` as average-cost of residual lots after sales.
- Rejects an empty token-account set when the book already has positions.
- Writes audit and portfolio state atomically outside Git.
- Uses public RPC fallback endpoints and records redacted RPC errors without fabricating fills.

It never signs, submits, buys, sells, or transfers funds.

## Manual verification

From the repository root:

```bash
.venv/bin/python scripts/portfolio_ledger_refresh.py
```

The same command can be repeated safely; a second run should report `new_fill_count: 0` when no new transactions exist.
