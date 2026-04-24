"""
Back-compat aliases for legacy ``trading.*`` import paths.

The crypto trading modules used to live at the top of the ``trading`` package
(``trading.client``, ``trading.strategy``, etc.). They now live under
``trading.crypto.*``. Legacy imports across the repo — scripts/, tests/, cli/,
hermes/integration.py, and ``trading.journal`` internals — continue to work
because this module registers ``sys.modules`` aliases so Python resolves the
old paths to the real, relocated modules.

This file is imported exactly once, from ``trading/__init__.py``. Do not import
it directly.

Invariant: every legacy top-level import path that used to resolve under
``trading/`` must be re-aliased here. If you add a new module to
``trading/crypto/``, decide whether it should be reachable via the legacy
top-level path; if so, add an alias entry below.
"""

from __future__ import annotations

import importlib
import sys

# Legacy name → real (moved) module name.
# Order matters for packages: import the package first so its submodules are
# discoverable before we alias any child submodule paths.
_ALIASES: dict[str, str] = {
    # --- single-file modules ------------------------------------------------
    "trading.client": "trading.crypto.client",
    "trading.vault": "trading.crypto.vault",
    "trading.signals": "trading.crypto.signals",
    "trading.strategy": "trading.crypto.strategy",
    "trading.theory_v2": "trading.crypto.theory_v2",
    "trading.execution": "trading.crypto.execution",
    "trading.config": "trading.crypto.config",
    "trading.cot_gate": "trading.crypto.cot_gate",
    "trading.mcp_server": "trading.crypto.mcp_server",
    # --- packages (register parent first, then children) --------------------
    "trading.cot": "trading.crypto.cot",
    "trading.cot.models": "trading.crypto.cot.models",
    "trading.cot.cot_analyzer": "trading.crypto.cot.cot_analyzer",
    "trading.cot.cot_fetcher": "trading.crypto.cot.cot_fetcher",
    "trading.cot.cot_historical_analyzer": "trading.crypto.cot.cot_historical_analyzer",
    "trading.cot.cot_position_generator": "trading.crypto.cot.cot_position_generator",
    "trading.cot.cot_report_generator": "trading.crypto.cot.cot_report_generator",
    "trading.services": "trading.crypto.services",
    "trading.services.cot_service": "trading.crypto.services.cot_service",
}


def install() -> None:
    """Register sys.modules aliases. Idempotent — safe to call multiple times.

    Also binds the aliased module as an attribute on its legacy parent package
    so tools that walk the package graph (pytest's monkeypatch, inspect,
    importlib.metadata) can resolve ``trading.services`` / ``trading.cot``
    without Python having physically imported those paths.
    """
    for legacy, real in _ALIASES.items():
        if legacy in sys.modules:
            continue
        try:
            module = importlib.import_module(real)
        except ImportError:
            # Surface the real error at first use rather than on package import.
            # Strategies that depend on optional packages (e.g. hyperliquid SDK)
            # must not prevent the journal or stocks workflows from importing.
            continue
        sys.modules[legacy] = module
        # Bind as attribute on the legacy parent so `trading.services` works.
        parent_name, _, child_name = legacy.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, child_name, module)
