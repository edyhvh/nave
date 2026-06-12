from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config import CliDefaults, HyperliquidSettings
from trading.crypto.vault import WalletVault
from trading.crypto.wallet_service import (
    create_wallet,
    generate_evm_wallet,
    get_account_status,
    list_wallets,
    setup_default_wallets,
    validate_wallet_name,
)


@pytest.fixture
def temp_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WalletVault:
    vault_dir = tmp_path / "wallets"
    vault_dir.mkdir()
    key_file = vault_dir / ".vault_key"
    monkeypatch.setattr("trading.crypto.vault.VAULT_DIR", vault_dir)
    monkeypatch.setattr("trading.crypto.vault.VAULT_KEY_FILE", key_file)
    return WalletVault(vault_dir=vault_dir)


def test_validate_wallet_name_normalizes_and_rejects_invalid() -> None:
    assert validate_wallet_name("OpenFang") == "openfang"
    with pytest.raises(ValueError):
        validate_wallet_name("bad name")


def test_generate_evm_wallet_has_expected_fields() -> None:
    wallet = generate_evm_wallet()
    assert wallet["address"].startswith("0x")
    assert len(wallet["mnemonic"].split()) == 24
    assert len(wallet["private_key"]) == 64


def test_create_wallet_persists_record(temp_vault: WalletVault) -> None:
    record = create_wallet("trading", vault=temp_vault)
    assert record.name == "trading"
    assert temp_vault.address("trading") == record.address


def test_create_wallet_rejects_duplicate(temp_vault: WalletVault) -> None:
    create_wallet("trading", vault=temp_vault)
    with pytest.raises(FileExistsError):
        create_wallet("trading", vault=temp_vault)


def test_setup_default_wallets_skips_existing(temp_vault: WalletVault) -> None:
    create_wallet("hermes", vault=temp_vault)
    result = setup_default_wallets(vault=temp_vault)
    created_names = {record.name for record in result.created}
    assert "hermes" not in created_names
    assert "hermes" in result.skipped
    assert len(list_wallets(vault=temp_vault)) == 3


def test_hyperliquid_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HL_WALLET", "openfang")
    monkeypatch.setenv("HL_TESTNET", "false")
    monkeypatch.setenv("HL_MAX_POSITION_USD", "250")
    monkeypatch.setenv("HL_MIN_CONFIDENCE", "0.75")

    settings = HyperliquidSettings.from_env()
    assert settings.wallet == "openfang"
    assert settings.testnet is False
    assert settings.max_position_usd == 250.0
    assert settings.min_confidence == 0.75


def test_cli_defaults_wallet_follows_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HL_WALLET", "ironclaw")
    defaults = CliDefaults.from_env()
    assert defaults.wallet == "ironclaw"


def test_get_account_status_uses_client(monkeypatch: pytest.MonkeyPatch, temp_vault: WalletVault) -> None:
    record = create_wallet("paper", vault=temp_vault)

    class FakeClient:
        def __init__(self, wallet_name: str, testnet: bool = True):
            self.wallet_name = wallet_name
            self.testnet = testnet
            self.address = record.address
            self.env = "TESTNET" if testnet else "MAINNET"

        def get_account_state(self):
            return {"marginSummary": {"accountValue": "123.45", "totalMarginUsed": "10"}}

        def get_open_positions(self):
            return [{"position": {"coin": "ETH"}}]

        def get_open_orders(self):
            return []

    monkeypatch.setattr("trading.crypto.wallet_service.HyperliquidClient", FakeClient)

    status = get_account_status("paper", testnet=True, vault=temp_vault)
    assert status.wallet == "paper"
    assert status.equity_usd == 123.45
    assert status.position_count == 1
    assert status.funded is True


def test_wallet_cli_create_and_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    vault_dir = tmp_path / "wallets"
    vault_dir.mkdir()
    key_file = vault_dir / ".vault_key"
    monkeypatch.setattr("trading.crypto.vault.VAULT_DIR", vault_dir)
    monkeypatch.setattr("trading.crypto.vault.VAULT_KEY_FILE", key_file)

    from cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["wallet", "create", "--name", "demo"])
    assert result.exit_code == 0, result.stdout
    assert "Created wallet 'demo'" in result.stdout

    result = runner.invoke(app, ["wallet", "list", "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload[0]["name"] == "demo"
