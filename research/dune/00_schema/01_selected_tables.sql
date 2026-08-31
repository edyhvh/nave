-- Purpose: executable schema/semantics probe for the selected Dune sources.
-- Every probe is bounded to one minute and returns no rows; this file is
-- documentation for the column contract, not a production panel query.

-- pumpdotfun_solana.pump_evt_createevent: launch, creator, supply, initial reserves.
SELECT * FROM pumpdotfun_solana.pump_evt_createevent
WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
  AND evt_block_time < TIMESTAMP '2026-08-27 00:01:00 UTC'
LIMIT 0;

-- pumpdotfun_solana.pump_evt_tradeevent: bonding-curve trades and reserve state.
SELECT * FROM pumpdotfun_solana.pump_evt_tradeevent
WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
  AND evt_block_time < TIMESTAMP '2026-08-27 00:01:00 UTC'
LIMIT 0;

-- pumpdotfun_solana.pump_evt_completeevent: graduation/completion.
SELECT * FROM pumpdotfun_solana.pump_evt_completeevent
WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
  AND evt_block_time < TIMESTAMP '2026-08-27 00:01:00 UTC'
LIMIT 0;

-- pumpdotfun_solana.pump_call_migrate: migration call and PumpSwap pool accounts.
SELECT * FROM pumpdotfun_solana.pump_call_migrate
WHERE call_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
  AND call_block_time < TIMESTAMP '2026-08-27 00:01:00 UTC'
LIMIT 0;

-- dex_solana.trades: normalized DEX trade continuation and instruction order.
SELECT * FROM dex_solana.trades
WHERE block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
  AND block_time < TIMESTAMP '2026-08-27 00:01:00 UTC'
  AND project = 'pumpswap'
LIMIT 0;

-- prices.usd: historical SOL/USD mark. contract_address is varbinary in this
-- table; address joins require the table's encoded representation, not a string.
SELECT * FROM prices.usd
WHERE minute >= TIMESTAMP '2026-08-27 00:00:00 UTC'
  AND minute < TIMESTAMP '2026-08-27 00:01:00 UTC'
  AND blockchain = 'solana'
LIMIT 0;
