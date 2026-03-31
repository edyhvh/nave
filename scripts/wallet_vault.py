"""
Compatibility shim — re-exports WalletVault from trading.vault.

The authoritative implementation lives in trading/vault.py.
This file exists so standalone scripts in scripts/ can be run directly.
"""

import sys
from pathlib import Path

# Add repo root to path so `trading` package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading.vault import WalletVault, VAULT_DIR, VAULT_KEY_FILE  # noqa: F401


if __name__ == "__main__":
    vault = WalletVault()
    if len(sys.argv) < 2 or sys.argv[1] == "list":
        wallets = vault.list_wallets()
        if not wallets:
            print("No wallets found. Run: python scripts/setup_wallets.py")
        else:
            for name in wallets:
                print(f"  {name}: {vault.address(name)}")
    elif sys.argv[1] == "address" and len(sys.argv) == 3:
        print(vault.address(sys.argv[2]))
    else:
        print("Usage: python scripts/wallet_vault.py [list | address <name>]")
