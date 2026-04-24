from __future__ import annotations

from typing import Iterable

from trading.stocks.data_provider import FundamentalSnapshot
from trading.stocks.ism_scraper import ISMIndustryRanking, ISMReport
from trading.stocks.reporting import build_ism_industry_report


class _StubFetcher:
    def __init__(self, report: ISMReport):
        self._report = report

    def fetch_report(self, *, kind: str):  # noqa: ARG002
        return self._report


class _StubMassive:
    def __init__(self, snapshots: dict[str, FundamentalSnapshot], sector_avg: dict[str, float]):
        self._snapshots = snapshots
        self._sector_avg = sector_avg

    def sector_average_pe(self, sector: str, *, symbols: Iterable[str] | None = None) -> float | None:  # noqa: ARG002
        return self._sector_avg.get(sector)

    def batch_fundamentals(self, symbols: Iterable[str]) -> list[FundamentalSnapshot]:
        return [self._snapshots[s] for s in symbols if s in self._snapshots]


def _make_report() -> ISMReport:
    return ISMReport(
        kind="manufacturing",
        report_month="March 2026",
        pmi=53.4,
        source_url="https://example.test/ism",
        expanding=[
            ISMIndustryRanking(
                industry="machinery",
                trend="expanding",
                rank=1,
                gics_sector="Industrials",
            )
        ],
        contracting=[
            ISMIndustryRanking(
                industry="wood products",
                trend="contracting",
                rank=1,
                gics_sector="Materials",
            )
        ],
    )


def test_ism_report_candidate_includes_fmp_industry() -> None:
    report = ISMReport(
        kind="manufacturing",
        report_month="March 2026",
        pmi=53.4,
        source_url="https://example.test/ism",
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
            symbol="GE",
            sector="Industrials",
            pe_ratio=15.0,
            forward_pe=13.5,
            eps_growth_next_year=12.0,
            raw={},
            industry="Aerospace & Defense",
            eps_growth_source="vendor_estimate",
            eps_growth_confidence=1.0,
        )
    }

    payload = build_ism_industry_report(
        fetcher=_StubFetcher(report),
        massive=_StubMassive(snapshots, {"Industrials": 25.0}),
        universe={"Industrials": ["GE"]},
        top_n=1,
        max_sectors_per_trend=1,
    )

    row = payload["candidates"]["expanding"][0]
    assert row["industry"] == "Aerospace & Defense"
    assert row["industry_source"] == "fmp"
    assert payload["candidates"]["longs"][0]["symbol"] == "GE"
    assert payload["candidates"]["longs"][0]["industry_momentum"] == "gaining"
    assert payload["candidates"]["longs"][0]["side"] == "long"
    assert payload["candidates"]["longs"][0]["confidence"] >= 0.7


def test_ism_report_candidate_falls_back_to_ism_industry_hint() -> None:
    report = _make_report()
    snapshots = {
        "GE": FundamentalSnapshot(
            symbol="GE",
            sector="Industrials",
            pe_ratio=15.0,
            forward_pe=13.5,
            eps_growth_next_year=12.0,
            raw={},
            industry=None,
        )
    }

    payload = build_ism_industry_report(
        fetcher=_StubFetcher(report),
        massive=_StubMassive(snapshots, {"Industrials": 25.0}),
        universe={"Industrials": ["GE"]},
        top_n=1,
        max_sectors_per_trend=1,
        min_confidence=0.0,
    )

    row = payload["candidates"]["expanding"][0]
    assert row["industry"] == "machinery"
    assert row["industry_source"] == "ism_hint"
    assert payload["summary"]["long_candidates"] == 1


def test_ism_report_filters_low_confidence_false_positive() -> None:
    report = ISMReport(
        kind="manufacturing",
        report_month="March 2026",
        pmi=53.4,
        source_url="https://example.test/ism",
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
            symbol="GE",
            sector="Industrials",
            pe_ratio=38.0,
            forward_pe=39.0,
            eps_growth_next_year=16.0,
            raw={},
            industry="Aerospace & Defense",
            eps_growth_source="vendor_estimate",
            eps_growth_confidence=1.0,
        )
    }

    payload = build_ism_industry_report(
        fetcher=_StubFetcher(report),
        massive=_StubMassive(snapshots, {"Industrials": 30.0}),
        universe={"Industrials": ["GE"]},
        top_n=5,
        max_sectors_per_trend=1,
        min_confidence=0.7,
    )

    assert payload["candidates"]["longs"] == []
