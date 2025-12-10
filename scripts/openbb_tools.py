#!/usr/bin/env python3
"""
OpenBB Tools - Unified script for all OpenBB-related operations
Consolidated from: check_openbb_capabilities.py, openbb_coverage_summary.py,
verify_partial_indicators.py, setup_api_keys.py, setup_openbb_keys.py,
verify_partial_indicators_detailed.py, analyze_partial_indicators.py,
explore_partial_indicators.py, verify_updated_indicators.py
"""

import sys
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from openbb import obb
    from dotenv import load_dotenv
    OPENBB_AVAILABLE = True
except ImportError:
    OPENBB_AVAILABLE = False

# Load environment variables
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)

def print_header(title):
    """Print a formatted header"""
    print("\n" + "="*60)
    print(f" {title}")
    print("="*60)

def check_openbb_installation():
    """Check if OpenBB is installed and working"""
    print_header("OpenBB Installation Check")

    if not OPENBB_AVAILABLE:
        print("❌ OpenBB is not installed")
        print("Install with: pip install -r requirements.txt")
        return False

    try:
        print("✅ OpenBB is installed")
        print(f"   Version: {getattr(obb, '__version__', 'Unknown')}")

        # Check available modules
        modules = [x for x in dir(obb) if not x.startswith('_')]
        print(f"   Available modules ({len(modules)}): {', '.join(modules[:10])}{'...' if len(modules) > 10 else ''}")

        return True
    except Exception as e:
        print(f"❌ Error checking OpenBB: {e}")
        return False

def show_openbb_capabilities():
    """Show detailed OpenBB capabilities"""
    print_header("OpenBB Capabilities")

    if not OPENBB_AVAILABLE:
        print("❌ OpenBB not available")
        return

    # Check key modules
    capabilities = {
        'economy': hasattr(obb, 'economy'),
        'crypto': hasattr(obb, 'crypto'),
        'fixedincome': hasattr(obb, 'fixedincome'),
        'equity': hasattr(obb, 'equity'),
        'commodity': hasattr(obb, 'commodity'),
        'currency': hasattr(obb, 'currency'),
        'etf': hasattr(obb, 'etf'),
        'regulators': hasattr(obb, 'regulators'),
        'derivatives': hasattr(obb, 'derivatives'),
    }

    print("Core modules:")
    for module, available in capabilities.items():
        status = "✅" if available else "❌"
        print(f"  {status} {module}")

    # Test some basic functionality
    print("\nTesting basic functionality:")

    try:
        # Test equity data
        print("  Testing equity data...")
        test = obb.equity.price.quote(symbol="AAPL")
        print("  ✅ Equity data working"    except:
        print("  ❌ Equity data failed"    try:
        # Test crypto data
        print("  Testing crypto data...")
        test = obb.crypto.price(symbol="BTC")
        print("  ✅ Crypto data working"    except:
        print("  ❌ Crypto data failed"    try:
        # Test economic data
        print("  Testing economic data...")
        test = obb.economy.fred_series(series_id="GDP")
        print("  ✅ Economic data working"    except:
        print("  ❌ Economic data failed"
def generate_coverage_summary():
    """Generate OpenBB coverage summary from fund.yaml"""
    print_header("OpenBB Coverage Summary")

    fund_path = project_root / "docs" / "fund.yaml"

    if not fund_path.exists():
        print(f"❌ File not found: {fund_path}")
        return

    with open(fund_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all indicators with their fields
    pattern = r'name:\s*(.+?)\n(?:[^\n]*\n)*?\s+openbb_available:\s*(Yes|Partial|No)'

    matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)

    stats = {'Yes': [], 'Partial': [], 'No': []}

    for match in matches:
        name = match.group(1).strip().strip("'\"")
        status = match.group(2)
        stats[status].append(name)

    # Print summary
    total = sum(len(indicators) for indicators in stats.values())

    print(f"Total indicators: {total}")
    print(f"✅ Fully available (Yes): {len(stats['Yes'])}")
    print(f"🟡 Partially available (Partial): {len(stats['Partial'])}")
    print(f"❌ Not available (No): {len(stats['No'])}")

    if stats['Partial']:
        print(f"\n🟡 Partial indicators ({len(stats['Partial'])}):")
        for indicator in stats['Partial']:
            print(f"  - {indicator}")

def verify_partial_indicators():
    """Verify what data is actually available for Partial indicators"""
    print_header("Verifying Partial Indicators")

    if not OPENBB_AVAILABLE:
        print("❌ OpenBB not available")
        return

    print("Testing key partial indicators...")

    # Test some key partial indicators
    tests = [
        ("US Treasury yields", lambda: obb.fixedincome.rate(symbol="DGS10")),
        ("ETF flows", lambda: obb.crypto.etf.symbols()),
        ("Capital flows", lambda: obb.economy.balance_of_payments(country="US")),
    ]

    for name, test_func in tests:
        try:
            print(f"  Testing {name}...")
            result = test_func()
            if result and len(result) > 0:
                print(f"  ✅ {name}: Data available")
            else:
                print(f"  ⚠️  {name}: No data returned")
        except Exception as e:
            print(f"  ❌ {name}: Error - {str(e)[:100]}")

def setup_api_keys():
    """Setup API keys for OpenBB"""
    print_header("OpenBB API Key Setup")

    print("OpenBB API keys can be set in several ways:")
    print("1. Environment variables (.env file)")
    print("2. OpenBB account login")
    print("3. Direct configuration")

    if OPENBB_AVAILABLE:
        print("\nTo login to OpenBB account:")
        print("  from openbb import obb")
        print("  obb.account.login()")
    else:
        print("\n❌ OpenBB not available - install first")

def run_mstr_proxy():
    """Run MSTR proxy analysis"""
    print_header("MSTR Proxy Analysis")

    if not OPENBB_AVAILABLE:
        print("❌ OpenBB not available")
        return

    print("⚠️  MSTR proxy analysis not yet implemented")
    print("   This feature requires additional development")

def run_treasury_yields():
    """Run Treasury Yields analysis"""
    print_header("Treasury Yields Analysis")

    if not OPENBB_AVAILABLE:
        print("❌ OpenBB not available")
        return

    print("⚠️  Treasury yields analysis not yet implemented")
    print("   This feature requires additional development")

def main():
    """Main menu"""
    while True:
        print_header("OpenBB Tools - Unified Interface")
        print("Choose an option:")
        print("1. Check OpenBB installation")
        print("2. Show OpenBB capabilities")
        print("3. Generate coverage summary")
        print("4. Verify partial indicators")
        print("5. Setup API keys")
        print("6. Run MSTR proxy analysis")
        print("7. Run Treasury yields analysis")
        print("0. Exit")

        try:
            choice = input("\nEnter choice (0-7): ").strip()

            if choice == "0":
                print("Goodbye!")
                break
            elif choice == "1":
                check_openbb_installation()
            elif choice == "2":
                show_openbb_capabilities()
            elif choice == "3":
                generate_coverage_summary()
            elif choice == "4":
                verify_partial_indicators()
            elif choice == "5":
                setup_api_keys()
            elif choice == "6":
                run_mstr_proxy()
            elif choice == "7":
                run_treasury_yields()
            else:
                print("❌ Invalid choice")

            input("\nPress Enter to continue...")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()