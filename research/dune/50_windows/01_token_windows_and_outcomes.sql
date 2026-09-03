-- Purpose: compact launch-relative historical windows and point-in-time marks.
-- Cohort: all Pump.fun launches on 2026-08-27 UTC. Observation: launch through
-- launch + 72h. Raw trade rows are not exported; this query aggregates in Dune.
-- Price: Pump.fun SOL/token amounts are converted with historical prices.usd
-- minute marks; PumpSwap uses its historical amount_usd and quote amounts.
-- Outcome marks use a fixed +/- 5 minute tolerance around each horizon. A
-- missing mark is UNKNOWN, never a zero return.

WITH sol_marks AS (
    SELECT minute, MAX(price) AS sol_usd
    FROM prices.usd
    WHERE minute >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND minute < TIMESTAMP '2026-08-31 00:00:00 UTC'
      AND blockchain = 'solana' AND symbol = 'SOL'
    GROUP BY minute
), launches AS (
    SELECT mint, MIN(evt_block_time) AS launch_ts,
           MAX_BY(creator, evt_block_time) AS creator,
           MAX_BY(token_total_supply, evt_block_time) AS token_total_supply,
           MAX_BY(is_mayhem_mode, evt_block_time) AS is_mayhem_mode,
           MAX_BY(is_cashback_enabled, evt_block_time) AS is_cashback_enabled,
           MAX_BY(quote_mint, evt_block_time) AS quote_mint,
           MAX_BY(token_program, evt_block_time) AS token_program
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND evt_block_time < TIMESTAMP '2026-08-28 00:00:00 UTC'
    GROUP BY mint
), migrations AS (
    SELECT account_mint AS mint, MIN(call_block_time) AS migration_ts,
           MIN_BY(account_pool, call_block_time) AS pool_id
    FROM pumpdotfun_solana.pump_call_migrate
    WHERE call_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND call_block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
    GROUP BY account_mint
), pump_events AS (
    SELECT
        t.mint, t.evt_block_time AS event_time, t.evt_block_slot AS block_slot,
        t.evt_tx_id AS tx_id, t.evt_tx_index AS tx_index,
        t.evt_outer_instruction_index AS outer_instruction_index,
        t.evt_inner_instruction_index AS inner_instruction_index,
        CAST(t.user AS varchar) AS wallet,
        CASE WHEN t.is_buy THEN 'buy' ELSE 'sell' END AS side,
        CAST(t.sol_amount AS double) / 1000000000 AS quote_amount_sol,
        (CAST(t.sol_amount AS double) / NULLIF(CAST(t.token_amount AS double), 0)) / 1000 AS price_sol,
        ((CAST(t.sol_amount AS double) / NULLIF(CAST(t.token_amount AS double), 0)) / 1000) * sm.sol_usd AS price_usd,
        CAST(t.token_amount AS double) / 1000000 AS token_amount,
        CAST(t.virtual_sol_reserves AS double) / 1000000000 AS virtual_quote_reserves,
        CAST(t.virtual_token_reserves AS double) / 1000000 AS virtual_token_reserves,
        CAST(t.real_sol_reserves AS double) / 1000000000 AS real_quote_reserves,
        CAST(t.real_token_reserves AS double) / 1000000 AS real_token_reserves,
        'pumpfun' AS venue
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN launches l ON l.mint = t.mint
    LEFT JOIN sol_marks sm ON sm.minute = date_trunc('minute', t.evt_block_time)
    WHERE t.evt_block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND t.evt_block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
      AND t.evt_block_time >= l.launch_ts
      AND t.evt_block_time < date_add('hour', 72, l.launch_ts)
), pumpswap_events AS (
    SELECT
        CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
             THEN d.token_sold_mint_address ELSE d.token_bought_mint_address END AS mint,
        d.block_time AS event_time, d.block_slot, d.tx_id, d.tx_index,
        d.outer_instruction_index, d.inner_instruction_index,
        d.trader_id AS wallet,
        CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
             THEN 'sell' ELSE 'buy' END AS side,
        CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
             THEN d.token_bought_amount ELSE d.token_sold_amount END AS quote_amount_sol,
        CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
             THEN d.token_bought_amount / NULLIF(d.token_sold_amount, 0)
             ELSE d.token_sold_amount / NULLIF(d.token_bought_amount, 0) END AS price_sol,
        d.amount_usd / NULLIF(CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
             THEN d.token_sold_amount ELSE d.token_bought_amount END, 0) AS price_usd,
        CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
             THEN d.token_sold_amount ELSE d.token_bought_amount END AS token_amount,
        CAST(NULL AS double) AS virtual_quote_reserves,
        CAST(NULL AS double) AS virtual_token_reserves,
        CAST(NULL AS double) AS real_quote_reserves,
        CAST(NULL AS double) AS real_token_reserves,
        'pumpswap' AS venue
    FROM dex_solana.trades d
    JOIN launches l ON l.mint = CASE WHEN d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
                                     THEN d.token_sold_mint_address ELSE d.token_bought_mint_address END
    WHERE d.block_time >= TIMESTAMP '2026-08-27 00:00:00 UTC'
      AND d.block_time < TIMESTAMP '2026-08-31 00:00:00 UTC'
      AND d.project = 'pumpswap'
      AND (d.token_bought_mint_address = 'So11111111111111111111111111111111111111112'
           OR d.token_sold_mint_address = 'So11111111111111111111111111111111111111112')
      AND d.block_time >= l.launch_ts
      AND d.block_time < date_add('hour', 72, l.launch_ts)
), events AS (
    SELECT e.*, date_diff('second', l.launch_ts, e.event_time) AS rel_sec
    FROM (SELECT * FROM pump_events UNION ALL SELECT * FROM pumpswap_events) e
    JOIN launches l ON l.mint = e.mint
    WHERE e.event_time >= l.launch_ts
), windows AS (
    SELECT * FROM UNNEST(ARRAY[30, 60, 180, 300, 600, 900, 1800, 3600, 14400, 28800, 86400, 172800, 259200]) AS u(window_end_seconds)
), stats AS (
    SELECT
        l.mint, w.window_end_seconds,
        COUNT(e.event_time) AS trade_count,
        COUNT_IF(e.side = 'buy') AS buy_count,
        COUNT_IF(e.side = 'sell') AS sell_count,
        COUNT(DISTINCT CASE WHEN e.side = 'buy' THEN e.wallet END) AS unique_buyers,
        COUNT(DISTINCT CASE WHEN e.side = 'sell' THEN e.wallet END) AS unique_sellers,
        SUM(CASE WHEN e.side = 'buy' THEN e.quote_amount_sol ELSE 0 END) AS buy_quote_volume_sol,
        SUM(CASE WHEN e.side = 'sell' THEN e.quote_amount_sol ELSE 0 END) AS sell_quote_volume_sol,
        approx_percentile(e.quote_amount_sol, 0.5) AS median_trade_size_sol,
        MAX(e.quote_amount_sol) / NULLIF(SUM(e.quote_amount_sol), 0) AS largest_trade_share,
        MIN_BY(e.price_usd, e.event_time) FILTER (WHERE e.price_usd IS NOT NULL) AS price_open_usd,
        MAX(e.price_usd) AS price_high_usd,
        MIN(e.price_usd) AS price_low_usd,
        MAX_BY(e.price_usd, e.event_time) FILTER (WHERE e.price_usd IS NOT NULL) AS price_close_usd,
        MAX_BY(e.virtual_quote_reserves, e.event_time) FILTER (WHERE e.virtual_quote_reserves IS NOT NULL) AS virtual_quote_reserves_sol,
        MAX_BY(e.real_quote_reserves, e.event_time) FILTER (WHERE e.real_quote_reserves IS NOT NULL) AS real_quote_reserves_sol,
        COUNT_IF(e.venue = 'pumpfun') AS pumpfun_trade_count,
        COUNT_IF(e.venue = 'pumpswap') AS pumpswap_trade_count
    FROM launches l CROSS JOIN windows w
    LEFT JOIN events e ON e.mint = l.mint AND e.rel_sec >= 0 AND e.rel_sec <= w.window_end_seconds
    GROUP BY l.mint, w.window_end_seconds
), markers AS (
    SELECT
        l.mint, h.horizon_seconds,
        MIN_BY(e.price_usd, ABS(date_diff('second', e.event_time, date_add('second', h.horizon_seconds, l.launch_ts)))) FILTER (WHERE e.price_usd IS NOT NULL) AS mark_price_usd,
        MIN_BY(e.event_time, ABS(date_diff('second', e.event_time, date_add('second', h.horizon_seconds, l.launch_ts)))) FILTER (WHERE e.price_usd IS NOT NULL) AS mark_observed_ts,
        COUNT_IF(e.price_usd IS NOT NULL AND e.event_time >= date_add('second', h.horizon_seconds - 300, l.launch_ts) AND e.event_time <= date_add('second', h.horizon_seconds + 300, l.launch_ts)) AS mark_candidates
    FROM launches l
    CROSS JOIN UNNEST(ARRAY[300, 900, 1800, 3600, 14400, 28800, 86400, 172800, 259200]) AS h(horizon_seconds)
    LEFT JOIN events e ON e.mint = l.mint
        AND e.event_time >= date_add('second', h.horizon_seconds - 300, l.launch_ts)
        AND e.event_time <= date_add('second', h.horizon_seconds + 300, l.launch_ts)
    GROUP BY l.mint, h.horizon_seconds
)
SELECT
    s.*,
    l.launch_ts, l.creator, l.token_total_supply, l.is_mayhem_mode,
    l.is_cashback_enabled, l.quote_mint, l.token_program,
    m.migration_ts, m.pool_id,
    mk.mark_price_usd, mk.mark_observed_ts, mk.mark_candidates,
    CASE WHEN mk.mark_price_usd IS NOT NULL THEN 'RESOLVED' ELSE 'UNKNOWN' END AS outcome_status,
    mk.horizon_seconds
FROM stats s
JOIN launches l ON l.mint = s.mint
LEFT JOIN migrations m ON m.mint = s.mint
LEFT JOIN markers mk ON mk.mint = s.mint AND mk.horizon_seconds = s.window_end_seconds
ORDER BY s.mint, s.window_end_seconds
