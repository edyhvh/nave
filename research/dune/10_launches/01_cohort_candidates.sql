-- Purpose: choose a bounded historical cohort and find complete lifecycle candidates.
-- Period: launches on 2026-08-27 UTC; lifecycle look-ahead ends 2026-08-30 UTC
-- (72 hours after the selected launch date).
-- Sources: Pump.fun decoded create/complete events, migrate calls, and DEX Spellbook.
-- Limitations: PumpSwap is linked by mint in dex_solana.trades; pool identity is
-- retained from the migration call where available and is not guessed from symbols.

WITH launches AS (
    SELECT
        mint,
        creator,
        evt_block_time AS launch_ts,
        evt_block_slot AS launch_slot,
        evt_tx_id AS launch_tx_id,
        evt_tx_index AS launch_tx_index,
        evt_outer_instruction_index AS launch_outer_instruction_index,
        evt_inner_instruction_index AS launch_inner_instruction_index,
        quote_mint,
        token_total_supply,
        real_token_reserves,
        virtual_sol_reserves,
        virtual_token_reserves,
        is_mayhem_mode,
        is_cashback_enabled,
        token_program,
        ROW_NUMBER() OVER (PARTITION BY mint ORDER BY evt_block_time, evt_tx_index, evt_outer_instruction_index, evt_inner_instruction_index) AS rn
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND evt_block_time < TIMESTAMP '2026-08-28 00:00:00 UTC'
), first_launch AS (
    SELECT * FROM launches WHERE rn = 1
), completions AS (
    SELECT mint, MIN(evt_block_time) AS complete_ts, COUNT(*) AS complete_rows
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND evt_block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
    GROUP BY mint
), migrations AS (
    SELECT
        account_mint AS mint,
        MIN(call_block_time) AS migration_ts,
        MIN_BY(account_pool, call_block_time) AS pool_id,
        MIN_BY(account_pump_amm, call_block_time) AS pump_amm,
        COUNT(*) AS migration_rows,
        SUM(CASE WHEN array_join(call_log_messages, ' ') LIKE '%already migrated%' THEN 1 ELSE 0 END) AS already_migrated_rows
    FROM pumpdotfun_solana.pump_call_migrate
    WHERE call_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND call_block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
    GROUP BY account_mint
), pumpswap AS (
    SELECT
        mint,
        MIN(first_ts) AS pumpswap_first_ts,
        SUM(trade_count) AS pumpswap_trade_count,
        SUM(unique_trader_count) AS pumpswap_unique_traders
    FROM (
        SELECT
            CASE WHEN token_bought_mint_address <> 'So11111111111111111111111111111111111111112'
                 THEN token_bought_mint_address ELSE token_sold_mint_address END AS mint,
            MIN(block_time) AS first_ts,
            COUNT(*) AS trade_count,
            COUNT(DISTINCT trader_id) AS unique_trader_count
        FROM dex_solana.trades
        WHERE block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
          AND block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
          AND project = 'pumpswap'
          AND (token_bought_mint_address <> 'So11111111111111111111111111111111111111112'
               OR token_sold_mint_address <> 'So11111111111111111111111111111111111111112')
        GROUP BY 1
    ) grouped
    GROUP BY mint
)
SELECT
    l.mint,
    l.creator,
    l.launch_ts,
    l.launch_slot,
    l.launch_tx_id,
    l.quote_mint,
    l.token_total_supply,
    l.real_token_reserves,
    l.virtual_sol_reserves,
    l.virtual_token_reserves,
    l.is_mayhem_mode,
    l.is_cashback_enabled,
    l.token_program,
    c.complete_ts,
    c.complete_rows,
    m.migration_ts,
    m.pool_id,
    m.pump_amm,
    m.migration_rows,
    m.already_migrated_rows,
    p.pumpswap_first_ts,
    p.pumpswap_trade_count,
    p.pumpswap_unique_traders
FROM first_launch l
LEFT JOIN completions c ON c.mint = l.mint
LEFT JOIN migrations m ON m.mint = l.mint
LEFT JOIN pumpswap p ON p.mint = l.mint
ORDER BY l.launch_ts, l.mint
LIMIT 20000
