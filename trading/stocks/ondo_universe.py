"""Ondo stock perp research-universe helpers.

Ondo Global Markets lists 250+ tokenized US equities. Nave's ISM workflow
screens a curated DEFAULT_UNIVERSE of liquid names; this module treats that
set as a research proxy until a live venue manifest is wired.
"""

from __future__ import annotations

from trading.stocks.universe import DEFAULT_UNIVERSE

ONDO_STOCK_PERP_VENUE = "ondo_stock_perp"
ONDO_STOCK_PERP_UNIVERSE_SOURCE = "research_proxy_default_universe"
ONDO_STOCK_PERP_EXECUTION_STATUS = "proxy_not_live_manifest"

ONDO_STOCK_PERP_UNIVERSE: frozenset[str] = frozenset(
    symbol.upper()
    for tickers in DEFAULT_UNIVERSE.values()
    for symbol in tickers
)


def is_ondo_stock_perp(symbol: str) -> bool:
    return symbol.upper() in ONDO_STOCK_PERP_UNIVERSE
