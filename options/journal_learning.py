"""Convert manual options journal trades into replay-compatible learning rows."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

DEFAULT_JOURNAL_DIR = Path(__file__).resolve().parents[1] / "trade_journal" / "manual_trades"

_STRATEGY_ALIASES = {
    "bull put": "bull_put_credit_spread",
    "bull_put": "bull_put_credit_spread",
    "bear call": "bear_call_credit_spread",
    "bear_call": "bear_call_credit_spread",
    "csp": "cash_secured_put",
    "cash secured put": "cash_secured_put",
}


def _normalize_strategy(setup: str) -> str | None:
    raw = (setup or "").strip().lower().replace("-", "_")
    if not raw:
        return None
    if raw in _STRATEGY_ALIASES:
        return _STRATEGY_ALIASES[raw]
    for key, val in _STRATEGY_ALIASES.items():
        if key in raw:
            return val
    if "bull_put" in raw:
        return "bull_put_credit_spread"
    if "bear_call" in raw:
        return "bear_call_credit_spread"
    if "cash_secured" in raw or "csp" in raw:
        return "cash_secured_put"
    return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _infer_pnl(trade: dict[str, Any]) -> tuple[float | None, bool | None]:
    """Best-effort PnL from journal fields."""
    notes = str(trade.get("notes") or "")
    for token in notes.split():
        if token.lower().startswith("pnl:"):
            try:
                pnl = float(token.split(":", 1)[1].replace("$", "").replace(",", ""))
                return pnl, pnl > 0
            except ValueError:
                pass
    entry = float(trade.get("entry_price") or 0)
    exit_px = trade.get("take_profit_final_price") or trade.get("target_price")
    if trade.get("status") == "closed" and entry > 0 and exit_px:
        side = str(trade.get("side") or "long").lower()
        exit_f = float(exit_px)
        pnl = (exit_f - entry) if side == "long" else (entry - exit_f)
        return pnl, pnl > 0
    return None, None


def manual_trade_to_replay_row(trade: dict[str, Any]) -> dict[str, Any] | None:
    if str(trade.get("market_type") or "").lower() != "options":
        return None
    sym = str(trade.get("asset") or "").strip().upper()
    if not sym or len(sym) > 6:
        return None
    strategy = _normalize_strategy(str(trade.get("setup") or ""))
    if not strategy:
        return None
    entry_d = _parse_date(trade.get("date_created"))
    if entry_d is None:
        return None
    pnl, profitable = _infer_pnl(trade)
    if pnl is None:
        return None
    return {
        "ticker": sym,
        "status": "trade_candidate",
        "strategy_name": strategy,
        "profitable": bool(profitable),
        "mark": {"pnl_dollars": float(pnl), "source": "journal"},
        "entry_metrics": {"pop": None, "probability_of_touch": None},
        "entry_date": entry_d.isoformat(),
        "directional_bias": "neutral",
        "source": "journal",
    }


def load_options_journal_rows(
    journal_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    root = Path(journal_dir) if journal_dir else DEFAULT_JOURNAL_DIR
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        if path.name.endswith(".tmp"):
            continue
        try:
            trade = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        row = manual_trade_to_replay_row(trade)
        if row:
            rows.append(row)
    return rows