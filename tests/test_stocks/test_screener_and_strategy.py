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
    # EPS-only scoring: GE (20%) > LIN (10%) > CAT (5%)
    assert [p.symbol for p in picks] == ["GE", "LIN", "CAT"]
    assert picks[0].score > picks[1].score > picks[2].score


def test_screener_applies_pe_and_eps_filters():
    report = _make_report([("machinery", "Industrials")])
    snapshots = {
        "GE": FundamentalSnapshot(
            "GE",
            "Industrials",
            pe_ratio=15.0,
            forward_pe=13.0,
            eps_growth_next_year=12.0,
            raw={},
        ),
        "CAT": FundamentalSnapshot(
            "CAT",
            "Industrials",
            pe_ratio=32.0,
            forward_pe=28.0,
            eps_growth_next_year=8.0,
            raw={},
        ),
        "HON": FundamentalSnapshot(
            "HON",
            "Industrials",
            pe_ratio=18.0,
            forward_pe=17.0,
            eps_growth_next_year=5.0,
            raw={},
        ),
    }
    screener = SectorScreener(
        massive=_FakeMassive({"Industrials": 25.0}, snapshots),
        universe={"Industrials": ["GE", "CAT", "HON"]},
    )

    picks = screener.rank_from_ism(
        report,
        top_n=5,
        min_eps_growth_next_year=10.0,
    )
    assert [p.symbol for p in picks] == ["GE"]


def test_screener_filters_low_confidence_when_requested():
    report = ISMReport(
        kind="manufacturing",
        report_month="March 2026",
        pmi=53.0,
        expanding=[
            ISMIndustryRanking(
                industry="printing & related support activities",
                trend="expanding",
                rank=1,
                gics_sector="Industrials",
            )
        ],
    )
    snapshots = {
        "GE": FundamentalSnapshot(
            "GE",
            "Industrials",
            pe_ratio=38.0,
            forward_pe=39.0,
            eps_growth_next_year=16.0,
            raw={},
            industry="Aerospace & Defense",
            eps_growth_source="vendor_estimate",
            eps_growth_confidence=1.0,
        ),
    }
    screener = SectorScreener(
        massive=_FakeMassive({"Industrials": 30.0}, snapshots),
        universe={"Industrials": ["GE"]},
    )

    picks = screener.rank_from_ism(report, top_n=3, min_confidence=0.7)
    assert picks == []


def test_screener_high_confidence_transportation_equipment_match():
    report = ISMReport(
        kind="manufacturing",
        report_month="March 2026",
        pmi=53.0,
        expanding=[
            ISMIndustryRanking(
                industry="transportation equipment",
                trend="expanding",
                rank=1,
                gics_sector="Industrials",
            )
        ],
    )
    snapshots = {
        "GE": FundamentalSnapshot(
            "GE",
            "Industrials",
            pe_ratio=30.0,
            forward_pe=28.0,
            eps_growth_next_year=18.0,
            raw={},
            industry="Aerospace & Defense",
            eps_growth_source="vendor_estimate",
            eps_growth_confidence=1.0,
        ),
    }
    screener = SectorScreener(
        massive=_FakeMassive({"Industrials": 32.0}, snapshots),
        universe={"Industrials": ["GE"]},
    )

    picks = screener.rank_from_ism(report, top_n=1, min_confidence=0.7)
    assert len(picks) == 1
    assert picks[0].driver_industry == "transportation equipment"
    assert picks[0].match_confidence >= 0.7


def test_screener_short_mode_prefers_high_pe_with_weak_eps():
    report = ISMReport(
        kind="manufacturing",
        report_month="March 2026",
        pmi=53.0,
        contracting=[
            ISMIndustryRanking(
                industry="wood products",
                trend="contracting",
                rank=1,
                gics_sector="Materials",
            )
        ],
    )
    snapshots = {
        "LIN": FundamentalSnapshot(
            "LIN",
            "Materials",
            pe_ratio=34.0,
            forward_pe=37.0,
            eps_growth_next_year=-8.0,
            raw={},
        ),
        "ECL": FundamentalSnapshot(
            "ECL",
            "Materials",
            pe_ratio=18.0,
            forward_pe=16.0,
            eps_growth_next_year=10.0,
            raw={},
        ),
    }
    screener = SectorScreener(
        massive=_FakeMassive({"Materials": 25.0}, snapshots),
        universe={"Materials": ["LIN", "ECL"]},
    )

    picks = screener.rank_from_ism(report, trend="contracting", side="short", top_n=2)
    assert [p.symbol for p in picks] == ["LIN", "ECL"]
    assert picks[0].side == "short"


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


def test_strategy_passes_filter_criteria_to_screener():
    report = _make_report([("machinery", "Industrials")])
    snapshots = {
        "GE": FundamentalSnapshot(
            "GE",
            "Industrials",
            pe_ratio=15.0,
            forward_pe=13.0,
            eps_growth_next_year=12.0,
            raw={},
        ),
        "CAT": FundamentalSnapshot(
            "CAT",
            "Industrials",
            pe_ratio=26.0,
            forward_pe=22.0,
            eps_growth_next_year=8.0,
            raw={},
        ),
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
        max_positions=3,
        min_eps_growth_next_year=10.0,
        dry_run=True,
        fetcher=_StubFetcher(),
    )
    summary = strategy.run_once()
    assert [item.symbol for item in summary["plan"]] == ["GE"]


def test_strategy_passes_min_confidence_to_screener():
    report = ISMReport(
        kind="manufacturing",
        report_month="March 2026",
        pmi=53.0,
        expanding=[
            ISMIndustryRanking(
                industry="printing & related support activities",
                trend="expanding",
                rank=1,
                gics_sector="Industrials",
            )
        ],
    )
    snapshots = {
        "GE": FundamentalSnapshot(
            "GE",
            "Industrials",
            pe_ratio=38.0,
            forward_pe=39.0,
            eps_growth_next_year=16.0,
            raw={},
            industry="Aerospace & Defense",
            eps_growth_source="vendor_estimate",
            eps_growth_confidence=1.0,
        ),
    }
    massive = _FakeMassive({"Industrials": 30.0}, snapshots)
    broker = _CountingBroker()

    class _StubFetcher:
        def fetch_report(self, kind, url=None):  # noqa: ARG002
            return report

    strategy = ISMSectorStrategy(
        broker=broker,
        massive=massive,
        universe={"Industrials": ["GE"]},
        capital_usd=1000.0,
        max_positions=3,
        min_confidence=0.7,
        dry_run=True,
        fetcher=_StubFetcher(),
    )
    summary = strategy.run_once()
    assert summary["plan"] == []


def test_services_mode_ranks_by_long_term_revenue_growth():
    """Services mode ranks purely by long-term revenue growth."""
    report = _make_report([("publishing industries (except internet)", "Communication Services")])
    snapshots = {
        "GOOGL": FundamentalSnapshot(
            "GOOGL",
            "Communication Services",
            pe_ratio=22.0,
            forward_pe=20.0,
            eps_growth_next_year=None,
            raw={},
            industry="Interactive Media & Services",
            revenue_growth_long_term=18.0,
            revenue_growth_source="fmp_analyst_estimate",
        ),
        "META": FundamentalSnapshot(
            "META",
            "Communication Services",
            pe_ratio=24.0,
            forward_pe=22.0,
            eps_growth_next_year=None,
            raw={},
            industry="Interactive Media & Services",
            revenue_growth_long_term=12.0,
            revenue_growth_source="fmp_analyst_estimate",
        ),
        "DIS": FundamentalSnapshot(
            "DIS",
            "Communication Services",
            pe_ratio=28.0,
            forward_pe=24.0,
            eps_growth_next_year=None,
            raw={},
            industry="Entertainment",
            revenue_growth_long_term=6.0,
            revenue_growth_source="yfinance_trailing_revenue_growth",
        ),
    }
    screener = SectorScreener(
        massive=_FakeMassive(
            sector_avg={"Communication Services": 30.0},
            snapshots=snapshots,
        ),
        universe={"Communication Services": ["GOOGL", "META", "DIS"]},
    )

    picks = screener.rank_from_ism(report, top_n=3, mode="services")
    # All three pass PE < sector_avg_pe (30.0). Rank by revenue growth.
    assert [p.symbol for p in picks] == ["GOOGL", "META", "DIS"]
    assert picks[0].revenue_growth_long_term == 18.0
    assert picks[0].mode == "services"


def test_services_mode_drops_candidates_without_revenue_forecast():
    report = _make_report([("publishing industries (except internet)", "Communication Services")])
    snapshots = {
        "GOOGL": FundamentalSnapshot(
            "GOOGL",
            "Communication Services",
            pe_ratio=22.0,
            forward_pe=20.0,
            eps_growth_next_year=25.0,  # high EPS growth — irrelevant for services
            raw={},
            industry="Interactive Media & Services",
            revenue_growth_long_term=None,  # no forecast → filtered out
        ),
        "META": FundamentalSnapshot(
            "META",
            "Communication Services",
            pe_ratio=24.0,
            forward_pe=22.0,
            eps_growth_next_year=10.0,
            raw={},
            industry="Interactive Media & Services",
            revenue_growth_long_term=11.0,
            revenue_growth_source="fmp_analyst_estimate",
        ),
    }
    screener = SectorScreener(
        massive=_FakeMassive(
            sector_avg={"Communication Services": 30.0},
            snapshots=snapshots,
        ),
        universe={"Communication Services": ["GOOGL", "META"]},
    )

    picks = screener.rank_from_ism(report, top_n=3, mode="services")
    assert [p.symbol for p in picks] == ["META"]


def test_services_mode_applies_pe_relative_filter():
    """Services mode drops companies with PE >= sector average PE."""
    report = _make_report([("publishing industries (except internet)", "Communication Services")])
    snapshots = {
        "GOOGL": FundamentalSnapshot(
            "GOOGL",
            "Communication Services",
            pe_ratio=22.0,  # under sector PE → passes
            forward_pe=20.0,
            eps_growth_next_year=None,
            raw={},
            industry="Interactive Media & Services",
            revenue_growth_long_term=15.0,
            revenue_growth_source="fmp_analyst_estimate",
        ),
        "NFLX": FundamentalSnapshot(
            "NFLX",
            "Communication Services",
            pe_ratio=40.0,  # above sector PE → fails filter
            forward_pe=36.0,
            eps_growth_next_year=None,
            raw={},
            industry="Entertainment",
            revenue_growth_long_term=20.0,  # higher growth, still excluded
            revenue_growth_source="fmp_analyst_estimate",
        ),
    }
    screener = SectorScreener(
        massive=_FakeMassive(
            sector_avg={"Communication Services": 30.0},
            snapshots=snapshots,
        ),
        universe={"Communication Services": ["GOOGL", "NFLX"]},
    )

    picks = screener.rank_from_ism(report, top_n=5, mode="services")
    assert [p.symbol for p in picks] == ["GOOGL"]


def test_manufacturing_mode_ignores_revenue_growth_field():
    """Adding revenue_growth doesn't affect manufacturing-mode ranking."""
    report = _make_report([("machinery", "Industrials")])
    snapshots = {
        "GE": FundamentalSnapshot(
            "GE", "Industrials",
            pe_ratio=15.0, forward_pe=13.0, eps_growth_next_year=20.0, raw={},
            revenue_growth_long_term=3.0,  # low rev growth
        ),
        "CAT": FundamentalSnapshot(
            "CAT", "Industrials",
            pe_ratio=22.0, forward_pe=21.0, eps_growth_next_year=5.0, raw={},
            revenue_growth_long_term=40.0,  # high rev growth but mode=manuf
        ),
    }
    screener = SectorScreener(
        massive=_FakeMassive({"Industrials": 25.0}, snapshots),
        universe={"Industrials": ["GE", "CAT"]},
    )

    picks = screener.rank_from_ism(report, top_n=2)  # default mode=manufacturing
    # EPS-growth still drives the ranking — GE (20%) beats CAT (5%).
    assert [p.symbol for p in picks] == ["GE", "CAT"]


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
