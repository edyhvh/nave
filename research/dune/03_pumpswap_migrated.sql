-- Stage D template. The migrated_mints VALUES list is rendered locally.
WITH migrated_mints(mint) AS (
    VALUES
        -- ('rendered_mint_1')
)
SELECT
    CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
         THEN d.token_sold_mint_address ELSE d.token_bought_mint_address END AS mint,
    d.block_time AS event_time, d.block_slot AS slot, d.tx_id AS transaction,
    d.tx_index, d.outer_instruction_index, d.inner_instruction_index,
    d.trader_id AS wallet,
    CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
         THEN 'sell' ELSE 'buy' END AS side,
    CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
         THEN d.token_sold_amount ELSE d.token_bought_amount END AS token_amount,
    CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
         THEN d.token_bought_amount ELSE d.token_sold_amount END AS quote_amount_sol,
    d.amount_usd, d.fee_usd, d.fee_tier, d.token_bought_vault, d.token_sold_vault
FROM dex_solana.trades d
JOIN migrated_mints m ON m.mint = CASE
    WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
    THEN d.token_sold_mint_address ELSE d.token_bought_mint_address END
WHERE d.blockchain = 'solana'
  AND d.block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
  AND d.block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
  AND d.project = 'pumpswap'
