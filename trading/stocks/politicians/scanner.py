"""Daily scan: fetch latest House+Senate disclosures and surface new ones.

Called once per day by Hermes (or via ``nave stocks politicians-scan``).
Idempotent — re-running on the same calendar day after the cache is
populated returns ``new_total=0``.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Protocol

from trading.stocks.politicians.provider import (
    FMPPoliticianTradesProvider,
    PoliticianTrade,
)
from trading.stocks.politicians.store import SeenStore

logger = logging.getLogger(__name__)


class TradesProvider(Protocol):
    """Provider contract for politician disclosures."""

    def fetch_all(self) -> list[PoliticianTrade]:
        ...


def run_daily_scan(
    *,
    provider: TradesProvider | None = None,
    store: SeenStore | None = None,
    persist: bool = True,
    event_journal_path: str | None = None,
) -> dict[str, Any]:
    """Fetch latest disclosures, return only those unseen since the last scan."""
    provider = provider or FMPPoliticianTradesProvider()
    store_was_default = store is None
    store = store or SeenStore()
    assert provider is not None
    assert store is not None

    previous_scan_at = store.last_scan_at
    seen_count_before = store.size()
    fetched_at = datetime.now(UTC).isoformat()

    trades = provider.fetch_all()
    new_trades = [t for t in trades if not store.contains(t.unique_id)]

    if persist:
        store.add_many(t.unique_id for t in trades)
        store.save()
        # Keep new disclosures visible after they leave the provider's latest
        # feed. The journal is local state and does not trigger any trade.
        from trading.stocks.event_journal import record_politician_trades

        if store_was_default or event_journal_path:
            record_politician_trades(
                (asdict(t) for t in new_trades),
                path=event_journal_path,
            )

    return {
        "generated_at": fetched_at,
        "previous_scan_at": previous_scan_at,
        "fetched_total": len(trades),
        "new_total": len(new_trades),
        "seen_total_before": seen_count_before,
        "seen_total_after": store.size(),
        "summary": _summarize(new_trades),
        "new_trades": [asdict(t) for t in new_trades],
    }


def _summarize(trades: list[PoliticianTrade]) -> dict[str, Any]:
    by_chamber: dict[str, int] = {"house": 0, "senate": 0}
    by_type: dict[str, int] = {}
    by_symbol: dict[str, int] = {}
    politicians: set[str] = set()
    for t in trades:
        by_chamber[t.chamber] = by_chamber.get(t.chamber, 0) + 1
        if t.transaction_type:
            by_type[t.transaction_type] = by_type.get(
                t.transaction_type, 0) + 1
        if t.symbol:
            by_symbol[t.symbol] = by_symbol.get(t.symbol, 0) + 1
        politicians.add(t.politician)
    top_symbols = sorted(
        by_symbol.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return {
        "by_chamber": by_chamber,
        "by_type": by_type,
        "top_symbols": [{"symbol": s, "count": c} for s, c in top_symbols],
        "unique_politicians": len(politicians),
    }
