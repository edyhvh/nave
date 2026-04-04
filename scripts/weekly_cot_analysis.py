#!/usr/bin/env python3
"""
Nave Weekly COT Analysis - Sunday Trading Setup Generator

This script runs the complete weekly COT analysis workflow:
1. Fetches latest COT data for BTC and ETH
2. Compares setups using FITS framework
3. Generates position sizing recommendations
4. Scans Hyperliquid perps for additional opportunities
5. Outputs a comprehensive markdown report

Usage:
    ./run.sh weekly-cot
    
    Or directly:
    python scripts/weekly_cot_analysis.py [--live] [--capital 5000]

Environment:
    Set HYPERLIQUID_WALLET for live trading (otherwise uses testnet)
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: rich not installed. Install with: pip install rich")

from trading.client import HyperliquidClient
from trading.strategy import CotWeeklyStrategy
from trading.signals import generate_weekly_signals


def print_plain_report(report: str) -> None:
    """Print report without rich formatting."""
    print(report)


def print_rich_report(report: str, result: dict) -> None:
    """Print report with rich formatting."""
    console = Console()
    
    # Print header panel
    console.print(Panel(
        "[bold cyan]Nave Weekly COT Analysis[/bold cyan]\n"
        "[dim]Commitment of Traders as Primary Weekly Driver[/dim]",
        border_style="cyan"
    ))
    
    # Print main report
    md = Markdown(report)
    console.print(md)
    
    # Print summary table
    if result.get('sizing'):
        sizing = result['sizing']
        table = Table(title="Position Summary", border_style="green")
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="yellow")
        
        table.add_row("Asset", result['best_asset'])
        table.add_row("Direction", sizing.direction.value.upper())
        table.add_row("Size", f"${sizing.size_usd:,.0f}")
        table.add_row("Leverage", f"{sizing.leverage:.1f}x")
        table.add_row("Risk", f"${sizing.risk_usd:.0f} ({sizing.risk_pct*100:.0f}%)")
        table.add_row("R:R", f"{sizing.expected_rr:.1f}:1")
        table.add_row("Instrument", sizing.instrument.upper())
        
        console.print(table)
    
    # Print status
    if result.get('execution_results'):
        console.print(f"\n[green]✓[/green] Analysis complete. {len(result['execution_results'])} position(s) evaluated.")


def main():
    parser = argparse.ArgumentParser(
        description="Nave Weekly COT Analysis - Generate Sunday trading setups"
    )
    parser.add_argument(
        '--live', 
        action='store_true',
        help='Enable live trading (default: dry-run)'
    )
    parser.add_argument(
        '--capital',
        type=float,
        default=2000.0,
        help='Trading capital in USD (default: 2000)'
    )
    parser.add_argument(
        '--risk',
        type=float,
        default=0.10,
        help='Risk per trade as decimal (default: 0.10 = 10%%)'
    )
    parser.add_argument(
        '--wallet',
        type=str,
        default='openfang',
        help='Wallet name from vault (default: openfang)'
    )
    parser.add_argument(
        '--plain',
        action='store_true',
        help='Plain text output (no rich formatting)'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.5,
        help='Minimum confidence threshold (default: 0.5)'
    )
    
    args = parser.parse_args()
    
    # Initialize client
    try:
        client = HyperliquidClient(
            wallet_name=args.wallet,
            testnet=not args.live
        )
    except Exception as e:
        print(f"Error initializing client: {e}")
        print("Running in analysis-only mode (no price data)")
        client = None
    
    # Initialize strategy
    strategy = CotWeeklyStrategy(
        client=client,
        capital_usd=args.capital,
        risk_pct=args.risk,
        dry_run=not args.live,
        min_confidence=args.min_confidence
    )
    
    # Run analysis
    print("Fetching COT data and generating signals...")
    print()
    
    try:
        result = strategy.run_weekly_analysis()
        report = result['report']
        
        # Output report
        if RICH_AVAILABLE and not args.plain:
            print_rich_report(report, result)
        else:
            print_plain_report(report)
        
        # Exit code based on signal quality
        if result['best_signal'] and result['best_signal'].confidence >= args.min_confidence:
            return 0
        else:
            print("\n[!] No high-confidence signal generated.")
            return 1
            
    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
