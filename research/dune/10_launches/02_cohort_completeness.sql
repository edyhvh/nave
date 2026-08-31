-- Purpose: exact denominator and lifecycle coverage for the selected 24-hour
-- launch cohort. Period is 2026-08-27 UTC; look-ahead ends 2026-08-30 UTC.
-- This query returns one compact row and never selects raw trades.

WITH launches AS (
    SELECT mint, MIN(evt_block_time) AS launch_ts, MAX_BY(creator, evt_block_time) AS creator,
           MAX_BY(quote_mint, evt_block_time) AS quote_mint,
           MAX_BY(token_total_supply, evt_block_time) AS token_total_supply,
           MAX_BY(is_mayhem_mode, evt_block_time) AS is_mayhem_mode,
           MAX_BY(is_cashback_enabled, evt_block_time) AS is_cashback_enabled,
           MAX_BY(token_program, evt_block_time) AS token_program
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND evt_block_time < TIMESTAMP '2026-08-28 00:00:00 UTC'
    GROUP BY mint
), completes AS (
    SELECT DISTINCT mint
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND evt_block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
), migrations AS (
    SELECT DISTINCT account_mint AS mint
    FROM pumpdotfun_solana.pump_call_migrate
    WHERE call_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND call_block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
), pump_trades AS (
    SELECT DISTINCT t.mint
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN launches l ON l.mint = t.mint
    WHERE t.evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND t.evt_block_time < TIMESTAMP '2026-08-30 00:00:00 UTC'
      AND t.evt_block_time >= l.launch_ts
), pumpswap AS (
    SELECT DISTINCT CASE WHEN token_bought_mint_address = 'So11111111111111111111111111111111111111112'
                         THEN token_sold_mint_address ELSE token_bought_mint_address END AS mint
    FROM dex_solana.trades
    WHERE block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
      AND project = 'pumpswap'
), joined AS (
    SELECT l.*, c.mint IS NOT NULL AS graduated, m.mint IS NOT NULL AS migrated,
           pt.mint IS NOT NULL AS has_pump_trades, ps.mint IS NOT NULL AS has_pumpswap
    FROM launches l
    LEFT JOIN completes c ON c.mint = l.mint
    LEFT JOIN migrations m ON m.mint = l.mint
    LEFT JOIN pump_trades pt ON pt.mint = l.mint
    LEFT JOIN pumpswap ps ON ps.mint = l.mint
)
SELECT
    COUNT(*) AS launch_count,
    COUNT_IF(launch_ts IS NOT NULL) AS tokens_with_valid_launch_time,
    COUNT_IF(creator IS NOT NULL) AS tokens_with_creator,
    COUNT_IF(quote_mint IS NOT NULL) AS tokens_with_quote_asset,
    COUNT_IF(token_total_supply IS NOT NULL) AS tokens_with_supply,
    COUNT_IF(token_program IS NOT NULL) AS tokens_with_token_program,
    COUNT_IF(graduated) AS tokens_graduated,
    COUNT_IF(migrated) AS tokens_with_migration,
    COUNT_IF(graduated AND migrated) AS graduated_and_migrated,
    COUNT_IF(has_pump_trades) AS tokens_with_pumpfun_trades,
    COUNT_IF(has_pumpswap) AS tokens_with_pumpswap_trades,
    COUNT_IF(graduated AND migrated AND has_pumpswap) AS graduated_tokens_followed_into_pumpswap,
    COUNT_IF(is_mayhem_mode IS NOT NULL) AS tokens_with_mayhem_state,
    COUNT_IF(is_cashback_enabled IS NOT NULL) AS tokens_with_cashback_state
FROM joined
