# Options Module

The options module provides equity options analytics with a first implementation focused on MSFT.

## Features

- Full options chain fetch across all expirations via yfinance.
- Liquidity filtering by volume, open interest, and bid/ask spread quality.
- Historical volatility, IV rank/percentile, and put/call skew analytics.
- Greeks enrichment (Delta, Gamma, Theta, Vega) with py_vollib plus fallback.
- Strategy generation and scoring for:
  - Covered Call
  - Cash-Secured Put
  - Iron Condor
  - Butterfly
  - Straddle / Strangle
  - Credit / Debit vertical spreads
- Plotly-first charts with matplotlib fallback:
  - Payoff at expiration
  - Greeks by strike
  - Monte Carlo P/L distribution
- Parquet + sqlite cache under data/options_cache.
- Hermes integration via tool name options_scan.

## Environment Variables

- NAVE_OPTIONS_CACHE_ROOT
- NAVE_OPTIONS_SQLITE_PATH
- NAVE_OPTIONS_MIN_VOLUME
- NAVE_OPTIONS_MIN_OI
- NAVE_OPTIONS_MAX_SPREAD_PCT
- NAVE_OPTIONS_CACHE_TTL_MINUTES
- NAVE_OPTIONS_TIMEOUT_SECONDS
- NAVE_OPTIONS_MAX_RETRIES
- NAVE_OPTIONS_RETRY_BACKOFF_SECONDS
- NAVE_OPTIONS_RISK_FREE_RATE
- NAVE_OPTIONS_DIVIDEND_YIELD
- NAVE_OPTIONS_HV_WINDOW_SHORT
- NAVE_OPTIONS_HV_WINDOW_LONG
- NAVE_OPTIONS_IV_LOOKBACK_DAYS
- NAVE_OPTIONS_MC_PATHS
- NAVE_OPTIONS_MC_SEED
- NAVE_OPTIONS_HISTORY_PERIOD
- NAVE_OPTIONS_ENABLE_PLOTLY
- NAVE_OPTIONS_BULL_PUT_OTM_MIN_PCT
- NAVE_OPTIONS_BULL_PUT_OTM_MAX_PCT
- NAVE_OPTIONS_SPREAD_WIDTH_MIN_POINTS
- NAVE_OPTIONS_SPREAD_WIDTH_MAX_POINTS
- NAVE_OPTIONS_CONSERVATIVE_TOUCH_MAX_PCT
- NAVE_OPTIONS_MODELED_TOUCH_WARNING_PCT

## Quick Start

```bash
python -m options.analyzer
nave options analyze --ticker MSFT --days-to-exp 30 --json
nave hermes call --tool options_scan --args-json '{"ticker":"MSFT","days_to_exp":30}'
```
