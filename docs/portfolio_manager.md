# Long-term portfolio manager

## Purpose

`nave stocks portfolio-review` is the first structural layer for a small,
long-term portfolio executed manually through ONDO. It produces a ranked
`enter/watch/review` list and a staged monthly allocation. It is intentionally
**human-gated**: Nave does not place orders, custody funds, or claim that a
candidate is investable without current evidence.

The portfolio is systematic in process, not rigid in outcome. The policy must
be reviewed when evidence quality, execution venue, or observed results reveal
that a rule is failing.

## Decision contract

Every candidate is normalised into these evidence lanes:

1. **ISM** — manufacturing/services ranking and the mapped company thesis.
2. **Congress** — STOCK Act disclosure, with instrument, transaction date,
   filing lag, and amount range preserved. It is a delayed contextual signal,
   never a standalone entry.
3. **Technical** — current price, entry zone, trend/structure confirmation,
   invalidation, and risk/reward.
4. **Reserve AI** — a Reserve index is treated as a research allocation/catalyst
   input only after its methodology, constituents, pricing, liquidity, and
   fees are fetched and timestamped. No index is hardcoded into the engine.
5. **Social** — supporting context, not fundamental truth.
6. **ONDO** — availability and liquidity are separate booleans. The research
   universe is not proof of a live executable market.

The score is weighted toward ISM and technical confirmation. Missing or weak
ONDO evidence reduces the score. Social sentiment cannot compensate for a
missing technical setup.

## Monthly cadence

The funding date is the 26th. `monthly_review_date` moves it to the next
weekday when the 26th is a weekend; it does not force a purchase. On or after
that date, the manager should:

1. snapshot current positions and cash;
2. refresh ISM, congress, ONDO, technical and Reserve evidence;
3. review existing positions first (`broken`/`invalidated` thesis is an exit
   prompt; drawdowns and large gains are review prompts);
4. rank new candidates and reject stale or incomplete evidence;
5. allocate at most 85% of the monthly budget, keeping 15% as reserve;
6. stage entries and wait when price is outside the validated entry zone;
7. record the user's actual execution, price, fee, and date in the journal.

For a $300 budget, the default reserve is $45. The remaining $255 is subject
to the single-position cap and the number of validated candidates. These are
risk controls, not return promises.

## Exit and review discipline

- **EXIT prompt:** thesis explicitly broken or invalidated. The human confirms
  the order after checking current facts.
- **REVIEW prompt:** loss reaches the configured drawdown threshold, gain reaches
  the profit-review threshold, or technical evidence weakens.
- **HOLD:** no exit/review condition is present and the thesis remains active.
- **WATCH:** score is not sufficient for a new allocation, or price has not
  reached the entry zone.

No rule uses an arbitrary "sell because it went up" or "average down because it
fell" instruction. The manager must distinguish price movement from thesis
failure.

## CLI example

```bash
PYTHONPATH=. python cli/main.py stocks portfolio-review \
  --monthly-budget 300 \
  --candidates-json '[
    {"ticker":"NVDA","evidence":{"ism_score":0.8,"technical_score":0.9,
      "reserve_ai_score":0.7,"ondo_available":true,"ondo_liquid":true}},
    {"ticker":"TSLA","evidence":{"ism_score":0.5,"technical_score":0.3,
      "ondo_available":true,"ondo_liquid":true}}
  ]' --json
```

This command only emits a dry-run plan. Provider adapters and a position
snapshot/journal integration are follow-up work for subsequent PRs; they must
be implemented with current-data tests and explicit read-back verification.

## Wallet scope

The ETH and SOL addresses supplied by the operator are execution context for
future ONDO adapters, not secrets and not authorization to transact. This PR
does not read from or write to either wallet.
