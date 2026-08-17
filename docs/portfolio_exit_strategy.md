# Portfolio exit and monitoring policy

The Portfolio Manager is human-gated. It never places orders and never treats a
single price drop as an automatic exit.

## Decision levels

- `HOLD`: normal volatility, intact trend, and no material thesis change.
- `REVIEW`: deterioration that deserves a human decision, such as a close below
  SMA50 while the position is down at least 5%, an accelerating five-day decline,
  or a profitable position losing its short-term trend after a meaningful run.
- `EXIT`: only after thesis invalidation, a confirmed structural risk, or a
  previously agreed protection/invalidation level. The assistant explains the
  evidence and waits for Joni's manual execution.

## What a price review checks

Twice each weekday at 10:00 and 16:00 America/Argentina/Buenos_Aires, the local
read-only monitor checks:

- current price;
- SMA20 and SMA50;
- 20-session high/low;
- ATR14;
- five-session return;
- residual cost basis and position return.

The worker is silent when there is no new material condition. It deduplicates an
unchanged condition and reports infrastructure failures separately from no-change.

## Preventing missed exit windows

For each position the monitor should maintain an evidence trail:

1. thesis and invalidation level;
2. entry and residual cost basis;
3. high-water mark after entry;
4. technical trend state;
5. `HOLD`, `REVIEW`, or `EXIT` transitions;
6. the last alert and the reason it changed.

A winning position can therefore generate a `REVIEW` when it loses short-term
trend, without forcing a sale. A losing position can remain `HOLD` when the thesis
is intact, and can become `EXIT` only when the thesis or agreed invalidation is
broken.

## New entries and waiting targets

The 26th is a review reference, not a mandatory purchase date. When price is too
extended, the decision is `WATCH` with a concrete target zone and re-check schedule.
A target alert means "review the setup now", not "place an order".

## Restricted universe

Direct war, weapons, military, and defense exposure is excluded from new entries.
Indirect exposure is reviewed case by case and must be explicitly classified before
allocation. A restricted candidate is never allocated and is reported as
`direct_defense_excluded`.
