#!/usr/bin/env python3
\"\"\"Weekly COT analysis - Sunday driver for Nave trading setups.\"\"\"
import sys
from rich.console import Console
from rich.markdown import Markdown
from trading.strategy import CotWeeklyStrategy
from trading.client import HyperliquidClient

console = Console()

def main():
    client = HyperliquidClient(wallet_name=\"openfang\", testnet=True)
    strategy = CotWeeklyStrategy(client, capital_usd=2000.0, dry_run=True)
    
    report = strategy.weekly_report()
    md = Markdown(report)
    console.print(md)
    
    # Execute dry-run
    signals = strategy.compute_signals()
    strategy.execute_signals(signals)
    print(\"\\n✅ Weekly analysis complete. Review report above for allocations.\")

if __name__ == \"__main__\":
    main()