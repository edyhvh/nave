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

from __future__ import annotations

from importlib import import_module
from typing import Any

# Back-compat aliases must be installed BEFORE any re-export pulls a submodule,
# so legacy paths like ``trading.client`` resolve to ``trading.crypto.client``.
from trading import _compat as _compat

_compat.install()

_EXPORTS: dict[str, tuple[str, str]] = {
    "HyperliquidClient": ("trading.crypto.client", "HyperliquidClient"),
    "WalletVault": ("trading.crypto.vault", "WalletVault"),
    "Signal": ("trading.crypto.signals", "Signal"),
    "Direction": ("trading.crypto.signals", "Direction"),
    "Timeframe": ("trading.crypto.signals", "Timeframe"),
    "BaseStrategy": ("trading.crypto.strategy", "BaseStrategy"),
    "CotWeeklyStrategy": ("trading.crypto.strategy", "CotWeeklyStrategy"),
    "TheoryV2Strategy": ("trading.crypto.strategy", "TheoryV2Strategy"),
    "TheoryV2Engine": ("trading.crypto.theory_v2", "TheoryV2Engine"),
    "TheoryV2Decision": ("trading.crypto.theory_v2", "TheoryV2Decision"),
    "ExecutionPlan": ("trading.crypto.execution", "ExecutionPlan"),
    "build_execution_plan": ("trading.crypto.execution", "build_execution_plan"),
    "fetch_latest_cot": ("trading.crypto.cot.cot_fetcher", "fetch_latest_cot"),
    "COTAnalyzer": ("trading.crypto.cot.cot_analyzer", "COTAnalyzer"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))

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
