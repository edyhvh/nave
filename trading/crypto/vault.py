"""
Wallet Vault — secure local storage for BIP39 seed phrases and EVM wallet data.

Seed phrases are encrypted with Fernet (AES-128-CBC + HMAC-SHA256).
The vault key lives in ~/.secrets/nave-wallets/.vault_key (chmod 400).
Wallet files live in ~/.secrets/nave-wallets/<name>.enc (chmod 600).

SECURITY RULES:
  - Vault directory is never committed to git.
  - Private keys are loaded only in memory when needed for signing.
  - Never log, print, or pass private_key to anything except a signer.

Usage:
    from trading.crypto.vault import WalletVault

    vault = WalletVault()
    print(vault.address("openfang"))   # safe — public address only

    # For signing only (keep in memory, never log):
    key = vault.private_key("openfang")
    account = eth_account.Account.from_key(key)
    del key  # discard after use
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
    """Fernet-encrypted wallet store. Thread-safe for reads; writes are serialized by the OS."""

    def __init__(self, vault_dir: Path | None = None):
        self._vault_dir = vault_dir or VAULT_DIR
        self._fernet = _load_or_create_vault_key()

    def store(self, name: str, *, mnemonic: str, address: str, private_key: str) -> None:
        """Encrypt and persist wallet data. Private key is never logged."""
        _ensure_vault_dir()
        payload = json.dumps({
            "name": name,
            "address": address,
            "mnemonic": mnemonic,
            "private_key": private_key,
        }).encode()
        encrypted = self._fernet.encrypt(payload)
        wallet_file = self._vault_dir / f"{name}.enc"
        wallet_file.write_bytes(encrypted)
        os.chmod(wallet_file, stat.S_IRUSR | stat.S_IWUSR)  # 600

    def load(self, name: str) -> dict:
        """Decrypt and return full wallet dict. Handle private_key with care."""
        wallet_file = self._vault_dir / f"{name}.enc"
        if not wallet_file.exists():
            raise FileNotFoundError(
                f"No wallet found for '{name}'. Run: python scripts/setup_wallets.py"
            )
        return json.loads(self._fernet.decrypt(wallet_file.read_bytes()))

    def address(self, name: str) -> str:
        """Return only the public address — safe to log or display."""
        return self.load(name)["address"]

    def private_key(self, name: str) -> str:
        """Return private key for signing. Never log or store the return value."""
        return self.load(name)["private_key"]

    def list_wallets(self) -> list[str]:
        """Return names of all stored wallets."""
        return [f.stem for f in self._vault_dir.glob("*.enc")]

    def exists(self, name: str) -> bool:
        return (self._vault_dir / f"{name}.enc").exists()
