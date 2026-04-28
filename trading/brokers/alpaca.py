"""
Alpaca Markets broker — **stub**.

This file pins the public interface so downstream code (strategies, CLI,
Hermes tools) can depend on the type today. The actual HTTP integration
lands in a follow-up PR once the Alpaca account and keys are provisioned.

When you implement it, prefer ``alpaca-py``:
    https://alpaca.markets/docs/trading/overview/

Environment variables (already listed in ``.env.example``):
    ALPACA_API_KEY
    ALPACA_API_SECRET
    ALPACA_PAPER_TRADING=true   # default: paper endpoint
"""

from __future__ import annotations

import logging
import os
from typing import Any

from trading.base.broker import BaseBroker, BrokerResponse, OrderSide

logger = logging.getLogger(__name__)


class AlpacaBroker(BaseBroker):
    """Stub broker. Raises :class:`NotImplementedError` on any write."""

    name = "alpaca"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        *,
        paper: bool = True,
    ):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET")
        self.paper = paper
        logger.info(
            "AlpacaBroker initialized (paper=%s, key_present=%s). "
            "Full integration pending — calls will raise NotImplementedError.",
            paper,
            bool(self.api_key),
        )

    # ── Read-only -------------------------------------------------------
    def get_open_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "AlpacaBroker.get_open_positions is stubbed. "
            "Integration pending — see trading/brokers/alpaca.py docstring."
        )

    def get_mid(self, symbol: str) -> float:
        raise NotImplementedError("AlpacaBroker.get_mid is stubbed.")

    # ── Writes ----------------------------------------------------------
    def market_open(
        self,
        symbol: str,
        side: OrderSide,
        size_usd: float,
        *,
        slippage: float = 0.01,
    ) -> BrokerResponse:
        raise NotImplementedError(
            f"AlpacaBroker.market_open({symbol!r}, {side!r}, ${size_usd:.2f}) is stubbed."
        )

    def market_close(self, symbol: str, *, slippage: float = 0.01) -> BrokerResponse:
        raise NotImplementedError(f"AlpacaBroker.market_close({symbol!r}) is stubbed.")

    # ── Meta ------------------------------------------------------------
    def healthcheck(self) -> bool:
        """Return ``True`` only if both keys are present. No network call yet."""
        return bool(self.api_key and self.api_secret)
