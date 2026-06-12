from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.config import CliDefaults, HyperliquidSettings
from trading.crypto.vault import SECRETS_POLICY_MESSAGE, WalletSecretAccessError, WalletVault
from trading.crypto.wallet_service import (
    DEFAULT_WALLET_NAMES,
    _trade_succeeded,
    claim_testnet_drip,
    create_wallet,
    generate_evm_wallet,
    get_account_status,
    list_wallets,
    run_test_trade,
    setup_default_wallets,
    validate_wallet_name,
    verify_testnet_trading,
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


def test_default_wallet_names_only_hermes() -> None:
    assert DEFAULT_WALLET_NAMES == ("hermes",)


def test_setup_default_wallets_skips_existing(temp_vault: WalletVault) -> None:
    create_wallet("hermes", vault=temp_vault)
    result = setup_default_wallets(vault=temp_vault)
    created_names = {record.name for record in result.created}
    assert "hermes" not in created_names
    assert "hermes" in result.skipped
    assert len(list_wallets(vault=temp_vault)) == 1


def test_vault_load_blocks_secret_export(temp_vault: WalletVault) -> None:
    create_wallet("hermes", vault=temp_vault)
    with pytest.raises(WalletSecretAccessError, match="never displayed"):
        temp_vault.load("hermes")


def test_show_mnemonic_script_refuses_to_export_secrets() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/show_mnemonic.py", "hermes"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert SECRETS_POLICY_MESSAGE in result.stdout
    assert "Recovery Phrase" not in result.stdout


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


def test_verify_testnet_trading_long_and_short(
    temp_vault: WalletVault,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_wallet("hermes", vault=temp_vault)

    class FakeClient:
        env = "TESTNET"
        address = "0xabc"

        def __init__(self, wallet_name: str, testnet: bool = True):
            self.wallet_name = wallet_name
            self.testnet = testnet
            self._open = False

        def get_account_state(self):
            return {"marginSummary": {"accountValue": "1000", "totalMarginUsed": "0"}}

        def get_open_positions(self):
            if not self._open:
                return []
            return [{"position": {"coin": "BTC", "szi": "0.001"}}]

        def get_open_orders(self):
            return []

        def get_mid(self, coin: str) -> float:
            return 2500.0

        def market_open(self, coin: str, side: str, size_usd: float):
            self._open = True
            return {
                "status": "ok",
                "response": {
                    "type": "order",
                    "data": {"statuses": [{"filled": {"totalSz": "0.001", "avgPx": "64000"}}]},
                },
            }

        def market_close(self, coin: str):
            self._open = False
            return {
                "status": "ok",
                "response": {
                    "type": "order",
                    "data": {"statuses": [{"filled": {"totalSz": "0.001", "avgPx": "64000"}}]},
                },
            }

    monkeypatch.setattr("trading.crypto.wallet_service.HyperliquidClient", FakeClient)

    result = verify_testnet_trading("hermes", vault=temp_vault)
    assert result["verified"] is True
    assert set(result["sides"]) == {"long", "short"}
    for side in ("long", "short"):
        assert result["sides"][side]["open_ok"] is True
        assert result["sides"][side]["close_ok"] is True


def test_claim_testnet_drip_reports_mainnet_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, json=None, timeout=15):
        if json and json.get("type") == "claimDrip":
            return FakeResponse(
                "Cannot claim drip because user 0xabc does not exist on mainnet."
            )
        raise AssertionError(f"unexpected post {url} {json}")

    monkeypatch.setattr("trading.crypto.wallet_service.requests.post", fake_post)
    result = claim_testnet_drip("0xabc")
    assert result.success is False
    assert "mainnet" in result.message.lower()


def test_trade_succeeded_detects_ok_and_err() -> None:
    assert _trade_succeeded({"status": "ok"}) is True
    assert _trade_succeeded({"status": "err", "response": "insufficient margin"}) is False
    assert _trade_succeeded(
        {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": {"totalSz": "0.00078", "avgPx": "64000"}}]},
            },
        }
    )
    assert not _trade_succeeded(
        {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"error": "Order has invalid size."}]},
            },
        }
    )


def test_run_test_trade_rejects_short_on_mainnet(temp_vault: WalletVault) -> None:
    create_wallet("hermes", vault=temp_vault)
    with pytest.raises(ValueError, match="testnet"):
        run_test_trade("hermes", testnet=False, vault=temp_vault)


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
