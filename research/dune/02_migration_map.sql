-- Compact Stage C. Restrict post-migration work to the small migrated set.
SELECT account_mint AS mint, MIN(call_block_time) AS migration_time,
       MIN_BY(account_pool, call_block_time) AS pool_id,
       MIN_BY(account_pump_amm, call_block_time) AS pump_amm
FROM pumpdotfun_solana.pump_call_migrate
WHERE call_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
  AND call_block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
GROUP BY account_mint
