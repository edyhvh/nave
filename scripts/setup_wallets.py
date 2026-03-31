"""
Wallet setup script — generates BIP39 seed phrases and EVM wallets for
ironclaw and openfang, then stores them securely in the local vault.

Run ONCE to generate wallets. If wallets already exist, it skips them.

    python scripts/setup_wallets.py

Recovery phrases are ONLY ever stored encrypted in ~/.secrets/nave-wallets/.
They are never printed, logged, or committed to git.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from wallet_vault import WalletVault


WALLETS = ["ironclaw", "openfang"]


def generate_evm_wallet() -> dict:
    """Generate a new BIP39 mnemonic and derive an EVM HD wallet from it."""
    from mnemonic import Mnemonic
    from eth_account import Account

    Account.enable_unaudited_hdwallet_features()
    mnemo = Mnemonic("english")
    mnemonic = mnemo.generate(strength=256)  # 24-word phrase
    acct = Account.from_mnemonic(mnemonic, account_path="m/44'/60'/0'/0/0")
    return {
        "mnemonic": mnemonic,
        "address": acct.address,
        "private_key": acct.key.hex(),
    }


def main() -> None:
    vault = WalletVault()
    generated = []
    skipped = []

    for name in WALLETS:
        if vault.exists(name):
            skipped.append(name)
            continue

        print(f"  Generating wallet for '{name}'...")
        wallet = generate_evm_wallet()
        vault.store(
            name,
            mnemonic=wallet["mnemonic"],
            address=wallet["address"],
            private_key=wallet["private_key"],
        )
        generated.append((name, wallet["address"]))

    print()
    if generated:
        print("✅ Wallets created:")
        for name, address in generated:
            print(f"   {name}: {address}")
        print()
        print("🔐 Seed phrases are encrypted in ~/.secrets/nave-wallets/")
        print("   Import into Phantom by running: python scripts/wallet_vault.py list")
        print("   To get seed phrase for import: python scripts/show_mnemonic.py <name>")

    if skipped:
        print(f"⏭  Skipped (already exist): {', '.join(skipped)}")

    print()
    print("Wallet addresses (safe to share):")
    for name in WALLETS:
        if vault.exists(name):
            print(f"   {name}: {vault.address(name)}")


if __name__ == "__main__":
    print("🔑 Nave Wallet Setup")
    print("=" * 40)
    main()
