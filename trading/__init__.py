"""
nave.trading — programmatic trading integration for Hyperliquid.

Public API:
    from trading import HyperliquidClient, WalletVault, Signal, BaseStrategy
    from trading import CotWeeklyStrategy, CotSignalProducer
    from trading.cot import CotFetcher, CotAnalyzer

Wallet credentials are NEVER stored in this package or in environment
variables. All secrets live in ~/.secrets/nave-wallets/ (Fernet-encrypted).

COT Integration:
    The trading module now includes CME Commitment of Traders (COT) analysis
    as the primary weekly sentiment driver. Use CotWeeklyStrategy for
    automated weekly setup generation.
"""
from trading.vault import WalletVault
from trading.client import HyperliquidClient
from trading.signals import Signal, Direction, CotSignalProducer, generate_weekly_signals
from trading.strategy import BaseStrategy, CotWeeklyStrategy, PositionSizing

__all__ = [
    # Core
    "HyperliquidClient",
    "WalletVault",
    "Signal",
    "Direction",
    "BaseStrategy",
    # COT Integration
    "CotSignalProducer",
    "CotWeeklyStrategy",
    "PositionSizing",
    "generate_weekly_signals",
]