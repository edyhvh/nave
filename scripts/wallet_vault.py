"""
Wallet Vault — secure local storage for BIP39 seed phrases and EVM wallet data.

Seed phrases are encrypted with Fernet (AES-128-CBC + HMAC-SHA256).
Vault key lives in ~/.secrets/nave-wallets/.vault_key (chmod 400, never committed).

Usage:
    vault = WalletVault()
    vault.store("ironclaw", mnemonic="word1 word2 ...", address="0x...", private_key="0x...")
    wallet = vault.load("ironclaw")
    print(wallet["address"])   # safe to print
    # private_key accessible only within vault.load() result — never log it
"""

import json
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet


VAULT_DIR = Path.home() / ".secrets" / "nave-wallets"
VAULT_KEY_FILE = VAULT_DIR / ".vault_key"


def _ensure_vault_dir() -> None:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(VAULT_DIR, stat.S_IRWXU)  # 700 — owner only


def _load_or_create_vault_key() -> Fernet:
    _ensure_vault_dir()
    if VAULT_KEY_FILE.exists():
        key = VAULT_KEY_FILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        VAULT_KEY_FILE.write_bytes(key)
        os.chmod(VAULT_KEY_FILE, stat.S_IRUSR)  # 400 — read-only by owner
    return Fernet(key)


class WalletVault:
    def __init__(self):
        self._fernet = _load_or_create_vault_key()

    def store(self, name: str, *, mnemonic: str, address: str, private_key: str) -> None:
        """Encrypt and persist wallet data. Never logs the private key."""
        _ensure_vault_dir()
        payload = json.dumps({
            "name": name,
            "address": address,
            "mnemonic": mnemonic,
            "private_key": private_key,
        }).encode()
        encrypted = self._fernet.encrypt(payload)
        wallet_file = VAULT_DIR / f"{name}.enc"
        wallet_file.write_bytes(encrypted)
        os.chmod(wallet_file, stat.S_IRUSR | stat.S_IWUSR)  # 600

    def load(self, name: str) -> dict:
        """Decrypt and return wallet data. Caller must handle private_key securely."""
        wallet_file = VAULT_DIR / f"{name}.enc"
        if not wallet_file.exists():
            raise FileNotFoundError(f"No wallet found for '{name}' in vault")
        encrypted = wallet_file.read_bytes()
        payload = self._fernet.decrypt(encrypted)
        return json.loads(payload)

    def address(self, name: str) -> str:
        """Return only the public address — safe for logging."""
        return self.load(name)["address"]

    def private_key(self, name: str) -> str:
        """Return private key — use only to sign, never log or print."""
        return self.load(name)["private_key"]

    def list_wallets(self) -> list[str]:
        """Return names of all stored wallets."""
        return [f.stem for f in VAULT_DIR.glob("*.enc")]

    def exists(self, name: str) -> bool:
        return (VAULT_DIR / f"{name}.enc").exists()


if __name__ == "__main__":
    import sys
    vault = WalletVault()
    if len(sys.argv) < 2:
        print("Stored wallets:", vault.list_wallets())
    elif sys.argv[1] == "address" and len(sys.argv) == 3:
        print(vault.address(sys.argv[2]))
    elif sys.argv[1] == "list":
        for name in vault.list_wallets():
            print(f"  {name}: {vault.address(name)}")
    else:
        print("Usage: wallet_vault.py [list | address <name>]")
