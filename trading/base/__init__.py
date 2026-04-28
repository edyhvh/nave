"""
Asset-agnostic trading primitives.

This layer defines the contracts that concrete asset classes
(``trading.crypto``, ``trading.stocks``) must satisfy. Strategies, journals,
and orchestration code should depend on these abstractions rather than on any
specific broker or venue.

Public contracts:
    BaseBroker   — order execution + read-only market state
    BaseStrategy — compute signals + route through a BaseBroker
    BaseJournal  — facade over ``trading.journal`` scoped to an asset class

The Hyperliquid crypto strategies predate this layer; they continue to work
via ``HyperliquidClientProtocol`` in ``trading.crypto.client``. New asset
classes (stocks, whatever comes next) should build on ``BaseBroker``.
"""

from trading.base.broker import BaseBroker, OrderSide, BrokerResponse
from trading.base.journal import BaseJournal
from trading.base.strategy import AbstractStrategy

__all__ = [
    "BaseBroker",
    "OrderSide",
    "BrokerResponse",
    "BaseJournal",
    "AbstractStrategy",
]
