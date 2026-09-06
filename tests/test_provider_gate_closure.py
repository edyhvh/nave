from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from research.cava.transcript import SupadataTranscriptProvider
from research.disclosure_providers import OGE_API_URL, OfficialOGEExecutiveDisclosureProvider
from research.disclosures import DisclosureWorkflow
from research.core.store import ResearchStore
from research.portfolio_providers import load_current_ism_inputs
from research.short_providers import acquire_short_snapshot
from research.shorts import StockShortResearchWorkflow
from trading.stocks.ism_identity import expected_reference, release_identity
from trading.stocks.ism_scraper import ISMReport, ISMReportFetcher

NOW = datetime(2026, 9, 7, 15, tzinfo=UTC)


def test_supadata_uses_routed_profile_not_ambient(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("SUPADATA_API_KEY", "wrong-profile-test-only")
    (tmp_path / ".env").write_text("SUPADATA_API_KEY=routed-test-only\n")

    def respond(request):
        assert request.headers["x-api-key"] == "routed-test-only"
        return httpx.Response(200, json={"content": "bounded transcript", "lang": "es"})

    provider = SupadataTranscriptProvider(http=httpx.Client(transport=httpx.MockTransport(respond)))
    assert provider.fetch("fixture").source == "supadata"
    (tmp_path / ".env").write_text("")
    assert SupadataTranscriptProvider().api_key is None


@pytest.mark.parametrize(
    "month,status",
    [
        ("August 2026", "CURRENT"),
        ("August 2022", "STALE"),
        ("July 2026", "STALE"),
        ("September 2026", "UNPUBLISHED"),
    ],
)
@pytest.mark.parametrize("kind", ["manufacturing", "services"])
def test_release_identity(month, status, kind):
    identity = release_identity(ISMReport(kind, month, 50.0), NOW)
    assert identity["release_status"] == status
    assert identity["report_type"] == kind.upper()


def test_services_publication_gate():
    assert expected_reference("services", datetime(2026, 9, 3, 13, 59, tzinfo=UTC)).month == 7
    assert expected_reference("services", datetime(2026, 9, 3, 14, 0, tzinfo=UTC)).month == 8


def test_roundup_selects_own_release_and_month(monkeypatch):
    f = ISMReportFetcher()
    current = (
        "https://www.prnewswire.com/news-releases/services-pmi-at-55-4-august-2026-report.html"
    )
    old = "https://www.prnewswire.com/news-releases/services-pmi-at-56-9-august-2022-report.html"
    html = f'<h1>ISM PMI Reports Roundup: August Services</h1><p>Services last expanded in August 2022</p><a href="{old}">history</a><a href="{current}">current</a>'
    url = "https://www.ismworld.org/blog/2026/ism-pmi-reports-roundup-august-2026-services/"
    monkeypatch.setattr(f, "_fetch_html", lambda _: html)
    assert f._extract_prnewswire_url(url, kind="services") == current
    assert f._parse(html, kind="services", source_url=url).report_month == "August 2026"


def test_headline_rankings_never_take_subindex_lists():
    html = "<h1>August 2026 Manufacturing</h1>Manufacturing PMI registered 54.6 percent. The industries reporting growth are: Primary Metals. The industries reporting a contraction are: Wood Products; and Chemical Products. WHAT RESPONDENTS ARE SAYING Employment industries reporting contraction are: Primary Metals."
    report = ISMReportFetcher()._parse(
        html, kind="manufacturing", source_url="https://ism.test/release"
    )
    assert [r.industry for r in report.contracting] == ["wood products", "chemical products"]


def test_missing_rankings_and_stale_structured_values():
    f = SimpleNamespace(fetch_report=lambda kind: ISMReport(kind, "August 2026", 55.0))
    result = load_current_ism_inputs(
        report_fetcher=f,
        now=NOW,
        fred_fetcher=lambda _: {"records": [{"date": "2022-08-01", "value": 40}]},
    )
    for kind in ("manufacturing", "services"):
        assert result[kind]["pmi"] == 55.0
        assert result[kind]["headline_status"] == "HEADLINE_VALID"
        assert result[kind]["industry_rankings_status"] == "UNAVAILABLE"
        assert result[kind]["status"] == "PARTIAL"


def test_wrong_month_never_contributes_rankings():
    f = SimpleNamespace(fetch_report=lambda kind: ISMReport(kind, "July 2026", 55.0))
    result = load_current_ism_inputs(report_fetcher=f, now=NOW, fred_fetcher=lambda _: {})
    assert all(result[k]["status"] == "UNAVAILABLE" for k in ("manufacturing", "services"))


def test_oge_current_index_known_historical_and_empty(monkeypatch):
    state = {"empty": False}

    def response(request):
        if str(request.url).startswith(OGE_API_URL):
            filtered = bool(request.url.params.get("columns[3][search][value]"))
            rows = (
                []
                if filtered and state["empty"]
                else [
                    {
                        "name": "Trump, Donald J",
                        "docDate": datetime.now(UTC).isoformat()
                        if not filtered
                        else "2025-06-13T04:00:00",
                        "type": "<a href='https://extapps2.oge.gov/filing.pdf'>Annual</a>",
                    }
                ]
            )
            return httpx.Response(200, json={"data": rows, "recordsFiltered": len(rows)})
        return httpx.Response(200, text=OGE_API_URL)

    provider = OfficialOGEExecutiveDisclosureProvider(
        http=httpx.Client(transport=httpx.MockTransport(response))
    )
    rows = provider.fetch()
    assert rows[0]["subject"] == "Trump, Donald J"
    assert rows[0]["index_added_at"] == "2025-06-13T04:00:00"
    assert rows[0]["disclosure_date"] is None
    state["empty"] = True
    assert provider.fetch() == [] and provider.health["status"] == "HEALTHY"


def test_oge_broken_schema_is_not_no_records():
    provider = OfficialOGEExecutiveDisclosureProvider(
        http=httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text="maintenance"))
        )
    )
    with pytest.raises(ValueError):
        provider.fetch()


def test_disclosure_empty_health_and_dedupe(tmp_path):
    w = DisclosureWorkflow(store=ResearchStore(tmp_path))
    statuses = {"congress": {"status": "OK"}, "executive": {"status": "OK"}}
    record = {
        "subject": "filer",
        "asset": "PUBLIC_FINANCIAL_DISCLOSURE",
        "transaction_type": "FILING_OBSERVED",
        "source_url": "https://oge.gov/a.pdf",
        "provider": "official_oge",
    }
    first = w.sync_payload(executive_records=[record, record], provider_status=statuses)
    assert first.payload["new_total"] == 1
    assert first.payload["records"][0]["provider"] == "official_oge"
    second = w.sync_payload(executive_records=[record], provider_status=statuses)
    assert second.payload["runtime_health"] == "HEALTHY"
    assert second.payload["research_result"] == "NO_NEW_RECORDS"
    broken = w.sync_payload(
        provider_status={
            "congress": {"status": "UNAVAILABLE"},
            "executive": {"status": "UNAVAILABLE"},
        }
    )
    assert broken.status.value == "DATA_UNAVAILABLE"


@pytest.mark.parametrize("age,missing", [(1, False), (10, False), (1, True)])
def test_autonomous_short_fails_closed(age, missing):
    class Provider:
        fundamentals = SimpleNamespace(
            fundamentals=lambda _: (_ for _ in ()).throw(RuntimeError("unavailable"))
        )

        def _history(self, ticker, now):
            if missing:
                raise RuntimeError("provider offline")
            stamp = now - timedelta(days=age)
            return pd.Series(range(100, 125)), "fixture", stamp.isoformat(), now.isoformat()

    rows = acquire_short_snapshot(provider=Provider(), now=NOW, universe={"AAPL": "XLK"})
    result = StockShortResearchWorkflow().scan(rows, decision_time=NOW)
    assert not result.payload["final_candidates"]
    assert result.payload["runtime_health"] == (
        "HEALTHY" if age == 1 and not missing else "DATA_UNAVAILABLE"
    )
    assert result.status.value == "INSUFFICIENT_EVIDENCE"
    if age == 1 and not missing:
        assert result.payload["rejected_candidates"][0]["factor_states"]["catalyst"] == "UNKNOWN"


def test_stale_body_at_current_url_rejected():
    with pytest.raises(ValueError, match="disagree"):
        ISMReportFetcher()._parse(
            "<h1>August 2022 Services PMI at 56.9</h1>",
            kind="services",
            source_url="https://www.prnewswire.com/news-releases/services-pmi-at-55-4-august-2026-report.html",
        )
