"""
Utility to safely reveal a mnemonic phrase for wallet import into Phantom.

USE CAREFULLY — only run this in a private terminal session.
The phrase is printed once and cleared. Never pipe output to a file or log.

    python scripts/show_mnemonic.py ironclaw
    python scripts/show_mnemonic.py openfang
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading.vault import WalletVault


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/show_mnemonic.py <wallet-name>")
        print("       wallet-name: ironclaw | openfang")
        sys.exit(1)

    name = sys.argv[1]
    vault = WalletVault()

    if not vault.exists(name):
        print(f"❌ No wallet found for '{name}'. Run setup_wallets.py first.")
        sys.exit(1)

    wallet = vault.load(name)

    print()
    print("⚠️  SENSITIVE — do not share, screenshot, or copy to clipboard on shared systems")
    print("=" * 60)
    print(f"Wallet:  {name}")
    print(f"Address: {wallet['address']}")
    print()
    print("Recovery Phrase (24 words):")
    words = wallet["mnemonic"].split()
    for i, word in enumerate(words, 1):
        print(f"  {i:2}. {word}")
    print("=" * 60)
    print()
    print("This output will self-clear in 60 seconds...")
    time.sleep(60)
    print("\033[H\033[J", end="")  # clear terminal
    print("✅ Cleared.")


if __name__ == "__main__":
    main()
