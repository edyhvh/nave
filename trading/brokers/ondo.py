"""
Ondo Finance broker — **stub**.

Ondo brings RWA tokens (USDY, OUSG) and permissioned equities exposure
on-chain. This adapter reserves the namespace; the actual wiring needs a
signed wallet + Ondo KYC onboarding, which is out of scope for the
ISM-driven stock workflow landing in this PR.

Intended surface when implemented:
  - Price quotes for listed RWA tokens + tokenized equities
  - Subscribe/redeem legs (primary-market) and secondary AMM swaps
  - Position reads reuse the crypto ``WalletVault`` for EVM signing
"""

from __future__ import annotations

import logging
import os
from typing import Any

from trading.base.broker import BaseBroker, BrokerResponse, OrderSide

logger = logging.getLogger(__name__)


class OndoBroker(BaseBroker):
    """Stub broker for Ondo Finance (RWA + tokenized equities)."""

    name = "ondo"

    def __init__(
        self,
        wallet_name: str | None = None,
        *,
        network: str = "ethereum",
    ):
        self.wallet_name = wallet_name or os.getenv("ONDO_WALLET", "hermes")
        self.network = network
        logger.info(
            "OndoBroker initialized (wallet=%s, network=%s). "
            "Integration pending — calls will raise NotImplementedError.",
            self.wallet_name,
            self.network,
        )

    def get_open_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError("OndoBroker.get_open_positions is stubbed.")

    def get_mid(self, symbol: str) -> float:
        raise NotImplementedError("OndoBroker.get_mid is stubbed.")

    def market_open(
        self,
        symbol: str,
        side: OrderSide,
        size_usd: float,
        *,
        slippage: float = 0.01,
    ) -> BrokerResponse:
        raise NotImplementedError(
            f"OndoBroker.market_open({symbol!r}, {side!r}, ${size_usd:.2f}) is stubbed."
        )

    def market_close(self, symbol: str, *, slippage: float = 0.01) -> BrokerResponse:
        raise NotImplementedError(f"OndoBroker.market_close({symbol!r}) is stubbed.")

    def healthcheck(self) -> bool:
        """No network call yet — reports whether a wallet name is configured."""
        return bool(self.wallet_name)
