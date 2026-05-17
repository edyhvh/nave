<p align="center">
	<img src="design/assets/logo_round.png" alt="NAVE logo" width="140" />
</p>

<h1 align="center">NAVE</h1>

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

Back-compat: the legacy top-level paths (`trading.client`, `trading.signals`,
`trading.cot.cot_analyzer`, …) keep working via `sys.modules` aliases set up
by `trading/_compat.py`, so scripts/, tests/, cli/, and hermes/integration.py
continue to import the crypto stack unchanged.

## Stocks workflow (ISM + FMP)

```bash
# 1. Install extra deps
pip install -r requirements.txt

# 2. Add your FMP API key to .env
FMP_API_KEY=your_key

# Optional: override the cache / budget controls
FMP_CACHE_TTL_SECONDS=86400

# 3. Fetch the latest ISM Manufacturing report
nave stocks ism-scan --kind manufacturing
nave stocks ism-scan --kind services --json

# 4. Run the full screener (ISM → fundamentals → ranked plan)
nave stocks screen --kind manufacturing --top-n 5 --capital 10000
nave stocks screen --kind manufacturing --top-n 5 --max-pe 28 --min-eps-growth 8
nave stocks screen --kind manufacturing --top-n 5 --max-pe 28 --min-eps-growth 8 --min-confidence 0.7

# 4b. Services mode — long-term revenue growth + PE-relative filter
nave stocks screen --kind services --mode services --top-n 5
nave stocks ism-report --kind services --mode services --sheet

# 5. Override the ticker universe (keep it lean to respect the 250-call/day cap)
nave stocks screen --universe-json '{"Industrials": ["GE","CAT"]}'

# 6. Build complete ISM report (hottest/worst industries + filtered picks)
nave stocks ism-report --kind manufacturing --top-n 5 --max-pe 28 --min-eps-growth 8
nave stocks ism-report --kind manufacturing --top-n 5 --max-pe 28 --min-eps-growth 8 --min-confidence 0.7
nave stocks ism-report --json
nave stocks ism-report --sheet
nave stocks ism-report --telegram-markdown-v2
nave stocks ism-report --json --sheet

# Default report view targets up to 10 longs + 10 shorts, but may return fewer
# after confidence and valuation filters.
# Output now includes company industry, driver ISM industry, confidence,
# industry/sector PE context, and EPS source metadata.
nave stocks ism-report --kind manufacturing
nave stocks ism-report --kind manufacturing --min-confidence 0.5

# 7. Stock-only journal stats (crypto trades excluded)
nave stocks journal-stats
```

**ISM data sources**: default path uses `httpx + BeautifulSoup` against
the public ISM press releases — no browser dependency. Pass
`--playwright` to `stocks ism-scan` for a JS-rendered mirror (requires
`pip install playwright && python -m playwright install chromium`).

**Fundamentals data source**: ISM stock screening now uses Financial Modeling
Prep via `FMP_API_KEY`. The client keeps a persistent cache under `var/fmp_cache/`
so repeat CLI/Hermes/MCP runs do not burn the 250 calls/day quota unnecessarily.
For Telegram/reminder workflows, prefer the preformatted `--telegram-markdown-v2`
output and keep chat-based schedules at or above hourly cadence.

### Screening modes

The screener supports two ranking strategies via `--mode` (defaults to the
value of `--kind`):

- **`--mode manufacturing`** *(default)* — ranks purely by EPS growth
  next year. Confidence = `0.6 × ISM industry-match + 0.4 × EPS confidence`.
  Unchanged from the original flow.
- **`--mode services`** — ranks by **long-term revenue growth forecast**
  (FMP analyst-estimate CAGR, yfinance trailing `revenueGrowth` as
  fallback) and drops names where `company PE ≥ sector average PE`
  (a secondary PE-relative check). No other scoring.

Example Services-mode output (truncated):

```
ISM Services — March 2026
Mode: services
Criteria: mode=services, top_n=5, min_eps_growth=None, min_conf=0.3

Top longs (hottest sectors)
┃ Symbol ┃ Name    ┃ Side ┃ Sector                 ┃ Rev LT % ┃ Rev src                 ┃ Score ┃
│ GOOGL  │ Alphabet│ long │ Communication Services │   18.0   │ fmp_analyst_estimate    │ +0.180│
│ META   │ Meta    │ long │ Communication Services │   12.0   │ fmp_analyst_estimate    │ +0.120│
│ DIS    │ Disney  │ long │ Communication Services │    6.0   │ yfinance_trailing_...   │ +0.060│
```

**Brokers**: `AlpacaBroker` and `OndoBroker` are stubs. All read/write
methods raise `NotImplementedError` until the real integrations land,
which is safe because the strategy defaults to `dry_run=True`.

### Professional CLI behavior (Typer)

The CLI uses a custom `ProfessionalTyper` wrapper that prints command
start/success/fail status lines (to stderr) with elapsed time.

```bash
# Disable status lines for clean script logs
NAVE_CLI_STATUS=0 nave stocks ism-report --json

# Re-enable (default)
NAVE_CLI_STATUS=1 nave stocks ism-report --json
```

Typer itself does not automatically render JSON as a table. In Nave, use
`--sheet` for human-readable terminal tables and `--json` for machine output.

For stocks reports, `--min-confidence` defaults to `0.7`. Lower it if you want
to inspect weaker matches, but the stricter default is intended to block false
positives where a company shares a broad sector with an ISM industry but does
not actually belong to that industry.

The same confidence filter now applies to `nave stocks screen`, so strategy
plans and reports use the same false-positive guardrail by default.

## Trading on Hyperliquid

Nave integrates with [Hyperliquid](https://hyperliquid.xyz) for futures paper
trading. Wallets are managed locally via an encrypted vault — no MetaMask or
browser required.

### Quick start

```bash
# 1. Generate wallets (one-time)
python scripts/setup_wallets.py

# 2. Check account state on testnet
python -m trading.client summary --wallet hermes

# 3. Run a strategy in dry-run mode (no real orders)
python -m trading.strategy --wallet hermes --coins BTC ETH
```

### Weekly COT Analysis

COT is now the **main weekly driver** for trading setups.

```bash
# Run weekly analysis (Sunday)
python scripts/weekly_cot_analysis.py --capital 2000 --paper

# Historical variation report (last 3 calendar months)
python scripts/weekly_cot_analysis.py --capital 2000 --cot-history 3

# Or with live execution (careful!)
python scripts/weekly_cot_analysis.py --capital 2000 --live --wallet hermes

# Unified CLI
nave trading run --paper --strategy cot-weekly
```

**Features**:

- Fetches latest CME COT for BTC (133741) and ETH
- Compares setups using F.I.T.S. + IPDA philosophy (75% retracement, order blocks, etc.)
- Recommends best asset + capital allocation, leverage, SL/TP
- Scans other Hyperliquid perps for liquidity/funding opportunities
- Dry-run by default

See `docs/technical.yaml` for full philosophy and `trading/crypto/cot/` for
the COT pipeline implementation. The full theory-refinement workflow that
produced theory_v2 is described in `AGENTS.md`.

### Wallets

Two EVM wallets are pre-generated for the trading agents:

| Agent      | Address                                                 |
| ---------- | ------------------------------------------------------- |
| `openfang` | `0x48b6cB6ea38D48304B5bc634294be4F0EFC52b51`            |
| `ironclaw` | `0x3fB31b355b82B6B1421dBb914364c0Ec5e72868F`            |
| `hermes`   | Generated locally via `python scripts/setup_wallets.py` |

Private keys and seed phrases are encrypted in `~/.secrets/nave-wallets/`
and never committed to this repository.

For full setup instructions see **[docs/web3-setup.md](docs/web3-setup.md)**.

## Unified CLI

After setup (`python setup.py`), use the professional `nave` CLI (powered by Typer):

```bash
nave --help
nave version
nave trading run-strategy --wallet hermes --dry-run
nave trading run --strategy cot-weekly --paper
nave api start --reload
nave mcp run
nave cot analyze --coins BTC ETH
nave data fetch aaii
nave hermes tools
nave hermes call --tool cot_report --args-json '{"coins": "BTC ETH"}'
nave stocks ism-report --kind manufacturing --top-n 5 --min-confidence 0.7 --sheet
```

This unifies all previous scripts, strategies, MCP, and backend. Legacy `./run.sh` and `python -m trading.*` still work.

## Hermes Agent Integration

Nave now exposes a dedicated Hermes integration layer designed for MCP and
gateway workflows with structured JSON outputs.

### Skill/Tool Discovery

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

Evaluate an exact manual bull put credit spread when you already have target
strikes/premiums:

```bash
nave options analyze --ticker MSFT --strategy bull-put \
  --short-put 395 --long-put 390 \
  --short-premium 8.50 --long-premium 6.90 \
  --expiration 2026-06-18
```

If you omit `--short-premium` or `--long-premium`, the analyzer uses the option
chain mid price for that leg when the strike is available.

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

Scan the default liquid S&P 500 top-100 options universe and return only
tickers whose analysis passes the executable trade quality gate:

```bash
nave options analyze --sp500-scan --sp500-limit 100 --top-trades 3
nave options analyze --sp500-scan --sp500-limit 100 --top-trades 3 --json
nave options analyze --sp500-scan --sp500-limit 100 --top-trades 3 --scan-workers 8 --terminal
```

This keeps single-ticker analysis unchanged. In scan mode, the command runs the
same per-ticker analyzer, filters for `trade_decision.status=trade_candidate`,
and ranks the top executable setups by score, EV, PoP, and lower touch risk. For
human output, the scan shows live progress and then prints detail panels for the
top trades. Use `--scan-workers` to tune concurrency; lower it if your data
provider starts rate-limiting.

Use Deribit-backed options data for BTC/ETH while keeping the same options output flow:

```bash
nave options analyze BTC --source deribit --days-to-exp 30
nave options analyze ETH --source deribit --days-to-exp 30 --json
nave options opportunities --coins BTC,ETH --source deribit
nave options opportunities --coins BTC,ETH --source deribit --json
nave options analyze BTC --source deribit --terminal
```

Scan BTC/ETH momentum-filtered options opportunities from the options module:

```bash
nave options opportunities --coins BTC,ETH
nave options opportunities --coins BTC,ETH --sheet
nave options opportunities --coins BTC,ETH --json
```

### Agent and service workflow

Useful operational commands:

```bash
nave hermes tools
nave hermes call --tool options_scan --args-json '{"ticker": "MSFT", "days_to_exp": 30}'
nave hermes call --tool options_scan --args-json '{"ticker": "BTC", "days_to_exp": 30, "source": "deribit"}'
nave hermes call --tool options_opportunities --args-json '{"coins": "BTC,ETH", "days_to_exp": 30}'
nave hermes call --tool options_opportunities --args-json '{"coins": "BTC,ETH", "days_to_exp": 30, "source": "deribit"}'
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
