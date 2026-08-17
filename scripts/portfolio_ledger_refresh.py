#!/usr/bin/env python3
"""Thin CLI for the read-only ONDO ledger refresh."""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with redirect_stdout(io.StringIO()):
    from trading.stocks.portfolio_ledger import main

if __name__ == "__main__":
    main()
