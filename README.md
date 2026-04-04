# Nave

[... previous content ... keep all]

## Trading on Hyperliquid

[... keep ...]

### Weekly COT Workflow (New!)

**Sunday Driver:** Analyzes CME COT reports (BTC/ETH) as FITS Sentiment bias.

```bash
./run.sh weekly-cot
```

**Output:** Markdown report with:
- COT net positions, %OI changes.
- BTC vs ETH comparison → best asset.
- Position sizing ($2000 ex.), leverage (conf-scaled 1-10x).
- 75% retrace/FVG setups on 4H/1H.
- Hyperliquid perp scans (liq, funding).
- Risk mgmt per technical.yaml (SL invalidation, R:R).

**Philosophy Integration:** COT → weekly premise. Aligns regressions/pullbacks, confluence/mitigation blocks.

See `docs/cot_integration.yaml` for config/rules.

## Project Structure (Updated)

```
trading/
├── cot/                 # NEW: COT fetch/analyze (FITS Sentiment)
│   ├── __init__.py
│   ├── cot_fetcher.py
│   └── cot_analyzer.py
├── signals.py           # + CotSignalProducer, perp scan
└── strategy.py          # + CotWeeklyStrategy
scripts/weekly_cot_analysis.py  # Sunday CLI
docs/cot_integration.yaml       # Philosophy tie-in
```

[... troubleshooting keep ...]