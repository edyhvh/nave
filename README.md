# Nave

Nave is a terminal-first trading copilot with three main surfaces:

- crypto: BTC/ETH momentum, COT context, Hyperliquid execution paths
- stocks: ISM-driven sector workflow with FMP fundamentals
- agents: Hermes and MCP-compatible JSON tool contracts

The root README is the fast path: get it running locally, connect an agent,
and use the CLI. Deeper theory and integration details live in the docs linked
at the end.

## Quick Setup

### Local setup

```bash
git clone https://github.com/edyhvh/nave.git
cd nave
python setup.py
```

`python setup.py` will:

- create `.venv`
- install dependencies from `requirements.txt`
- install the editable package and a local `nave` shim
- add `.venv/bin` to your shell rc file
- run `direnv allow` if `direnv` is available

Reload your shell after setup:

```bash
source ~/.zshrc
# or
source ~/.bashrc
```

Verify the CLI:

```bash
nave --help
nave version
```

Fallback if your shell has not picked up the shim yet:

```bash
PYTHONPATH=. python cli/main.py --help
```

### Required and optional keys

Create a `.env` file in the repo root.

Required for macro data:

```bash
FRED_API_KEY=your_fred_api_key
```

Optional for stocks and remote FMP MCP:

```bash
FMP_API_KEY=your_fmp_api_key
```

If you want OpenBB to persist the FRED key in its own config too:

```bash
python -c "from openbb import obb; obb.user.credentials.fred_api_key.set('your_fred_api_key'); obb.account.save()"
```

### Optional shell ergonomics

If you use `direnv`, enable it once and let Nave auto-activate the repo env:

```bash
echo 'eval "$(direnv hook zsh)"' >> ~/.zshrc
# or
echo 'eval "$(direnv hook bash)"' >> ~/.bashrc

direnv allow
```

If you do not use `direnv`, activate the environment manually:

```bash
source .venv/bin/activate
```

## Quick Setup with Hermes

Once local setup works, there are two common ways to wire an agent into Nave.

### 1. Use Hermes CLI contracts directly

List the available Hermes tools:

```bash
nave hermes tools
```

Call one tool directly and get structured JSON back:

```bash
nave hermes call --tool cot_report --args-json '{"coins": "BTC ETH"}'
nave hermes call --tool cot_history --args-json '{"months": 3, "coins": "BTC ETH"}'
nave hermes call --tool weekly_plan --args-json '{"capital": 2000, "wallet": "hermes"}'
```

If your agent expects a gateway-style payload:

```bash
nave hermes gateway-invoke '{"tool": "cot_report", "arguments": {"coins": "BTC ETH"}}'
```

### 2. Run Nave as an MCP server

Start the local MCP server over stdio:

```bash
nave mcp run
```

That exposes Nave's MCP tools to Hermes or any MCP-compatible client.

If you also want the vendor's remote FMP MCP connector URL:

```bash
nave mcp fmp-connector
```

Notes:

- Hermes-facing commands are designed to return structured JSON.
- Use the local MCP server for repo-native tools.
- Use the remote FMP connector only when you specifically need direct vendor MCP access.

## Using the CLI

The main entrypoint is `nave`. Start by inspecting the command tree:

```bash
nave --help
nave crypto --help
nave cot --help
nave stocks --help
nave options --help
nave hermes --help
nave mcp --help
```

### Crypto workflow

Scan BTC/ETH derivatives for current setups:

```bash
nave crypto scan
nave crypto scan --symbols BTCUSDT,ETHUSDT --tf 4h,1h --json
```

Build a concrete playbook for one symbol and side:

```bash
nave crypto playbook --symbol BTCUSDT --side long
nave crypto playbook --symbol ETHUSDT --side short --json
```

Backtest the live momentum engine on recent history:

```bash
nave crypto momentum-backtest --lookback-days 180
```

### Weekly COT workflow

Generate a manual COT report:

```bash
nave cot report --coins "BTC ETH"
nave cot report --coins "BTC ETH" --cot-history 3 --json
```

Run the broader weekly trading flow:

```bash
nave trading run --strategy cot-weekly --paper
```

### Stocks workflow

Fetch the latest ISM report:

```bash
nave stocks ism-scan --kind manufacturing
nave stocks ism-scan --kind services --json
```

Generate a stock report or screen:

```bash
nave stocks ism-report --kind manufacturing --top-n 5 --sheet
nave stocks screen --kind manufacturing --top-n 5 --capital 10000
```

### Options workflow

Run options analysis for a ticker and get a sheet-style ranked strategy summary in the terminal:

```bash
nave options analyze --ticker MSFT --days-to-exp 30
```

Render terminal-native charts (no browser) with plotext while keeping the
existing report flow and HTML chart artifacts:

```bash
nave options analyze --ticker MSFT --days-to-exp 30 --terminal
# alias
nave options analyze --ticker MSFT --days-to-exp 30 --ascii
```

When `--terminal` (or `--ascii`) is enabled, human output is grouped in this order:

1. Prompt and data block
2. Graphs (payoff, Greeks, Monte Carlo, strategy ranking)
3. Summary (metrics table, rankings, risk warnings)

The sheet run also saves a copyable JSON report file (path shown in terminal), so
you can share or reuse the result in automation.

Use a custom report path when needed:

```bash
nave options analyze --ticker MSFT --days-to-exp 30 --json-path ./msft_options.json
```

Print a ready-to-copy LLM prompt based on the generated report:

```bash
nave options analyze --ticker MSFT --days-to-exp 30 --llm-prompt
```

Terminal charts + LLM prompt in one run:

```bash
nave options analyze --ticker MSFT --days-to-exp 30 --terminal --llm-prompt
```

If you also pass `--json`, the output JSON includes `llm_prompt` plus the full
`charts` paths in a separate `llm_paths` block so downstream agents can consume everything from one payload:

```bash
nave options analyze --ticker MSFT --days-to-exp 30 --json --llm-prompt
```

`llm_prompt` contains embedded JSON analysis data with paths omitted, while
`llm_paths` contains the actual file/chart paths.

Emit full machine JSON only when you explicitly need automation payloads:

```bash
nave options analyze --ticker AAPL --days-to-exp 45 --json
```

### Agent and service workflow

Useful operational commands:

```bash
nave hermes tools
nave hermes call --tool options_scan --args-json '{"ticker": "MSFT", "days_to_exp": 30}'
nave mcp run
nave api start --reload
nave data fetch all
```

### JSON vs human output

Use human output in the terminal and `--json` for automation. Hermes-facing
commands are built around JSON contracts, and many reporting commands support
both modes.

## Hyperliquid and wallet setup

If you only want analysis, you can stop at CLI setup.

If you want execution paths on Hyperliquid, generate wallets locally:

```bash
python scripts/setup_wallets.py
```

Then use dry-run or paper-style flows first:

```bash
nave trading run --strategy cot-weekly --paper
```

For deeper wallet and execution details, see the linked docs below.

## Troubleshooting

If `nave` is not found:

```bash
python setup.py
source ~/.zshrc
# or
source ~/.bashrc
which nave
```

If you want a direct fallback from the repo root:

```bash
PYTHONPATH=. python cli/main.py --help
```

If you need a clean rebuild:

```bash
rm -rf .venv
python setup.py
```

## Further Reading

- [docs/hermes_integration.md](docs/hermes_integration.md)
- [docs/agent_onboarding.md](docs/agent_onboarding.md)
- [docs/web3-setup.md](docs/web3-setup.md)
- [docs/technical.yaml](docs/technical.yaml)
- [docs/cot_integration.yaml](docs/cot_integration.yaml)
