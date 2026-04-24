"""
nave.trading — multi-asset trading integration package.

Public API (stable):
    from trading import (
        HyperliquidClient, WalletVault,
        Signal, Direction, Timeframe,
        BaseStrategy, CotWeeklyStrategy, TheoryV2Strategy,
        TheoryV2Engine, TheoryV2Decision,
        ExecutionPlan, build_execution_plan,
        fetch_latest_cot, COTAnalyzer,
    )

Asset-class layout:
    trading.base/    — asset-agnostic abstractions (BaseBroker, BaseStrategy, …)
    trading.brokers/ — concrete broker implementations (alpaca, ondo stubs)
    trading.crypto/  — Hyperliquid + COT + theory-v2 stack (formerly trading.*)
    trading.stocks/  — ISM-driven equities workflow (Massive.com fundamentals)
    trading.journal/ — asset-class-aware trade journal (shared)

Wallet credentials are NEVER stored in this package or in environment
variables. All secrets live in ~/.secrets/nave-wallets/ (Fernet-encrypted).
"""

# Back-compat aliases must be installed BEFORE any re-export pulls a submodule,
# so legacy paths like ``trading.client`` resolve to ``trading.crypto.client``.
from trading import _compat as _compat

_compat.install()

from trading.crypto.vault import WalletVault
from trading.crypto.client import HyperliquidClient
from trading.crypto.signals import Signal, Direction, Timeframe
from trading.crypto.strategy import BaseStrategy, CotWeeklyStrategy, TheoryV2Strategy
from trading.crypto.theory_v2 import TheoryV2Engine, TheoryV2Decision
from trading.crypto.execution import ExecutionPlan, build_execution_plan
from trading.crypto.cot.cot_fetcher import fetch_latest_cot
from trading.crypto.cot.cot_analyzer import COTAnalyzer

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
