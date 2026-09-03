-- Purpose: materialize the complete 2026-08-27 UTC Pump.fun launch denominator.
-- Bounds: exactly one UTC day; all launches are retained, including tokens with
-- no later trades or migration. One row per mint is selected deterministically.

WITH ranked AS (
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
        name,
        symbol,
        uri,
        bonding_curve,
        ROW_NUMBER() OVER (
            PARTITION BY mint
            ORDER BY evt_block_time, evt_block_slot, evt_tx_index,
                     evt_outer_instruction_index, evt_inner_instruction_index
        ) AS rn
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND evt_block_time < TIMESTAMP '2026-08-28 00:00:00 UTC'
)
SELECT * FROM ranked WHERE rn = 1 ORDER BY launch_ts, launch_slot, launch_tx_index
