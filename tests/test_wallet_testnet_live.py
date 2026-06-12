"""Optional live Hyperliquid testnet verification.

Skipped automatically when the hermes wallet is missing or unfunded.
Set RUN_TESTNET_LIVE=1 to force the attempt even when equity is zero.
"""

from __future__ import annotations

import os

import pytest

from trading.crypto.vault import WalletVault
from trading.crypto.wallet_service import (
    DEFAULT_TEST_COIN,
    DEFAULT_TEST_SIZE_USD,
    DEFAULT_WALLET_NAME,
    get_account_status,
    verify_testnet_trading,
)


pytestmark = pytest.mark.integration


def _should_run_live() -> bool:
    return os.getenv("RUN_TESTNET_LIVE", "").strip().lower() in {"1", "true", "yes"}


@pytest.mark.skipif(not _should_run_live(), reason="Set RUN_TESTNET_LIVE=1 to run live testnet trades")
def test_live_testnet_long_and_short_round_trips() -> None:
    vault = WalletVault()
    if not vault.exists(DEFAULT_WALLET_NAME):
        pytest.skip(f"Wallet '{DEFAULT_WALLET_NAME}' not found. Run: nave wallet setup")

    status = get_account_status(DEFAULT_WALLET_NAME, testnet=True, vault=vault)
    if status.equity_usd < DEFAULT_TEST_SIZE_USD + 100:
        pytest.skip(
            f"Testnet wallet unfunded (${status.equity_usd:.2f}). "
            "Fund via https://app.hyperliquid-testnet.xyz/drip"
        )

    result = verify_testnet_trading(
        DEFAULT_WALLET_NAME,
        coin=DEFAULT_TEST_COIN,
        size_usd=DEFAULT_TEST_SIZE_USD,
        vault=vault,
    )
    assert result["verified"] is True
