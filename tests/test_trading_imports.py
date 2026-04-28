from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_import_trading_is_lazy() -> None:
    result = _run_python(
        "import sys, trading; "
        "print('crypto_client_loaded', 'trading.crypto.client' in sys.modules); "
        "print('crypto_strategy_loaded', 'trading.crypto.strategy' in sys.modules)"
    )

    assert result.returncode == 0
    assert "[data_loader]" not in result.stdout
    assert "crypto_client_loaded False" in result.stdout
    assert "crypto_strategy_loaded False" in result.stdout


def test_legacy_alias_module_loads_on_attribute_access() -> None:
    result = _run_python(
        "import sys, trading.client; "
        "print('before', 'trading.crypto.client' in sys.modules); "
        "from trading.client import HyperliquidClient; "
        "print('after', 'trading.crypto.client' in sys.modules); "
        "print('loaded_name', HyperliquidClient.__module__)"
    )

    assert result.returncode == 0
    assert "before False" in result.stdout
    assert "after True" in result.stdout
    assert "loaded_name trading.crypto.client" in result.stdout