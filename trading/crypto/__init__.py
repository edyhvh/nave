"""
Crypto asset class — Hyperliquid futures trading stack.

Primary API (BTC/ETH only):
    analysis   — ``CryptoAnalysisService.review()`` — COT, regime (long+short),
                 momentum 4H/1H, Deribit options, regime thesis
    momentum/  — setup engine + backtest
    cot/       — contrarian bias + weekly permission gate
    theory_v2  — diagnostic gate trace (secondary to analysis.review)
"""

from trading.crypto.client import HyperliquidClient, HyperliquidClientProtocol
from trading.crypto.vault import WalletVault
from trading.crypto.signals import (
    Signal,
    Direction,
    Timeframe,
    SignalAggregator,
    MacroSignalProducer,
)
from trading.crypto.strategy import (
    BaseStrategy,
    MacroMomentumStrategy,
    CotWeeklyStrategy,
    TheoryV2Strategy,
)
from trading.crypto.theory_v2 import TheoryV2Engine, TheoryV2Decision
from trading.crypto.execution import ExecutionPlan, build_execution_plan
from trading.crypto.analysis import CryptoAnalysisService, review_positions
from trading.crypto.momentum import MomentumBacktester, MomentumSetupEngine, TradePlan

__all__ = [
    "CryptoAnalysisService",
    "review_positions",
    "HyperliquidClient",
    "HyperliquidClientProtocol",
    "WalletVault",
    "Signal",
    "Direction",
    "Timeframe",
    "SignalAggregator",
    "MacroSignalProducer",
    "BaseStrategy",
    "MacroMomentumStrategy",
    "CotWeeklyStrategy",
    "TheoryV2Strategy",
    "TheoryV2Engine",
    "TheoryV2Decision",
    "ExecutionPlan",
    "build_execution_plan",
    "MomentumBacktester",
    "MomentumSetupEngine",
    "TradePlan",
]
