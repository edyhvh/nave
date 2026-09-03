-- Credit-efficient source stage. Render the selected_mints VALUES list locally.
-- One scan of Pump.fun trades; no launch x artificial-landmark cross join.
-- Keep event ordering fields for local precursor reconstruction.
-- See efficient.first_hour_query for a bounded rendered query.

WITH selected_mints(mint) AS (
    VALUES
        -- ('rendered_mint_1'), ('rendered_mint_2')
), launches AS (
    SELECT mint, MIN(evt_block_time) AS launch_time
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND evt_block_time < TIMESTAMP '2026-08-28 00:00:00 UTC'
    GROUP BY mint
)
SELECT
    t.mint, t.evt_block_time AS event_time, t.evt_block_slot AS slot,
    t.evt_tx_id AS transaction, t.evt_tx_index AS tx_index,
    t.evt_outer_instruction_index AS outer_instruction_index,
    t.evt_inner_instruction_index AS inner_instruction_index,
    CAST(t.user AS varchar) AS wallet,
    CASE WHEN t.is_buy THEN 'buy' ELSE 'sell' END AS side,
    CAST(t.token_amount AS double) / 1000000 AS token_amount,
    CAST(t.sol_amount AS double) / 1000000000 AS quote_amount_sol,
    CAST(t.fee AS double) / 1000000000 AS fee_sol,
    CAST(t.virtual_sol_reserves AS double) / 1000000000 AS virtual_quote_reserves_sol,
    CAST(t.virtual_token_reserves AS double) / 1000000 AS virtual_token_reserves,
    CAST(t.real_sol_reserves AS double) / 1000000000 AS real_quote_reserves_sol,
    CAST(t.real_token_reserves AS double) / 1000000 AS real_token_reserves
FROM pumpdotfun_solana.pump_evt_tradeevent t
JOIN selected_mints s ON s.mint = t.mint
JOIN launches l ON l.mint = t.mint
WHERE t.evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
  AND t.evt_block_time < TIMESTAMP '2026-08-28 00:00:00 UTC'
  AND t.evt_block_time >= l.launch_time
  AND t.evt_block_time < date_add('hour', 1, l.launch_time)
