-- Purpose: bounded realized-PnL and temporal-leakage audit on a small wallet
-- sample. It is a reproducibility template, not an executed query in this run.
-- PnL must use observed token/quote quantities and Dune fee fields where
-- available; open inventory is never marked as realized profit.
-- Point-in-time profiles must filter outcome_ts < cutoff_ts and require the
-- outcome horizon to have matured before the cutoff.

-- The next execution should select 10 wallets across several tokens from the
-- already materialized participant episode panel, then join only their
-- pre-cutoff trade events. Do not use current balances or current prices.
