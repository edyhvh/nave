# ETH Weekly Options Strategy - COT + Momentum

Date: 2026-06-08

## Scope

This note defines a first-pass ETH weekly options strategy for a small account
using the existing nave COT + momentum framework.

Important limitation: the repository has historical ETH COT/momentum backtests,
but it does not have multi-year historical Deribit option-chain snapshots. The
rules below are therefore based on ETH underlying signal follow-through and must
be paired with live option-chain execution filters before any trade is valid.

## Evidence Reviewed

Latest ETHUSDT slices from the persisted momentum artifacts in
`docs/analysis/raw/momentum_backtest_*.json`:

| Period | Trades | Win rate | Expectancy | Avg move | Reached 8% | Reached 12% | Read-through for weekly options |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2017-bull+2018-bear | 8 | 100.0% | 2.77R | 8.96% | 100.0% | 75.0% | Strong gamma regime |
| 2019-recovery | 14 | 71.4% | 1.40R | 5.13% | 78.6% | 14.3% | Directional, but spreads preferred |
| 2020-covid-crash | 9 | 88.9% | 2.61R | 7.22% | 77.8% | 11.1% | Debit spreads preferred after crash volatility |
| 2020-recovery+2021-ATH | 13 | 92.3% | 2.53R | 7.87% | 84.6% | 23.1% | Strong directional spread regime |
| 2022-bear | 8 | 100.0% | 3.41R | 11.41% | 87.5% | 25.0% | Best put-spread / put-gamma regime |
| 2023-recovery | 17 | 64.7% | 1.13R | 2.88% | 29.4% | 11.8% | Avoid long weekly premium unless exceptional |
| 2024-ETF-approval | 6 | 50.0% | 0.55R | 2.32% | 33.3% | 0.0% | No-trade or very tight debit spread only |
| 2024-2025-bull | 6 | 83.3% | 1.82R | 6.44% | 66.7% | 33.3% | Selective directional spreads |
| TODAY artifact | 2 | 100.0% | 2.75R | 10.27% | 100.0% | 100.0% | Live window only; not standalone validation |

Across these artifacts, the best ETH options candidates are not merely "winning"
spot/perp signals. They are signals with enough fast follow-through to overcome
weekly option decay and spread cost. The weak regimes are 2023 recovery and the
2024 ETF-approval window: the strategy was still positive in R, but 8% extension
was too rare for consistent long weekly premium.

## Weekly Decision Stack

Run this stack once after the weekly close and then re-check on any 4H/1H entry
trigger during the week:

1. COT permission:
   - COT must not conflict with the intended side.
   - Extreme crowded positioning blocks new entries unless the trade is a clear
     contrarian squeeze setup and momentum confirms.
   - COT is context, not an entry.
2. Weekly momentum:
   - Weekly velocity must exceed the nave threshold in the intended direction,
     or a valid range-breakout bias must be active.
   - Neutral weekly bias blocks swing-style weekly options.
3. Daily confirmation:
   - Daily trend must align with the weekly side.
   - If daily contradicts weekly, no weekly option trade.
4. 4H setup:
   - Price must be in a nave confluence/retest zone.
   - Do not chase the impulse; the option trade is entered on the post-momentum
     pullback or breakout retest.
5. 1H trigger:
   - A 1H trigger must fire inside the 4H zone.
   - No 1H-only trades.

## Strategy Rules

### Account Risk

For a USD 1,000 account:

- Base max loss per trade: USD 10-20.
- Absolute max loss for an A+ setup: USD 30, but anything above the base cap
  requires manual review and should not auto-enter from the CLI.
- Weekly loss cap: USD 20, or one failed trade.
- Monthly loss cap: 6% of account equity.
- No naked short options.
- No averaging down on premium.

### Expiration

Target 7-14 DTE at entry.

Do not enter new weekly options with less than 5 DTE unless the 1H trigger has
already fired and the premium paid is small enough to treat as a tactical loss.
Prefer 10-14 DTE when IV is high or the setup needs a 4H retest to develop.

### Structure Selection

Use the underlying follow-through regime to choose the option expression:

| ETH regime condition | Preferred option expression | Reason |
| --- | --- | --- |
| Reached-8% profile strong, 1H trigger clean, confidence >= 90 | Long call or long put, small size | Gamma can pay because ETH historically extends fast enough |
| Directional signal valid but 12% follow-through is uncommon | Bull call debit spread or bear put debit spread | Reduces theta and IV overpayment |
| Event / high-IV week, but direction valid | Debit spread only | Do not overpay for outright weekly premium |
| 8% follow-through profile weak, confidence < 90, or daily is choppy | No trade | Positive perp R is not enough for weekly options |
| Short-premium idea | Defined-risk spread only, max loss <= account risk cap | Naked short options are incompatible with this account size |

### Strike Selection

For debit spreads:

- Long leg: near the 1H trigger or slightly ITM if affordable.
- Short leg: near TP1 or the next 4H confluence target.
- Max debit must be within the account risk cap.
- Skip if bid/ask spread is too wide or the spread width implies poor max reward.

For outright long options:

- Use only when the historical regime and current setup imply fast movement.
- Premium paid is the stop.
- Prefer strikes close enough that a move to TP1 can plausibly produce at least
  1.5R after fees and spread.

For credit spreads:

- Use only when live chain pricing allows max loss within USD 10-30.
- Short strike must sit beyond the 4H invalidation zone, not merely OTM by a
  fixed percent.
- Close at 40-60% of max credit.
- Exit immediately if ETH closes beyond the 4H invalidation level.

## Entry And Management

Entry:

- Enter only after the 1H trigger closes.
- If the trigger occurs late Friday or with less than 5 DTE, skip unless the
  premium is tiny and the move is already in progress.
- If the option market is illiquid, skip even when the underlying signal is good.

Profit taking:

- Debit spread: take profit at 50-70% of max spread value, or at underlying TP1.
- Outright long option: take partial or full profit at 1.5R-2R, or when ETH tags
  TP1. Do not hold a winning weekly option for a distant TP2 if theta is rising.
- Credit spread: close at 40-60% of max credit.

Stops:

- Long premium: premium paid is max loss; optionally cut at 50% loss if the 1H
  trigger fails quickly.
- Debit spread: close if ETH invalidates the 4H setup.
- Credit spread: close on 4H invalidation; do not wait for the short strike.

Time stop:

- If ETH has not moved toward TP1 within 24-36 hours after entry, exit or reduce.
- Do not carry decaying weeklies through a stale 4H setup.

## Weekly Playbook

1. Weekend / Monday:
   - Run COT + momentum scan for ETH.
   - If weekly/daily are not aligned, mark no-trade.
2. During the week:
   - Watch only the active 4H zone.
   - Wait for the 1H trigger.
3. At trigger:
   - Pull the live Deribit chain.
   - Evaluate 7-14 DTE debit spread first.
   - Consider outright long option only in strong follow-through regimes.
4. After entry:
   - Manage to TP1, 1.5R-2R, or time stop.
   - Stop trading for the week after one full-risk loss.

## Current Implementation Fit

The existing code already supports most of the scan path:

- `options/fetchers/deribit_fetcher.py` fetches Deribit BTC/ETH option chains.
- `OptionsAnalyzer.scan_crypto_opportunities()` gates options analysis with
  momentum first.
- `trading/crypto/momentum/defaults.json` already uses COT overlay and a high
  score threshold.

Recommended executable refinement:

- Add an ETH weekly-options profile that defaults to:
  - `coins=ETH`
  - `days_to_exp=10`
  - `account_equity=1000`
  - `risk_pct=0.01`
  - `score_threshold=90`
  - `require_tradeable=true`
- Add a small-account options guard:
  - reject candidates whose max loss exceeds USD 20 by default,
  - mark A+ candidates between USD 20-30 for manual review rather than auto-entry,
  - reject outright long premium above USD 20 unless manually overridden,
  - prefer debit spreads over naked long weekly options in weak extension regimes.

## First-Pass Conclusion

Yes, ETH weekly options can be integrated with nave, but the solid version is
selective:

- Trade ETH only when COT permits, weekly/daily align, 4H setup is active, and
  1H trigger fires.
- Use a 90+ momentum confidence threshold for weekly options.
- Use debit spreads as the default expression.
- Use outright long calls/puts only in high follow-through regimes.
- Avoid 2023-style slow recovery/chop weeks for long premium.
- Keep risk small enough that one bad week does not damage the account.
