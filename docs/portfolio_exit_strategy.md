# Portfolio exit and monitoring policy

The Portfolio Manager is human-gated. It never places orders and never treats a
single price drop as an automatic exit.

## Decision levels

- `HOLD`: normal volatility, intact trend, and no material thesis change.
- `REVIEW`: deterioration that deserves a human decision, such as a close below
  SMA50 while the position is down at least 5%, an accelerating five-day decline,
  or a profitable position losing its short-term trend after a meaningful run.
- `REVIEW` with `profit_taking_window`: the position is profitable, close to its
  recent high, and technically extended. This is a prompt to consider selling a
  portion and withdrawing gains while keeping a core position.
- `EXIT`: only after thesis invalidation, a confirmed structural risk, or a
  previously agreed protection/invalidation level. The assistant explains the
  evidence and waits for Joni's manual execution.

## What a price review checks

The portfolio monitor may run every 30 minutes, including weekends, but remains silent during the seasonal Buenos Aires Shabbat pause. It never places orders.

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
trend, without forcing a sale. A losing position can remain `HOLD` when the
thesis is intact, and can become `EXIT` only when the thesis or agreed invalidation
is broken.

## Profit-taking framework

Profit-taking is separate from damage control. The default review ladder is:

1. Around +12% with price near a 20-session high and extended above SMA20:
   consider a partial sale, generally 25–33%, after reviewing the thesis and
   liquidity.
2. Around +20–30% or after another confirmed extension: consider another partial
   sale or move part of the proceeds to cash/reserve.
3. Keep a core position while the thesis and trend remain healthy.
4. Exit the remainder only on thesis invalidation, structural deterioration, or
   an agreed trailing/invalidation rule.

These are review thresholds, not orders. The actual percentage and execution are
approved and performed manually by Joni.

## New entries and waiting targets

The 26th is a review reference, not a mandatory purchase date. When price is too
extended, the decision is `WATCH` with a concrete target zone and re-check schedule.
A target alert means "review the setup now", not "place an order".

## Restricted universe

Direct war, weapons, military, and defense exposure is excluded from new entries.
Indirect exposure is reviewed case by case and must be explicitly classified before
allocation. A restricted candidate is never allocated and is reported as
`direct_defense_excluded`.
