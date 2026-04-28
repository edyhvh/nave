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
