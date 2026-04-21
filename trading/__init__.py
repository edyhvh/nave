"""
nave.trading — programmatic trading integration for Hyperliquid.

Public API:
    from trading import HyperliquidClient, WalletVault, Signal, BaseStrategy

Wallet credentials are NEVER stored in this package or in environment
variables. All secrets live in ~/.secrets/nave-wallets/ (Fernet-encrypted).
"""

from trading.vault import WalletVault
from trading.client import HyperliquidClient
from trading.signals import Signal, Direction, Timeframe
from trading.strategy import BaseStrategy, CotWeeklyStrategy, TheoryV2Strategy
from trading.theory_v2 import TheoryV2Engine, TheoryV2Decision
from trading.execution import ExecutionPlan, build_execution_plan
from trading.cot.cot_fetcher import fetch_latest_cot
from trading.cot.cot_analyzer import COTAnalyzer

__all__ = [
    "HyperliquidClient",
    "WalletVault",
    "Signal",
    "Direction",
    "Timeframe",
    "BaseStrategy",
    "CotWeeklyStrategy",
    "TheoryV2Strategy",
    "TheoryV2Engine",
    "TheoryV2Decision",
    "ExecutionPlan",
    "build_execution_plan",
    "fetch_latest_cot",
    "COTAnalyzer",
]
