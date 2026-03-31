"""
Compatibility shim — re-exports HyperliquidClient from trading.client.

The authoritative implementation lives in trading/client.py.
Run as a CLI: python scripts/hyperliquid_client.py summary --wallet openfang
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading.client import HyperliquidClient  # noqa: F401

if __name__ == "__main__":
    from trading.client import __name__ as _
    import runpy
    runpy.run_module("trading.client", run_name="__main__", alter_sys=True)
