"""
Hyperliquid adapter that satisfies :class:`trading.base.broker.BaseBroker`.

This is a thin facade over :class:`trading.crypto.client.HyperliquidClient`
so that code written against the asset-agnostic ``BaseBroker`` contract can
trade crypto perps without knowing about Hyperliquid specifics.

For direct Hyperliquid usage (summary printing, historical candles, etc.)
keep using :class:`HyperliquidClient` — this adapter intentionally exposes
only the small contract surface needed by strategies.
"""

from __future__ import annotations

from typing import Any

from trading.base.broker import BaseBroker, BrokerResponse, OrderSide
from trading.crypto.client import HyperliquidClient


class HyperliquidBroker(BaseBroker):
    """Adapter: :class:`HyperliquidClient` → :class:`BaseBroker`."""

    name = "hyperliquid"

    def __init__(
        self,
        client: HyperliquidClient | None = None,
        *,
        wallet_name: str = "hermes",
        testnet: bool = True,
    ):
        self.client = client or HyperliquidClient(wallet_name=wallet_name, testnet=testnet)

    def get_open_positions(self) -> list[dict[str, Any]]:
        return self.client.get_open_positions()

    def get_mid(self, symbol: str) -> float:
        return self.client.get_mid(symbol)

    def market_open(
        self,
        symbol: str,
        side: OrderSide,
        size_usd: float,
        *,
        slippage: float = 0.01,
    ) -> BrokerResponse:
        # Normalize buy/sell → long/short; Hyperliquid models positional intent.
        if side == "buy":
            side = "long"
        elif side == "sell":
            side = "short"
        raw = self.client.market_open(symbol, side, size_usd, slippage=slippage)
        return BrokerResponse(
            ok=str(raw.get("status", "")).lower() == "ok",
            broker=self.name,
            message=str(raw.get("status", "")),
            raw=raw if isinstance(raw, dict) else {"response": raw},
        )

    def market_close(self, symbol: str, *, slippage: float = 0.01) -> BrokerResponse:
        raw = self.client.market_close(symbol, slippage=slippage)
        return BrokerResponse(
            ok=str(raw.get("status", "")).lower() == "ok",
            broker=self.name,
            message=str(raw.get("status", "")),
            raw=raw if isinstance(raw, dict) else {"response": raw},
        )
