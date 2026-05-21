# MSFT options recheck - 2026-05-12 manual bull put spread

## Original analysis

- Source report: `data/options_cache/reports/MSFT_options_report_20260512_201239.json`
- Generated: 2026-05-12 20:12 UTC
- Underlying: MSFT at 407.76
- Structure evaluated: manual bull put credit spread
- Expiration: 2026-06-18
- Legs: sell 395 put at 8.25, buy 390 put at 6.725
- Net credit: 1.525, or 152.50 per 1-lot
- Max loss: 347.50
- Breakeven: 393.475
- Model result: no trade
- Main blockers: negative modeled expected value (-31.19), low composite score (19.50), high path risk / touch risk (75.37%)

## Recheck

- Recheck report: `data/options_cache/reports/MSFT_recheck_20260518_manual_bull_put.json`
- Generated: 2026-05-18 19:00 UTC
- Underlying: MSFT at 420.98
- Same strikes and expiration repriced from the current option chain
- Current leg marks: sell 395 put at 4.425, buy 390 put at 3.50
- Current net credit: 0.925, or 92.50 per 1-lot
- Current max loss: 407.50
- Current breakeven: 394.075
- Current model result: no trade
- Current blockers: negative modeled expected value (-35.21), low composite score (17.95)

## Other MSFT model outputs from last week

The saved MSFT reports from 2026-05-11 and 2026-05-12 contain several auto-ranked outputs:

- 2026-05-11 19:55-20:07 UTC: top auto-ranked structure was an iron condor, but EV was negative around -5.41 and composite score was about 46.13.
- 2026-05-11 21:14-22:36 UTC: top auto-ranked structure was a 410/415/420 call butterfly expiring 2026-06-12. It had positive modeled EV around 25.64, but only about 21.77% PoP and about 98.12% touch risk.
- 2026-05-12 14:30-14:31 UTC: top auto-ranked structure was a long straddle/strangle-style volatility setup expiring 2026-06-05. It had positive modeled EV around 704.34, but required a large move and carried heavy theta burn.
- 2026-05-12 18:28-20:06 UTC: top auto-ranked structure remained long volatility, but the later overlay explicitly marked the scan as no trade.

Current auto scan:

- Recheck report: `data/options_cache/reports/MSFT_recheck_20260518_auto.json`
- Generated: 2026-05-18 19:01 UTC
- Underlying: MSFT at 420.98
- Top current auto-ranked outputs: long strangle, long straddle, call butterfly
- Current decision: no trade
- Reason: no ranked setup passed the executable quality gate, even though long-vol structures still show positive modeled EV.

## Mark-to-market replay from 2026-05-18 chain

Using `data/options_cache/snapshots/MSFT_20260518_190010.parquet`:

| Source | Old top setup | Old spot | Old model read | 2026-05-18 mark |
| --- | --- | ---: | --- | --- |
| `MSFT_options_report_20260511_195551.json` | 2026-06-12 iron condor, 410/395 put side and 410/420 call side | 412.02 | Negative EV (-5.41), no overlay gate in that older report | Exact replay incomplete because today's snapshot is missing the 2026-06-12 410P mark. Available legs show the short 410C became expensive after MSFT rose. |
| `MSFT_options_report_20260511_211408.json` | 2026-06-12 410/415/420 call butterfly | 412.68 | Positive EV (25.64), but low PoP (21.77%) and very high touch risk (98.12%) | About -2.50 per 1-lot using current mids; roughly flat, but uncomfortable path risk played out as spot moved through the body. |
| `MSFT_options_report_20260512_143039.json` | 2026-06-05 long straddle-style volatility setup, 425C + 405P | 407.47 | Positive EV (704.34), score 51.85, high touch risk (91.74%) | About -20.00 per 1-lot using current mids. The call gained, but the put decayed enough to offset most of it. |
| `MSFT_options_report_20260512_200630.json` | 2026-06-12 long straddle, 410C + 410P | 407.76 | Positive EV (298.57), but overlay said no trade | Exact replay incomplete because today's snapshot is missing the 2026-06-12 410P mark. The 410C rose from 12.875 to 21.075, but the missing put mark prevents a clean total P/L. |
| `MSFT_options_report_20260512_200630.json` | 2026-06-12 385/375 bull put credit spread | 407.76 | Negative EV (-52.16), score 20.08, overlay said no trade | Exact replay incomplete because today's snapshot is missing the 2026-06-12 375P mark. The short 385P compressed from 4.65 to 2.15, directionally favorable. |
| `MSFT_options_report_20260512_201239.json` | 2026-06-18 395/390 manual bull put credit spread | 407.76 | Negative EV (-31.19), score 19.50, overlay said no trade | About +60.00 per 1-lot using current mids. Credit compressed from 1.525 to 0.925. |

## Read

The directional idea has worked so far because MSFT moved from 407.76 to 420.98 and remained above the 395 short put. That does not mean the original spread was a good executable trade. The model correctly separated directional comfort from option-structure quality: the spread was positive so far only because spot moved favorably, while the original entry still had negative modeled EV and high probability of touch.

At the recheck, the spread is safer on distance-to-short-strike, but the entry is no longer attractive because the available credit has compressed from 1.525 to 0.925. The same 5-point-wide spread now pays less premium for more remaining max loss, and the model still rejects it.

## Model improvement note

Add an explicit post-analysis label for rejected-but-directionally-correct candidates:

- `directional_thesis_outcome`: whether spot moved in the expected direction after the report.
- `structure_outcome`: whether the option structure improved on EV, credit-to-width, touch risk, and executable score.
- `decision_quality`: whether the original no-trade/pass decision remains valid despite the later spot move.

This prevents a common review error: upgrading the model because a rejected bullish spread would look good after a bullish move. The better lesson is to preserve the no-trade gate unless a post-trade replay shows that the EV or risk filters were systematically too strict across many similar cases.
