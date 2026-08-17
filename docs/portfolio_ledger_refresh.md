# Portfolio ledger refresh

`trading/stocks/portfolio_ledger.py` is the read-only, idempotent Solana
refresh. `scripts/portfolio_ledger_refresh.py` is a thin CLI over that module.

## Behavior

- Reads the public Solana wallet address from `~/.hermes/state/portfolio_manager/portfolio.json`.
- Discovers SPL and Token-2022 ONDO accounts, including unmapped `*ondo` mints.
- Uses wallet/account signatures and parsed transaction token balance deltas as evidence.
- Deduplicates by canonical signature + mint + side. The economic fallback is
  limited to a long truncated signature that is a prefix of its canonical RPC signature.
- Attributes USDC only when exactly one ONDO mint moved and the cash direction
  opposes the ONDO direction.
- Requires that ONDO + USDC pair for `confirmed_on_chain` cost evidence.
- Keeps unknown mints and unattributed cash events as `pending_review`.
- Updates quantities on existing book names only; it does not create positions or overwrite `thesis_status`.
- Stores remaining `cost_basis_usd` as average-cost of residual lots after sales.
- Requires two RPC endpoints to agree before accepting a completely empty
  token-account inventory, and zeroes absent known positions after a trusted snapshot.
- Marks cost basis `incomplete_history` whenever signature or transaction history
  could not be read completely.
- Writes audit and portfolio state atomically outside Git.
- Uses public RPC fallback endpoints and records redacted RPC errors without fabricating fills.

It never signs, submits, buys, sells, or transfers funds.

## Manual verification

From the repository root:

```bash
.venv/bin/python scripts/portfolio_ledger_refresh.py
```

The same command can be repeated safely; a second run should report `new_fill_count: 0` when no new transactions exist.
