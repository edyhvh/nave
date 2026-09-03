-- Purpose: one-token end-to-end proof for mint 7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump.
-- Bounds: launch through launch + 72 hours; only selected columns are returned.
-- This is a small raw-event proof. The cohort queries aggregate before transfer.

WITH sol_marks AS (
    SELECT minute, MAX(price) AS sol_usd
    FROM prices.usd
    WHERE minute >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND minute < TIMESTAMP '2026-08-30 00:00:00 UTC'
      AND blockchain = 'solana'
      AND symbol = 'SOL'
    GROUP BY minute
), lifecycle AS (
    SELECT
        mint,
        evt_block_time AS event_time,
        evt_block_slot AS block_slot,
        evt_tx_id AS tx_id,
        evt_tx_index AS tx_index,
        evt_outer_instruction_index AS outer_instruction_index,
        evt_inner_instruction_index AS inner_instruction_index,
        'CREATE' AS event_type,
        'pumpfun' AS venue,
        CAST(user AS varchar) AS wallet,
        CAST(NULL AS varchar) AS side,
        CAST(NULL AS double) AS token_amount,
        CAST(NULL AS double) AS quote_amount_sol,
        CAST(NULL AS double) AS price_sol,
        CAST(NULL AS double) AS price_usd,
        CAST(NULL AS double) AS virtual_token_reserves,
        CAST(NULL AS double) AS virtual_quote_reserves,
        CAST(NULL AS double) AS real_token_reserves,
        CAST(NULL AS double) AS real_quote_reserves,
        CAST(NULL AS varchar) AS pool_id,
        creator,
        CAST(is_mayhem_mode AS varchar) AS mayhem_mode,
        CAST(is_cashback_enabled AS varchar) AS cashback_enabled,
        CAST(token_program AS varchar) AS token_program
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND evt_block_time < TIMESTAMP '2026-08-30 00:00:00 UTC'
      AND mint = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
    UNION ALL
    SELECT
        mint,
        evt_block_time,
        evt_block_slot,
        evt_tx_id,
        evt_tx_index,
        evt_outer_instruction_index,
        evt_inner_instruction_index,
        CASE WHEN is_buy THEN 'BUY' ELSE 'SELL' END,
        'pumpfun',
        CAST(user AS varchar),
        CASE WHEN is_buy THEN 'buy' ELSE 'sell' END,
        CAST(token_amount AS double) / 1000000,
        CAST(sol_amount AS double) / 1000000000,
        (CAST(sol_amount AS double) / NULLIF(CAST(token_amount AS double), 0)) / 1000,
        ((CAST(sol_amount AS double) / NULLIF(CAST(token_amount AS double), 0)) / 1000) * sm.sol_usd,
        CAST(virtual_token_reserves AS double) / 1000000,
        CAST(virtual_sol_reserves AS double) / 1000000000,
        CAST(real_token_reserves AS double) / 1000000,
        CAST(real_sol_reserves AS double) / 1000000000,
        CAST(NULL AS varchar),
        creator,
        CAST(mayhem_mode AS varchar),
        CAST(cashback AS varchar),
        CAST(NULL AS varchar)
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    LEFT JOIN sol_marks sm ON sm.minute = date_trunc('minute', t.evt_block_time)
    WHERE t.evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND t.evt_block_time < TIMESTAMP '2026-08-30 00:00:00 UTC'
      AND t.mint = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
    UNION ALL
    SELECT
        mint,
        evt_block_time,
        evt_block_slot,
        evt_tx_id,
        evt_tx_index,
        evt_outer_instruction_index,
        evt_inner_instruction_index,
        'COMPLETE',
        'pumpfun',
        CAST(user AS varchar),
        CAST(NULL AS varchar),
        CAST(NULL AS double), CAST(NULL AS double), CAST(NULL AS double), CAST(NULL AS double),
        CAST(NULL AS double), CAST(NULL AS double), CAST(NULL AS double), CAST(NULL AS double),
        CAST(bonding_curve AS varchar), CAST(NULL AS varchar), CAST(NULL AS varchar), CAST(NULL AS varchar), CAST(NULL AS varchar)
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND evt_block_time < TIMESTAMP '2026-08-30 00:00:00 UTC'
      AND mint = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
    UNION ALL
    SELECT
        account_mint,
        call_block_time,
        call_block_slot,
        call_tx_id,
        call_tx_index,
        call_outer_instruction_index,
        call_inner_instruction_index,
        'MIGRATE',
        'pumpfun',
        CAST(account_user AS varchar),
        CAST(NULL AS varchar),
        CAST(NULL AS double), CAST(NULL AS double), CAST(NULL AS double), CAST(NULL AS double),
        CAST(NULL AS double), CAST(NULL AS double), CAST(NULL AS double), CAST(NULL AS double),
        CAST(account_pool AS varchar), CAST(NULL AS varchar), CAST(NULL AS varchar), CAST(NULL AS varchar), CAST(NULL AS varchar)
    FROM pumpdotfun_solana.pump_call_migrate
    WHERE call_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND call_block_time < TIMESTAMP '2026-08-30 00:00:00 UTC'
      AND account_mint = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
    UNION ALL
    SELECT
        CASE WHEN token_bought_mint_address = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
             THEN token_bought_mint_address ELSE token_sold_mint_address END,
        block_time,
        block_slot,
        tx_id,
        tx_index,
        outer_instruction_index,
        inner_instruction_index,
        CASE WHEN token_bought_mint_address = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
             THEN 'PUMPSWAP_BUY' ELSE 'PUMPSWAP_SELL' END,
        'pumpswap',
        trader_id,
        CASE WHEN token_bought_mint_address = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
             THEN 'buy' ELSE 'sell' END,
        CASE WHEN token_bought_mint_address = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
             THEN token_bought_amount ELSE token_sold_amount END,
        CASE WHEN token_bought_mint_address = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
             THEN token_sold_amount ELSE token_bought_amount END,
        CASE WHEN token_bought_mint_address = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
             THEN token_sold_amount / NULLIF(token_bought_amount, 0)
             ELSE token_bought_amount / NULLIF(token_sold_amount, 0) END,
        amount_usd / NULLIF(CASE WHEN token_bought_mint_address = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
             THEN token_bought_amount ELSE token_sold_amount END, 0),
        CAST(NULL AS double), CAST(NULL AS double), CAST(NULL AS double), CAST(NULL AS double),
        CAST(NULL AS varchar), CAST(NULL AS varchar), CAST(NULL AS varchar), CAST(NULL AS varchar), CAST(NULL AS varchar)
    FROM dex_solana.trades
    WHERE block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND block_time < TIMESTAMP '2026-08-30 00:00:00 UTC'
      AND project = 'pumpswap'
      AND (token_bought_mint_address = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump'
           OR token_sold_mint_address = '7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump')
)
SELECT * FROM lifecycle
ORDER BY event_time, block_slot, tx_index, outer_instruction_index, inner_instruction_index
