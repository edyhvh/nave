from __future__ import annotations

import json
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


def test_ism_report_marks_current_when_month_matches_calendar(
    monkeypatch,
) -> None:
    report = _make_report()
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
    monkeypatch.setattr(
        "trading.stocks.reporting._latest_expected_covers_month",
        lambda **kwargs: "2026-03",
    )

    payload = build_ism_industry_report(
        fetcher=_StubFetcher(report),
        massive=_StubMassive(snapshots, {"Industrials": 25.0}),
        universe={"Industrials": ["GE"]},
        top_n=1,
        max_sectors_per_trend=1,
    )

    assert payload["report_month_key"] == "2026-03"
    assert payload["expected_covers_month"] == "2026-03"
    assert payload["is_expected_month"] is True
    assert payload["freshness_status"] == "current"


def test_ism_report_marks_stale_when_month_mismatches_calendar(
    monkeypatch,
) -> None:
    report = _make_report()
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
    monkeypatch.setattr(
        "trading.stocks.reporting._latest_expected_covers_month",
        lambda **kwargs: "2026-04",
    )

    payload = build_ism_industry_report(
        fetcher=_StubFetcher(report),
        massive=_StubMassive(snapshots, {"Industrials": 25.0}),
        universe={"Industrials": ["GE"]},
        top_n=1,
        max_sectors_per_trend=1,
    )

    assert payload["report_month_key"] == "2026-03"
    assert payload["expected_covers_month"] == "2026-04"
    assert payload["is_expected_month"] is False
    assert payload["freshness_status"] == "stale"


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


def test_ism_report_persists_monthly_snapshot(tmp_path) -> None:
    report = _make_report()
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
        ),
        "NUE": FundamentalSnapshot(
            symbol="NUE",
            sector="Materials",
            pe_ratio=14.0,
            forward_pe=12.0,
            eps_growth_next_year=9.0,
            raw={},
            industry="Steel",
            eps_growth_source="vendor_estimate",
            eps_growth_confidence=1.0,
        ),
    }

    payload = build_ism_industry_report(
        fetcher=_StubFetcher(report),
        massive=_StubMassive(
            snapshots, {"Industrials": 25.0, "Materials": 18.0}),
        universe={"Industrials": ["GE"], "Materials": ["NUE"]},
        top_n=2,
        max_sectors_per_trend=2,
        min_confidence=0.0,
        persist_snapshot=True,
        snapshot_dir=tmp_path,
    )

    saved_to = payload.get("saved_to")
    assert isinstance(saved_to, str)

    saved = json.loads(
        (tmp_path / "ism_manufacturing_2026-03.json").read_text())
    assert saved["report_month"] == "March 2026"
    assert saved["screened_universe"]["all_symbols"] == ["GE", "NUE"]
    assert "hottest_industries" in saved
    assert "worst_industries" in saved


def test_ism_report_monthly_snapshot_does_not_overwrite_existing_file(tmp_path) -> None:
    existing = tmp_path / "ism_manufacturing_2026-03.json"
    original = {"marker": "original", "report_month": "March 2026"}
    existing.write_text(json.dumps(original))

    report = _make_report()
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
        min_confidence=0.0,
        persist_snapshot=True,
        snapshot_dir=tmp_path,
    )

    assert payload.get("saved_to") == str(existing)
    reloaded = json.loads(existing.read_text())
    assert reloaded == original


def test_default_snapshot_dir_is_repo_committed() -> None:
    """Snapshots default to <repo>/stocks_history (not gitignored var/)."""
    from trading.stocks.reporting import _default_snapshot_dir

    default = _default_snapshot_dir()
    assert default.name == "stocks_history"
    # Must be at the repo root, not under var/.
    assert "var" not in default.parts


def test_reviewed_companies_includes_picked_and_excluded(tmp_path) -> None:
    """Snapshot must contain per-company fundamentals + selection status."""
    report = _make_report()
    snapshots = {
        "GE": FundamentalSnapshot(
            symbol="GE",
            sector="Industrials",
            pe_ratio=15.0,
            forward_pe=13.5,
            eps_growth_next_year=12.0,
            raw={},
            industry="Aerospace & Defense",
            eps_growth_source="fmp_analyst_estimate",
            eps_growth_confidence=1.0,
            company_name="General Electric",
        ),
        "NUE": FundamentalSnapshot(
            symbol="NUE",
            sector="Materials",
            pe_ratio=14.0,
            forward_pe=12.0,
            eps_growth_next_year=2.0,  # below 5% floor → excluded
            raw={},
            industry="Steel",
            eps_growth_source="fmp_analyst_estimate",
            eps_growth_confidence=1.0,
            company_name="Nucor",
        ),
    }

    payload = build_ism_industry_report(
        fetcher=_StubFetcher(report),
        massive=_StubMassive(
            snapshots, {"Industrials": 25.0, "Materials": 18.0}),
        universe={"Industrials": ["GE"], "Materials": ["NUE"]},
        top_n=2,
        max_sectors_per_trend=2,
        min_confidence=0.0,
        min_eps_growth_next_year=5.0,
    )

    reviewed = payload["reviewed_companies"]
    by_symbol = {row["symbol"]: row for row in reviewed}
    assert set(by_symbol) == {"GE", "NUE"}

    ge = by_symbol["GE"]
    assert ge["side"] == "long"
    assert ge["pe_ratio"] == 15.0
    assert ge["forward_pe"] == 13.5
    assert ge["eps_growth_next_year"] == 12.0
    assert ge["eps_growth_source"] == "fmp_analyst_estimate"
    assert ge["company_name"] == "General Electric"
    assert ge["confidence"] is not None
    assert ge["score"] is not None
    assert ge["exclusion_reason"] is None

    nue = by_symbol["NUE"]
    assert nue["side"] == "not_selected"
    assert nue["pe_ratio"] == 14.0
    assert nue["confidence"] is None
    # Excluded by the EPS-growth floor in manufacturing mode.
    assert nue["exclusion_reason"] == "below_min_eps_growth (5.0%)"


def test_reviewed_companies_services_mode_records_pe_filter(tmp_path) -> None:
    """Services mode must record per-company sector PE + exclusion reason."""
    report = ISMReport(
        kind="services",
        report_month="March 2026",
        pmi=52.1,
        source_url="https://example.test/ism-services",
        expanding=[
            ISMIndustryRanking(
                industry="information",
                trend="expanding",
                rank=1,
                gics_sector="Communication Services",
            )
        ],
        contracting=[],
    )
    snapshots = {
        "META": FundamentalSnapshot(
            symbol="META",
            sector="Communication Services",
            pe_ratio=22.0,
            forward_pe=18.0,
            eps_growth_next_year=15.0,
            raw={},
            industry="Internet Content & Information",
            eps_growth_source="fmp_analyst_estimate",
            eps_growth_confidence=1.0,
            company_name="Meta",
            revenue_growth_long_term=12.0,
            revenue_growth_source="fmp_analyst_estimate",
        ),
        "NFLX": FundamentalSnapshot(
            symbol="NFLX",
            sector="Communication Services",
            pe_ratio=45.0,  # >= sector avg → excluded
            forward_pe=35.0,
            eps_growth_next_year=20.0,
            raw={},
            industry="Entertainment",
            eps_growth_source="fmp_analyst_estimate",
            eps_growth_confidence=1.0,
            company_name="Netflix",
            revenue_growth_long_term=14.0,
            revenue_growth_source="fmp_analyst_estimate",
        ),
    }

    payload = build_ism_industry_report(
        kind="services",
        mode="services",
        fetcher=_StubFetcher(report),
        massive=_StubMassive(
            snapshots, {"Communication Services": 30.0}),
        universe={"Communication Services": ["META", "NFLX"]},
        top_n=2,
        max_sectors_per_trend=1,
        min_confidence=0.0,
    )

    by_symbol = {row["symbol"]: row for row in payload["reviewed_companies"]}
    meta = by_symbol["META"]
    nflx = by_symbol["NFLX"]
    assert meta["side"] == "long"
    assert meta["sector_avg_pe"] == 30.0
    assert meta["revenue_growth_long_term"] == 12.0
    assert nflx["side"] == "not_selected"
    assert nflx["sector_avg_pe"] == 30.0
    assert nflx["exclusion_reason"].startswith("pe_above_sector_avg")
