"""
Asset-agnostic broker contract.

Every concrete broker (Hyperliquid, Alpaca, Ondo, …) implements this
interface so that strategies, journals, and Hermes tools can target any
asset class without caring whether they are placing a crypto perp or an
equities order.

Design rules:
  - Read-only methods must NEVER touch wallet secrets.
  - Write methods (open/close/cancel) load credentials lazily and discard
    local references immediately after signing.
  - All dollar amounts are USD-denominated floats.
  - Dry-run behavior is the caller's responsibility (see ``BaseStrategy``).
    Brokers assume a real order when called.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


OrderSide = Literal["long", "short", "buy", "sell"]


@dataclass
class BrokerResponse:
    """
    Canonical broker response envelope.

    Concrete brokers may return richer payloads via ``raw``; consumers that
    only need a safe success/failure flag can rely on ``ok``.
    """

    ok: bool
    broker: str
    message: str = ""
    order_id: str | None = None
    filled_size: float | None = None
    filled_price: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class BaseBroker(ABC):
    """Minimum contract every broker must implement."""

    #: Human-readable broker name (e.g. ``"hyperliquid"``, ``"alpaca"``).
    name: str = "base"

    # ── Read-only -------------------------------------------------------
    @abstractmethod
    def get_open_positions(self) -> list[dict[str, Any]]:
        """Return open positions for the active account."""

    @abstractmethod
    def get_mid(self, symbol: str) -> float:
        """Return the current mid price for ``symbol`` in quote currency."""

    # ── Writes ----------------------------------------------------------
    @abstractmethod
    def market_open(
        self,
        symbol: str,
        side: OrderSide,
        size_usd: float,
        *,
        slippage: float = 0.01,
    ) -> BrokerResponse:
        """Submit a market-priced order sized in notional USD."""

    @abstractmethod
    def market_close(self, symbol: str, *, slippage: float = 0.01) -> BrokerResponse:
        """Close the entire open position for ``symbol`` at market."""

    # ── Optional niceties ---------------------------------------------
    def healthcheck(self) -> bool:
        """Cheap read that confirms API reachability. Default: best-effort."""
        try:
            self.get_open_positions()
            return True
        except Exception:
            return False
