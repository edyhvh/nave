"""
nave.trading — programmatic trading integration for Hyperliquid.

Public API:
    from trading import HyperliquidClient, WalletVault, Signal, BaseStrategy

Wallet credentials are NEVER stored in this package or in environment
variables. All secrets live in ~/.secrets/nave-wallets/ (Fernet-encrypted).
"""

from trading.vault import WalletVault
from trading.client import HyperliquidClient
from trading.signals import Signal, Direction
from trading.strategy import BaseStrategy
from trading.cot.cot_fetcher import fetch_latest_cot
from trading.cot.cot_analyzer import COTAnalyzer

__all__ = [
    "HyperliquidClient",
    "WalletVault",
    "Signal",
    "Direction",
    "fetch_latest_cot",
    "COTAnalyzer",
    "BaseStrategy",
]
