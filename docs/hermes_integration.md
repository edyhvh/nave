# Hermes Integration Guide

This guide describes how Hermes Agent can integrate with Nave using modular
CLI commands, MCP tools, and gateway-style payload dispatch.

## Integration Surfaces

Nave exposes Hermes-compatible interfaces through:

1. `hermes/integration.py`
   - Tool registry (`list_tools`)
   - Structured dispatch (`dispatch_tool_call`)
   - Gateway payload handler (`gateway_invoke`)
2. `cli` Hermes command group
   - `nave hermes tools`
   - `nave hermes call`
   - `nave hermes gateway-invoke`
3. `trading/mcp_server.py`
   - Existing account/execution tools
   - COT + scan tools (`cot_report`, `cot_history`, `weekly_plan`, `theory_v2_scan`, `scan_history`)
   - Stocks macro report tool (`stocks_ism_report`)

## Tool Contracts

### `cot_report`

Returns latest COT metrics and bias for selected assets.

Input:

- `coins` (string): space-separated symbols, default `"BTC ETH"`
- `include_micro` (bool): include micro contracts
- `report_type` (string): `futures_only` or `futures_and_options`

### `cot_history`

Returns historical COT variation report for calendar windows.

Input:

- `months` (int): `1..12`
- `coins` (string)
- `include_micro` (bool)
- `report_type` (string)

### `weekly_plan`

Generates a weekly plan from real COT and 4H structure.

Input:

- `capital` (float)
- `wallet` (string)
- `coins` (string)
- `include_micro` (bool)

### `momentum_scan`

Returns BTC/ETH derivatives momentum scan data (4H setup + 1H trigger by default).

Input:

- `symbols` (string): comma-separated symbols, default `"BTCUSDT,ETHUSDT"`
- `tf` (string): setup/trigger pair, default `"4h,1h"`
- `account_equity` (number): sizing context
- `risk_pct` (number): decimal risk per trade (default `0.005`)
- `score_threshold` (integer): minimum score to classify setups as tradeable

Output additions:

- `telegram_markdown_v2[]`: pre-formatted digest chunks ready to send with
  `parse_mode=MarkdownV2`

Hermes behavior:

- Use `telegram_markdown_v2` directly for Telegram delivery (send one chunk per message).
- Keep the raw JSON (`summary`, `cadence`, `results`) for downstream logic and audits.
- Even when `tradeable_count == 0`, the digest includes conditional watch plans so
  the user can track pending zones.

### `momentum_zone_watch`

Monitors momentum entry zones and emits alerts when live price first touches a
watched zone.

Input:

- `symbols` (string): comma-separated symbols, default `"BTCUSDT,ETHUSDT"`
- `tf` (string): setup/trigger pair, default `"4h,1h"`
- `score_threshold` (int): minimum plan score to watch
- `account_equity` (number): sizing context for scan generation
- `risk_pct` (number): risk decimal used by scan generation

Output (key fields):

- `alert_count`, `alerts[]`
- `watch_candidates[]`
- `scan_summary`
- `telegram_markdown_v2[]`: alert chunks ready for Telegram `parse_mode=MarkdownV2`
- `operational_hints`: preferred execution mode plus safe reminder cadence

Scheduling guidance:
- For chat/reminder jobs, do **not** schedule faster than hourly.
- For high-frequency monitoring, use `scripts/monitor_entry_zones.py` via cron/launchd
  and send Telegram directly.

### `options_opportunities`

Returns BTC/ETH options opportunities from the options module by combining:

1. Momentum setup filtering (4H/1H path by default)
2. Options analysis on momentum-qualified symbols

Input:

- `coins` (string): comma-separated symbols, default `"BTC,ETH"`
- `days_to_exp` (int): target DTE for options ranking
- `tf` (string): momentum setup/trigger pair, default `"4h,1h"`
- `account_equity` (number): sizing context used by momentum filters
- `risk_pct` (number): risk decimal used by momentum filters
- `score_threshold` (int): momentum score threshold for tradeable gating
- `require_tradeable` (bool): if `true`, only analyze options for momentum-tradeable setups

Output (key fields):

- `summary`: requested/supported coins, momentum-allowed count, options-ready count
- `momentum`: timeframes and momentum summary metadata
- `opportunities[COIN]`: per-coin status (`ready`, `filtered_by_momentum`, `options_unavailable`, `unsupported_coin`)
- `ranked[]`: top ready opportunities with strategy score and expected value
- `telegram_markdown_v2[]`: compact digest chunks for Telegram delivery

### `stocks_ism_report`

Returns ISM hottest/worst industries and filtered stock candidates using FMP fundamentals.

Input:

- `kind` (string): `manufacturing` or `services`
- `top_n` (int): top candidates per trend bucket
- `max_pe_ratio` (number, optional): keep only names with `PE <= max_pe_ratio`
- `min_eps_growth_next_year` (number, optional): keep only names with `EPS growth >= threshold`

Output additions:
- `telegram_markdown_v2[]`: deterministic summary digest ready for Telegram
- `operational_hints`: hourly reminder guidance and provider-429 fallback note

### `stocks_politicians_scan`

Returns newly-disclosed Congressional STOCK Act trades (House + Senate) since
the previous scan. Designed for **autonomous daily invocation** — Hermes should
call this once per day as part of its standing routine.

Input:

- `lookback_days` (int, optional): reserved for future filtering. Currently
  ignored by the provider; novelty is gated entirely by the local seen-cache.
- `persist` (bool, default `true`): update the seen-cache with this scan's
  results. Set `false` for a dry-run preview.

Output (key fields):

- `generated_at`, `previous_scan_at`
- `fetched_total`: total disclosures returned by FMP `/house-latest` + `/senate-latest`
- `new_total`: count not seen in any prior scan — **the notification trigger**
- `summary`: counts by chamber, transaction type, top symbols, unique politicians
- `new_trades[]`: each entry includes `chamber`, `symbol`, `politician`,
  `state`, `district`, `owner`, `transaction_type` (Purchase / Sale / Exchange),
  `amount_range` (bucketed string, e.g. `"$1,001 - $15,000"`), `transaction_date`,
  `disclosure_date`, and `link` (source PDF/eFD URL)
- `telegram_markdown_v2[]`: pre-formatted digest chunks ready to send to
  Telegram with `parse_mode=MarkdownV2` (empty when `new_total == 0`)
- `operational_hints`: daily reminder guidance and provider-429 fallback note

Hermes behavior:

- **Once per day.** Call as part of the daily routine. The provider returns the
  same "latest" window regardless of when called; cadence faster than daily
  buys nothing.
- **Notify on `new_total > 0`.** Surface every new disclosure to the user —
  no chamber, ticker, politician, or amount filtering. The user wants the
  full firehose so they can decide which ones to act on.
- **Stay silent on `new_total == 0`.** Do not emit a "nothing to report"
  message daily; only speak up when there's actually new content.
- **Frame as informational, not a real-time edge.** The STOCK Act allows up
  to 45 days between trade and disclosure — copycat trading is not a
  guaranteed signal. Present trades as context for the user's own research.
- **Amounts are buckets, not exact values.** When the user asks about size,
  cite the bucket (e.g. `"$1,001 - $15,000"`) rather than inventing a midpoint.
- **Always include the source `link`** so the user can verify the original filing.
- **Telegram formatting:** send each `telegram_markdown_v2` chunk as a separate
  message. The digest is ordered as summary first, then grouped details.

### `stocks_ism_calendar`

Returns the stored ISM release calendar, next release, or most recent release
inside a retry window.

Input:

- `year` (int, optional): calendar year for full release listing.
- `kind` (string, optional): `manufacturing` or `services`.
- `next_only` (bool, default `false`): return the next upcoming release.
- `recent_days` (int, default `0`): when `> 0`, return the most recent release
  within the lookback window; useful for release-day retry jobs that run the
  next day in local timezone.
- `refresh` (bool, default `false`): re-fetch and overwrite stored calendar.

Output additions:
- `operational_hints`: prefer `next_only` / `recent_days` with `refresh=false`
  for recurring jobs so reminders reuse stored calendar data

### `stocks_x_analyze`
Fetches recent X posts and returns both:

- `analysis_prompt`: the richer LLM path for full sentiment writeups
- `telegram_markdown_v2[]`: deterministic fallback digest for provider-429 cases
- `operational_hints`: hourly reminder guidance and fallback note

## Entry-Zone Monitor (conditional setup alerts)

For "notify me when price reaches planned entry zone" workflows, use:

```bash
python scripts/monitor_entry_zones.py --symbols BTCUSDT,ETHUSDT --tf 4h,1h --score-threshold 75 --json
```

Notes:

- Designed for frequent scheduling (for example every 5 minutes).
- Detects first touch into each candidate `entry_zone` and de-duplicates via state file.
- Persists watch state in `var/state/entry_zone_watch.json`.
- Optional Telegram dispatch with `--send-telegram` using:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
- This monitor does **not** place orders; notifications are informational.

Example payload (truncated):

```json
{
  "generated_at": "2026-04-29T12:00:00+00:00",
  "previous_scan_at": "2026-04-28T12:00:00+00:00",
  "fetched_total": 80,
  "new_total": 3,
  "summary": {
    "by_chamber": { "house": 2, "senate": 1 },
    "by_type": { "Purchase": 2, "Sale": 1 },
    "top_symbols": [{ "symbol": "NVDA", "count": 2 }]
  },
  "new_trades": [
    {
      "chamber": "house",
      "symbol": "NVDA",
      "politician": "Jane Doe",
      "transaction_type": "Purchase",
      "amount_range": "$15,001 - $50,000",
      "transaction_date": "2026-04-10",
      "disclosure_date": "2026-04-28",
      "link": "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/..."
    }
  ]
}
```

## Examples

### List tool metadata

```bash
nave hermes tools
```

### Call tool directly

```bash
nave hermes call --tool cot_report --args-json '{"coins": "BTC ETH"}'
```

### Gateway payload invocation

```bash
nave hermes gateway-invoke '{"tool": "cot_history", "arguments": {"months": 3}}'
```

## MCP Use

Start MCP server:

```bash
nave mcp run
```

Hermes can then call tool names registered by the FastMCP server, including
COT report/history/planning tools plus `stocks_ism_report` for ISM equity workflows.

## Optional Remote FMP MCP

Nave already exposes its own local FastMCP server for repo-native tools. FMP also
ships a remote MCP endpoint for direct vendor access:

```bash
nave mcp fmp-connector
```

This prints `https://financialmodelingprep.com/mcp?apikey=...` using `FMP_API_KEY`.
Use that in an MCP client when you want direct FMP tools without proxying them
through Nave. Those calls still consume the same FMP API quota.
