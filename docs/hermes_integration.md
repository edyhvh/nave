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

### `stocks_ism_report`
Returns ISM hottest/worst industries and filtered stock candidates using FMP fundamentals.

Input:
- `kind` (string): `manufacturing` or `services`
- `top_n` (int): top candidates per trend bucket
- `max_pe_ratio` (number, optional): keep only names with `PE <= max_pe_ratio`
- `min_eps_growth_next_year` (number, optional): keep only names with `EPS growth >= threshold`

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

Example payload (truncated):
```json
{
  "generated_at": "2026-04-29T12:00:00+00:00",
  "previous_scan_at": "2026-04-28T12:00:00+00:00",
  "fetched_total": 80,
  "new_total": 3,
  "summary": {
    "by_chamber": {"house": 2, "senate": 1},
    "by_type": {"Purchase": 2, "Sale": 1},
    "top_symbols": [{"symbol": "NVDA", "count": 2}]
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
