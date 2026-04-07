"""Manual trade journal service with per-trade JSON persistence."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from trading.cot.cot_analyzer import COTAnalyzer
from trading.cot.cot_fetcher import fetch_latest_cot


TRADING_MODES = ("live", "demo", "backtest")
MARKET_TYPES = ("futures", "options", "spot")
SIDES = ("long", "short")


@dataclass
class ManualTrade:
    """Manual trade record saved as one JSON file per trade."""

    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asset: str = "BTC"
    platform: str = "binance"
    side: str = "long"
    market_type: str = "futures"
    trading_mode: str = "demo"
    entry_price: float = 0.0
    target_price: float = 0.0
    stop_loss_price: float = 0.0
    fees: float = 0.0
    size: float = 0.0
    leverage: float = 1.0
    setup: str = ""
    notes: str = ""
    cot_insight: Optional[Dict[str, Any]] = None
    cot_warning: Optional[str] = None
    take_profit_price_1: Optional[float] = None
    take_profit_price_2: Optional[float] = None
    take_profit_final_price: Optional[float] = None
    tp1_progress_percent: Optional[float] = None
    tp2_progress_percent: Optional[float] = None
    status: str = "open"
    date_created: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc).replace(tzinfo=None).isoformat()
    )
    date_updated: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc).replace(tzinfo=None).isoformat()
    )
    event_history: List[Dict[str, Any]] = field(default_factory=list)
    sync: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "asset": self.asset,
            "platform": self.platform,
            "side": self.side,
            "market_type": self.market_type,
            "trading_mode": self.trading_mode,
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "stop_loss_price": self.stop_loss_price,
            "fees": self.fees,
            "size": self.size,
            "leverage": self.leverage,
            "setup": self.setup,
            "notes": self.notes,
            "cot_insight": self.cot_insight,
            "cot_warning": self.cot_warning,
            "take_profit_price_1": self.take_profit_price_1,
            "take_profit_price_2": self.take_profit_price_2,
            "take_profit_final_price": self.take_profit_final_price,
            "tp1_progress_percent": self.tp1_progress_percent,
            "tp2_progress_percent": self.tp2_progress_percent,
            "status": self.status,
            "date_created": self.date_created,
            "date_updated": self.date_updated,
            "event_history": self.event_history,
            "sync": self.sync,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ManualTrade":
        return cls(**payload)


class ManualTradeStore:
    """Persist manual trades to one JSON file per trade."""

    def __init__(self, data_dir: str = "trade_journal/manual_trades"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _trade_file(self, trade_id: str) -> Path:
        return self.data_dir / f"{trade_id}.json"

    def _write_trade(self, trade: ManualTrade) -> None:
        trade.date_updated = datetime.now(
            timezone.utc).replace(tzinfo=None).isoformat()
        target = self._trade_file(trade.trade_id)
        tmp = target.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(trade.to_dict(), handle, indent=2)
        tmp.replace(target)

    def create_trade(self, trade: ManualTrade) -> ManualTrade:
        trade.event_history.append(
            {
                "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "action": "create",
                "payload": {
                    "entry_price": trade.entry_price,
                    "target_price": trade.target_price,
                    "stop_loss_price": trade.stop_loss_price,
                    "fees": trade.fees,
                },
            }
        )
        self._write_trade(trade)
        return trade

    def get_trade(self, trade_id: str) -> Optional[ManualTrade]:
        path = self._trade_file(trade_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return ManualTrade.from_dict(payload)

    def list_trades(self, status: Optional[str] = None, limit: int = 200) -> List[ManualTrade]:
        rows: List[ManualTrade] = []
        for path in sorted(self.data_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            with open(path, "r", encoding="utf-8") as handle:
                row = ManualTrade.from_dict(json.load(handle))
                if status and row.status != status:
                    continue
                rows.append(row)
                if len(rows) >= limit:
                    break
        return rows

    def apply_update(self, trade_id: str, action: str, value: Any) -> ManualTrade:
        trade = self.get_trade(trade_id)
        if trade is None:
            raise ValueError(f"Trade {trade_id} not found")

        action_map = {
            "take_profit_price_1": "take_profit_price_1",
            "take_profit_price_2": "take_profit_price_2",
            "take_profit_final_price": "take_profit_final_price",
            "stop_loss adjustment": "stop_loss_price",
            "fees adjustment": "fees",
            "notes update": "notes",
        }
        if action not in action_map:
            raise ValueError(f"Unsupported action: {action}")

        field_name = action_map[action]
        setattr(trade, field_name, value)

        if action == "take_profit_price_1":
            trade.tp1_progress_percent = round(
                self._tp_progress_pct(trade, float(value)), 2)
        elif action == "take_profit_price_2":
            trade.tp2_progress_percent = round(
                self._tp_progress_pct(trade, float(value)), 2)
        elif action == "take_profit_final_price":
            trade.status = "closed"

        trade.event_history.append(
            {
                "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "action": action,
                "payload": {field_name: value},
            }
        )
        self._write_trade(trade)
        return trade

    def mark_synced(self, trade_ids: List[str], page_name: str) -> None:
        synced_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        for trade_id in trade_ids:
            trade = self.get_trade(trade_id)
            if trade is None:
                continue
            trade.sync["wiki_synced_at"] = synced_at
            trade.sync["wiki_page"] = page_name
            self._write_trade(trade)

    def unsynced_trades(self) -> List[ManualTrade]:
        trades = self.list_trades(limit=5000)
        return [t for t in trades if not t.sync.get("wiki_synced_at")]

    @staticmethod
    def _tp_progress_pct(trade: ManualTrade, tp_price: float) -> float:
        denominator = trade.target_price - trade.entry_price
        numerator = tp_price - trade.entry_price
        if trade.side == "short":
            denominator = trade.entry_price - trade.target_price
            numerator = trade.entry_price - tp_price
        if denominator == 0:
            return 0.0
        return max(0.0, min(100.0, (numerator / denominator) * 100.0))


def fetch_cot_insight(asset: str) -> Dict[str, Any]:
    """Fetch normalized COT snapshot for a trade asset."""
    symbol = asset.upper().strip()
    cot_data = fetch_latest_cot()
    analyzer = COTAnalyzer()
    biases = analyzer.analyze(cot_data)
    bias = biases.get(symbol)
    if bias is None:
        raise ValueError(f"No COT data available for {symbol}")

    raw = cot_data.get(symbol, {})
    return {
        "asset": symbol,
        "bias": bias.bias,
        "bias_label": bias.bias_label,
        "confidence": bias.confidence,
        "historical_percentile": bias.historical_percentile,
        "weekly_change": bias.weekly_change,
        "pct_oi_non_com": bias.pct_oi_non_com,
        "fits_weighted_score": bias.metadata.get("fits_weighted_score"),
        "market_regime": bias.metadata.get("market_regime"),
        "source": raw.get("source", "openbb"),
        "cached": raw.get("cached", False),
        "report_type": raw.get("report_type"),
        "as_of_date": raw.get("as_of_date") or raw.get("latest_date"),
        "release_date": raw.get("release_date"),
    }
