"""
Concrete broker implementations.

The abstract contract lives in :mod:`trading.base.broker`. This package
collects the asset-specific adapters:

    HyperliquidBroker — thin adapter over ``trading.crypto.client``
    AlpacaBroker      — equities stub for Alpaca Markets
    OndoBroker        — equities / RWA stub for Ondo Finance

The crypto adapter is a no-op wrapper; stocks brokers are intentionally
stubs and will raise :class:`NotImplementedError` until the full
integration lands.
"""

from trading.brokers.alpaca import AlpacaBroker
from trading.brokers.hyperliquid import HyperliquidBroker
from trading.brokers.ondo import OndoBroker

__all__ = [
    "AlpacaBroker",
    "HyperliquidBroker",
    "OndoBroker",
]
