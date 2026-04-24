"""
Crypto asset class — Hyperliquid futures trading stack.

Modules:
    client     — HyperliquidClient REST + signing wrapper
    vault      — Fernet-encrypted EVM wallet storage
    signals    — macro signal producers (COT, RRP, AAII, VIX)
    strategy   — MacroMomentumStrategy, CotWeeklyStrategy, TheoryV2Strategy
    theory_v2  — top-down weekly→daily→4H→1H engine
    execution  — ExecutionPlan builder with timeframe contract
    cot/       — CFTC COT fetcher + analyzer + report generator
    cot_gate   — weekly COT filter for theory_v2
    services/  — COTService orchestrator for MCP + CLI reuse
    mcp_server — MCP tools for Hermes (account/COT/execution)
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

__all__ = [
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
]
