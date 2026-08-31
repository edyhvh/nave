-- Prototype only. An account with incremental-query support can replace the
-- prior result reference with its exact TABLE(previous.query.result(...)) name.
-- The query is deliberately a compact daily aggregate, not raw history.
SELECT CAST(evt_block_time AS date) AS launch_date,
       COUNT(DISTINCT mint) AS launches,
       COUNT(DISTINCT creator) AS creators
FROM pumpdotfun_solana.pump_evt_createevent
WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
  AND evt_block_time < TIMESTAMP '2026-08-28 00:00:00 UTC'
GROUP BY 1
