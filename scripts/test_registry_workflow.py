#!/usr/bin/env python3
"""End-to-end checklist for the top-40 ticker playbook workflow."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = PROJECT_ROOT / "var" / "registry" / "sp500_top40"


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "OK" if ok else "MISSING"
    line = f"  [{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    print("=== Ticker playbook workflow checklist ===\n")

    env_ok = True
    env_ok &= _check("FMP_API_KEY", bool(os.getenv("FMP_API_KEY")), "Congress + politicians scan")
    bearer = bool(os.getenv("X_BEARER_TOKEN") or os.getenv("TWITTER_BEARER_TOKEN"))
    _check(
        "X_BEARER_TOKEN (optional)",
        bearer,
        "skipped in current workflow",
    )
    x_db = os.getenv("X_ACCOUNTS_DB") or str(PROJECT_ROOT / "var" / "x_accounts.db")
    _check("X_ACCOUNTS_DB (optional)", Path(x_db).is_file(), "not required without X")

    print("\n=== Registry on disk ===")
    reg_ok = _check("index.json", (REGISTRY / "index.json").is_file())
    n_profiles = len(list(REGISTRY.glob("*.json"))) - (1 if reg_ok else 0)
    _check("ticker profiles", n_profiles >= 35, f"{n_profiles} files")

    print("\n=== Unit tests ===")
    tests = [
        "tests/test_x_interest.py",
        "tests/test_ticker_registry.py",
        "tests/test_gem_finder.py",
        "tests/test_options_replay.py",
    ]
    test_ok = True
    for path in tests:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        passed = r.returncode == 0
        test_ok &= passed
        tail = (r.stdout or r.stderr).strip().splitlines()[-1] if r.stdout or r.stderr else ""
        _check(path, passed, tail)

    print("\n=== Workflow (no X) ===")
    print("  1. FMP_API_KEY in .env")
    print("  2. nave congress")
    print("  3. python3 scripts/run_ticker_strategy_loop.py  (full learn loop)")
    print("     OR: nave options registry iterate")
    print("  4. nave options registry learn / show TICKER")

    if not env_ok:
        print("\nNote: Congress needs FMP_API_KEY; registry still builds price + replay without it.")

    return 0 if (reg_ok and test_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())