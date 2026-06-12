"""
Wallet setup script — generates BIP39 seed phrases and EVM wallets for
ironclaw, openfang, and hermes, then stores them securely in the local vault.

Run ONCE to generate wallets. If wallets already exist, it skips them.

    python scripts/setup_wallets.py

Recovery phrases are ONLY ever stored encrypted in ~/.secrets/nave-wallets/.
They are never printed, logged, or committed to git.

Prefer the CLI equivalent: nave wallet setup
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading.crypto.wallet_service import DEFAULT_WALLET_NAMES, setup_default_wallets
from trading.crypto.vault import WalletVault


def main() -> None:
    vault = WalletVault()
    result = setup_default_wallets(names=DEFAULT_WALLET_NAMES, vault=vault)

    print()
    if result.created:
        print("✅ Wallets created:")
        for record in result.created:
            print(f"   {record.name}: {record.address}")
        print()
        print("🔐 Seed phrases are encrypted in ~/.secrets/nave-wallets/")
        print("   Import into Phantom by running: python scripts/wallet_vault.py list")
        print("   To get seed phrase for import: python scripts/show_mnemonic.py <name>")

    if result.skipped:
        print(f"⏭  Skipped (already exist): {', '.join(result.skipped)}")

    print()
    print("Wallet addresses (safe to share):")
    for name in DEFAULT_WALLET_NAMES:
        if vault.exists(name):
            print(f"   {name}: {vault.address(name)}")


if __name__ == "__main__":
    print("🔑 Nave Wallet Setup")
    print("=" * 40)
    main()
