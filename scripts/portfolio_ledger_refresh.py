#!/usr/bin/env python3
"""Thin CLI for the read-only ONDO ledger refresh."""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with redirect_stdout(io.StringIO()):
    from trading.stocks.portfolio_ledger import main
    from trading.stocks.operational_calendar import operational_now

if __name__ == "__main__":
    if not operational_now():
        print(json.dumps({"status": "paused", "reason": "shabbat"}))
    else:
        main()
