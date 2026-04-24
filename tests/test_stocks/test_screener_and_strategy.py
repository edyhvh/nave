"""Screener + strategy tests — deterministic fixtures, no network."""

from __future__ import annotations

from typing import Any, Iterable

import pytest

from trading.base.broker import BaseBroker, BrokerResponse
from trading.brokers import AlpacaBroker, OndoBroker
from trading.journal import TradeEnvironment
from trading.stocks.data_provider import FundamentalSnapshot
from trading.stocks.ism_scraper import ISMIndustryRanking, ISMReport
from trading.stocks.screener import SectorScreener, StockScreenerError
from trading.stocks.strategy import ISMSectorStrategy


class _FakeMassive:
    """Deterministic stand-in for MassiveClient."""

    def __init__(self, sector_avg: dict[str, float], snapshots: dict[str, FundamentalSnapshot]):
        self._sector_avg = sector_avg
        self._snapshots = snapshots

    def sector_average_pe(self, sector: str) -> float | None:
        return self._sector_avg.get(sector)

    def batch_fundamentals(self, symbols: Iterable[str]) -> list[FundamentalSnapshot]:
        return [self._snapshots[s] for s in symbols if s in self._snapshots]

    def fundamentals(self, symbol: str) -> FundamentalSnapshot:
        return self._snapshots[symbol]


class _CountingBroker(BaseBroker):
    name = "counting"

    def __init__(self):
        self.opens: list[tuple[str, str, float]] = []

    def get_open_positions(self) -> list[dict[str, Any]]:
        return []

    def get_mid(self, symbol: str) -> float:
        return 100.0

    def market_open(self, symbol, side, size_usd, *, slippage=0.01):
        self.opens.append((symbol, side, size_usd))
        return BrokerResponse(ok=True, broker=self.name)

    def market_close(self, symbol, *, slippage=0.01):
        return BrokerResponse(ok=True, broker=self.name)


def _make_report(expanding_sectors: list[tuple[str, str]]) -> ISMReport:
    rankings = [
        ISMIndustryRanking(industry=industry, trend="expanding", rank=i, gics_sector=sector)
        for i, (industry, sector) in enumerate(expanding_sectors, start=1)
    ]
    return ISMReport(
        kind="manufacturing",
        report_month="March 2026",
        pmi=53.0,
        expanding=rankings,
    )


def test_screener_ranks_by_pe_discount_and_eps_growth():
    report = _make_report([
        ("machinery", "Industrials"),
        ("chemical products", "Materials"),
    ])
    snapshots = {
        "GE":  FundamentalSnapshot("GE",  "Industrials", pe_ratio=15.0, forward_pe=13.0, eps_growth_next_year=20.0, raw={}),
        "CAT": FundamentalSnapshot("CAT", "Industrials", pe_ratio=22.0, forward_pe=21.0, eps_growth_next_year=5.0,  raw={}),
        "LIN": FundamentalSnapshot("LIN", "Materials",   pe_ratio=30.0, forward_pe=28.0, eps_growth_next_year=10.0, raw={}),
    }
    massive = _FakeMassive(
        sector_avg={"Industrials": 25.0, "Materials": 25.0},
        snapshots=snapshots,
    )
    screener = SectorScreener(
        massive=massive,
        universe={"Industrials": ["GE", "CAT"], "Materials": ["LIN"]},
    )

    picks = screener.rank_from_ism(report, top_n=3)
    assert [p.symbol for p in picks] == ["GE", "CAT", "LIN"]
    # GE: big PE discount AND strong EPS growth ⇒ top score by a wide margin.
    assert picks[0].score > picks[1].score > picks[2].score
    assert picks[0].sector_avg_pe == 25.0


def test_screener_raises_when_no_sectors_resolvable():
    # An expanding industry with no GICS mapping produces an empty list.
    report = ISMReport(
        kind="manufacturing",
        report_month="March 2026",
        pmi=53.0,
        expanding=[ISMIndustryRanking(industry="something unknown", trend="expanding", rank=1)],
    )
    screener = SectorScreener(massive=_FakeMassive({}, {}), universe={})
    with pytest.raises(StockScreenerError):
        screener.rank_from_ism(report)


def test_strategy_dry_run_logs_plan_without_broker_calls():
    report = _make_report([("machinery", "Industrials")])
    snapshots = {
        "GE":  FundamentalSnapshot("GE",  "Industrials", pe_ratio=15.0, forward_pe=13.0, eps_growth_next_year=20.0, raw={}),
        "CAT": FundamentalSnapshot("CAT", "Industrials", pe_ratio=22.0, forward_pe=21.0, eps_growth_next_year=5.0,  raw={}),
    }
    massive = _FakeMassive({"Industrials": 25.0}, snapshots)
    broker = _CountingBroker()

    class _StubFetcher:
        def fetch_report(self, kind, url=None):  # noqa: ARG002
            return report

    strategy = ISMSectorStrategy(
        broker=broker,
        massive=massive,
        universe={"Industrials": ["GE", "CAT"]},
        capital_usd=1000.0,
        max_positions=2,
        dry_run=True,
        fetcher=_StubFetcher(),
    )
    summary = strategy.run_once()
    assert summary["strategy"] == "ISMSectorStrategy"
    assert summary["dry_run"] is True
    assert len(summary["plan"]) == 2
    assert broker.opens == []  # dry-run: zero broker calls


def test_strategy_live_mode_routes_through_broker():
    report = _make_report([("machinery", "Industrials")])
    snapshots = {
        "GE": FundamentalSnapshot("GE", "Industrials", pe_ratio=15.0, forward_pe=13.0, eps_growth_next_year=20.0, raw={}),
    }
    massive = _FakeMassive({"Industrials": 25.0}, snapshots)
    broker = _CountingBroker()

    class _StubFetcher:
        def fetch_report(self, kind, url=None):  # noqa: ARG002
            return report

    strategy = ISMSectorStrategy(
        broker=broker,
        massive=massive,
        universe={"Industrials": ["GE"]},
        capital_usd=1000.0,
        max_positions=1,
        dry_run=False,
        fetcher=_StubFetcher(),
    )
    strategy.run_once()
    assert broker.opens == [("GE", "buy", 1000.0)]


def test_alpaca_and_ondo_stubs_raise_not_implemented():
    alpaca = AlpacaBroker(api_key="k", api_secret="s")
    with pytest.raises(NotImplementedError):
        alpaca.market_open("AAPL", "buy", 100.0)
    with pytest.raises(NotImplementedError):
        alpaca.get_open_positions()
    # Healthcheck stays offline-safe: reports whether creds are present.
    assert alpaca.healthcheck() is True

    ondo = OndoBroker(wallet_name="hermes")
    with pytest.raises(NotImplementedError):
        ondo.market_open("USDY", "buy", 100.0)
    assert ondo.healthcheck() is True


def test_strategy_live_with_stubbed_broker_captures_skip(caplog):
    """Live run + stub broker must not crash — it must log and record a skip."""
    report = _make_report([("machinery", "Industrials")])
    snapshots = {
        "GE": FundamentalSnapshot("GE", "Industrials", pe_ratio=15.0, forward_pe=13.0, eps_growth_next_year=20.0, raw={}),
    }
    massive = _FakeMassive({"Industrials": 25.0}, snapshots)

    class _StubFetcher:
        def fetch_report(self, kind, url=None):  # noqa: ARG002
            return report

    strategy = ISMSectorStrategy(
        broker=AlpacaBroker(api_key="k", api_secret="s"),
        massive=massive,
        universe={"Industrials": ["GE"]},
        capital_usd=1000.0,
        max_positions=1,
        dry_run=False,
        fetcher=_StubFetcher(),
    )
    summary = strategy.run_once()
    # Summary should still record the attempt; actual order call was skipped.
    assert summary["result"][0]["stubbed"] is True


def test_stock_journal_tags_trades_with_stock_asset_class(tmp_path):
    from trading.journal import AssetClass, SQLiteStorage, TradeJournal
    from trading.stocks.journal import StockJournal

    db = tmp_path / "trades.db"
    journal = TradeJournal(storage=SQLiteStorage(db_path=str(db)))
    stock_j = StockJournal(journal=journal)

    trade = stock_j.record_entry(
        symbol="AAPL",
        direction="long",
        entry_price=180.0,
        size_usd=500.0,
        environment=TradeEnvironment.PAPER,
        strategy_name="ism-sector",
    )
    assert trade.asset_class == AssetClass.STOCK
    assert trade.symbol == "AAPL"

    history = stock_j.history()
    assert len(history) == 1
    assert history[0].asset_class == AssetClass.STOCK
