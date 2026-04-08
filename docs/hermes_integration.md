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
   - New COT-oriented tools (`cot_report`, `cot_history`, `weekly_plan`)

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
COT report/history/weekly planning tools for autonomous workflows.
