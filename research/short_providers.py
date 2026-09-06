"""Bounded autonomous acquisition using NAVE's existing equity adapters."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import math

from research.portfolio_providers import PortfolioContextProvider

# Small liquid research universe; no holdings or execution state is consulted.
UNIVERSE = {"AAPL": "XLK", "NVDA": "XLK", "TSLA": "XLY", "JPM": "XLF"}


def acquire_short_snapshot(*, provider=None, now=None, universe=None):
    now = now or datetime.now(UTC)
    provider = provider or PortfolioContextProvider()
    universe = universe or UNIVERSE
    symbols = sorted(set(universe) | set(universe.values()) | {"SPY"})

    def history(symbol):
        try:
            series, source, observed, retrieved = provider._history(symbol, now)
            stamp = datetime.fromisoformat(observed) if observed else None
            valid = (
                stamp is not None
                and stamp.tzinfo is not None
                and timedelta(0) <= now - stamp <= timedelta(days=5)
                and len(series) >= 21
                and all(math.isfinite(float(v)) and float(v) > 0 for v in series.tail(21))
            )
            return symbol, (series, source, observed, retrieved, valid)
        except Exception:
            return symbol, (None, "unavailable", None, None, False)

    with ThreadPoolExecutor(max_workers=4) as pool:
        histories = dict(pool.map(history, symbols))
    benchmark = histories["SPY"]
    rows = []
    for ticker, sector in universe.items():
        series, source, observed, retrieved, valid = histories[ticker]
        sec = histories[sector]
        row = {
            "ticker": ticker,
            "source": source,
            "source_url": f"https://finance.yahoo.com/quote/{ticker}/history/",
            "event_time": observed,
            "available_at": now.isoformat() if valid else None,
            "acquisition_mode": "LIVE",
            "required_factors": ["company_fundamentals", "technical_breakdown", "catalyst"],
            "provider_health": "HEALTHY" if valid else "DATA_UNAVAILABLE",
            "factor_evidence": {},
            "horizon": "daily swing research",
            "company_fundamentals": None,
            "catalyst": None,
            "earnings_revision_deterioration": None,
            "positioning_crowding": None,
            "valuation_support": None,
        }
        if valid:
            row["technical_breakdown"] = float(series.iloc[-1]) < float(series.iloc[-21:-1].min())
            row["factor_evidence"]["technical_breakdown"] = {
                "source": source,
                "observed_at": observed,
                "retrieved_at": retrieved,
                "rule": "daily close below previous 20 daily closes",
            }
        if benchmark[4]:
            b = benchmark[0]
            row["macro_regime"] = (
                "risk_off" if float(b.iloc[-1]) < float(b.tail(20).mean()) else "neutral"
            )
            row["factor_evidence"]["macro_regime"] = {
                "source": benchmark[1],
                "symbol": "SPY",
                "observed_at": benchmark[2],
                "semantics": "equity benchmark regime proxy, not full macro assessment",
            }
        if sec[4] and benchmark[4]:
            sector_return = float(sec[0].iloc[-1] / sec[0].iloc[-21] - 1)
            benchmark_return = float(benchmark[0].iloc[-1] / benchmark[0].iloc[-21] - 1)
            row["sector_weakness"] = sector_return < 0 and sector_return < benchmark_return
            row["factor_evidence"]["sector_weakness"] = {
                "source": sec[1],
                "symbol": sector,
                "observed_at": sec[2],
                "return_20d": sector_return,
                "benchmark_return_20d": benchmark_return,
            }
        try:
            info = asdict(provider.fundamentals.fundamentals(ticker))
            # Retrieval is not a filing date. Preserve raw company context but
            # don't assert deterioration from a lone undated fundamental snapshot.
            row["company_information"] = info
        except Exception:
            row["company_information"] = {"status": "UNAVAILABLE"}
        rows.append(row)
    return rows
