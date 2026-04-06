#!/usr/bin/env python3
"""
Backtest runner for COT strategy.

Usage:
    python run_backtests.py --objective setup-discovery
    python run_backtests.py --objective strategy-validation
    python run_backtests.py --all

This script runs the backtest tests and generates reports.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def run_setup_discovery():
    """Run setup discovery optimization tests."""
    print("=" * 60)
    print("SETUP DISCOVERY OPTIMIZATION")
    print("=" * 60)
    print()
    print("Objective: Find optimal COT signal parameters")
    print()
    
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", "test_setup_discovery.py", "-v", "-s"],
        cwd=Path(__file__).parent,
        capture_output=False
    )
    return result.returncode


def run_strategy_validation():
    """Run full strategy validation tests."""
    print("=" * 60)
    print("STRATEGY VALIDATION")
    print("=" * 60)
    print()
    print("Objective: Validate complete CotWeeklyStrategy")
    print()
    
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", "test_strategy.py", "-v", "-s"],
        cwd=Path(__file__).parent,
        capture_output=False
    )
    return result.returncode


def run_all():
    """Run all backtest tests."""
    print("=" * 60)
    print("COMPLETE BACKTEST SUITE")
    print("=" * 60)
    print()
    
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", ".", "-v", "--tb=short"],
        cwd=Path(__file__).parent,
        capture_output=False
    )
    return result.returncode


def generate_report():
    """Generate HTML report from test results."""
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", ".", "--html=backtest_report.html", "--self-contained-html"],
        cwd=Path(__file__).parent,
        capture_output=False
    )
    print(f"\nReport generated: {Path(__file__).parent / 'backtest_report.html'}")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Run COT strategy backtests")
    parser.add_argument(
        "--objective",
        choices=["setup-discovery", "strategy-validation"],
        help="Which objective to run"
    )
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--report", action="store_true", help="Generate HTML report")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only")
    
    args = parser.parse_args()
    
    if args.report:
        return generate_report()
    
    if args.objective == "setup-discovery":
        return run_setup_discovery()
    elif args.objective == "strategy-validation":
        return run_strategy_validation()
    elif args.all:
        return run_all()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
