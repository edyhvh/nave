"""ISM scraper unit tests — parsing, sector mapping, fallback behavior."""

from __future__ import annotations

import pytest

from trading.stocks.ism_scraper import (
    GICS_MAPPING,
    ISMReportFetcher,
    _looks_like_ism_captcha,
    _parse_industry_list,
    _strip_html,
)


FIXTURE_MANUFACTURING = """
<html><body>
<h1>March 2026 Manufacturing ISM&reg; Report On Business&reg;</h1>
<p>The Manufacturing PMI&reg; registered 52.3 percent.</p>
<p>The eight industries reporting growth in March, in order, are:
Machinery; Chemical Products; Computer &amp; Electronic Products;
Fabricated Metal Products; Food, Beverage &amp; Tobacco Products;
Primary Metals; Transportation Equipment; and Electrical Equipment,
Appliances &amp; Components.</p>
<p>The six industries reporting contraction in March, in order, are:
Wood Products; Apparel, Leather &amp; Allied Products; Paper Products;
Plastics &amp; Rubber Products; Nonmetallic Mineral Products;
and Furniture &amp; Related Products.</p>
</body></html>
"""

FIXTURE_SERVICES = """
<html><body>
<h1>March 2026 Services ISM Report On Business</h1>
<p>The Services PMI registered 55.1 percent.</p>
<p>The nine industries reporting growth in March, in order, are:
Information; Finance &amp; Insurance; Health Care &amp; Social Assistance;
Real Estate, Rental &amp; Leasing; Utilities; Transportation &amp;
Warehousing; Retail Trade; Construction; and Educational Services.</p>
<p>The two industries reporting contraction in March, in order, are:
Mining; and Accommodation &amp; Food Services.</p>
</body></html>
"""


def test_gics_mapping_covers_all_eleven_sectors():
    """Sanity: the mapping must span every standard GICS sector."""
    sectors = set(GICS_MAPPING.values())
    assert len(sectors) == 11, sectors


def test_strip_html_removes_scripts_and_normalizes_whitespace():
    src = "<html><body><script>evil()</script><p>Hello\n\n world</p></body></html>"
    assert _strip_html(src) == "Hello world"


def test_parse_manufacturing_report():
    fetcher = ISMReportFetcher()
    report = fetcher._parse(
        FIXTURE_MANUFACTURING, kind="manufacturing", source_url="fixture://m"
    )

    assert report.kind == "manufacturing"
    assert report.report_month == "March 2026"
    assert report.pmi == 52.3
    assert len(report.expanding) == 8
    assert report.expanding[0].industry == "machinery"
    assert report.expanding[0].gics_sector == "Industrials"
    assert len(report.contracting) == 6
    assert report.contracting[0].industry == "wood products"
    assert report.contracting[0].gics_sector == "Materials"


def test_parse_services_report():
    fetcher = ISMReportFetcher()
    report = fetcher._parse(
        FIXTURE_SERVICES, kind="services", source_url="fixture://s"
    )

    assert report.kind == "services"
    assert report.pmi == 55.1
    sectors = report.by_sector("expanding")
    # Order matters: expanding industries resolve to these sectors without dupes.
    assert sectors[0] == "Communication Services"  # "information" ⇒ CommS
    assert "Financials" in sectors
    assert "Health Care" in sectors


def test_by_sector_deduplicates_preserving_order():
    fetcher = ISMReportFetcher()
    report = fetcher._parse(
        FIXTURE_MANUFACTURING, kind="manufacturing", source_url="fixture://m"
    )
    sectors = report.by_sector("expanding")
    # Two industries map to Materials (Chemical, Primary Metals) — must appear once.
    assert sectors.count("Materials") == 1


def test_parse_industry_list_handles_trailing_and_and_semicolons():
    body = "Machinery; Chemical Products; and Computer & Electronic Products"
    rankings = _parse_industry_list(f"industries reporting growth: {body}.", trend="expanding")
    assert [r.industry for r in rankings] == [
        "machinery",
        "chemical products",
        "computer & electronic products",
    ]


def test_parse_missing_sections_returns_empty():
    """A report with neither list should produce empty rankings, not raise."""
    fetcher = ISMReportFetcher()
    report = fetcher._parse(
        "<html><body><p>Nothing here.</p></body></html>",
        kind="manufacturing",
        source_url="fixture://empty",
    )
    assert report.expanding == []
    assert report.contracting == []
    assert report.pmi is None


def test_fetch_with_playwright_raises_helpful_error_when_unavailable(monkeypatch):
    """If playwright isn't installed, the fetcher must tell the user how to fix it."""
    monkeypatch.setitem(__import__("sys").modules, "playwright.sync_api", None)
    fetcher = ISMReportFetcher(use_playwright=True)
    with pytest.raises(RuntimeError, match="Playwright is not installed"):
        fetcher._fetch_with_playwright("https://example.com")


def test_resolve_latest_release_prefers_prnewswire_from_roundup(monkeypatch):
    fetcher = ISMReportFetcher()

    monkeypatch.setattr(
        fetcher,
        "_resolve_latest_roundup_url",
        lambda kind: "https://www.ismworld.org/x/ism-pmi-reports-roundup-march-2026-manufacturing/",
    )
    monkeypatch.setattr(
        fetcher,
        "_extract_prnewswire_url",
        lambda roundup_url, kind: "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-52-7-march-2026-ism-manufacturing-pmi-report-302730721.html",
    )

    url = fetcher._resolve_latest_release("manufacturing")
    assert "prnewswire.com" in url
    assert "manufacturing-pmi" in url


def test_extract_prnewswire_url_prefers_kind_specific_link(monkeypatch):
    fetcher = ISMReportFetcher()
    html = """
    <a href="https://www.prnewswire.com/news-releases/other-release-1.html">x</a>
    <a href="https://www.prnewswire.com/news-releases/services-pmi-at-54-march-2026-ism-services-pmi-report-302734026.html">y</a>
    """
    monkeypatch.setattr(fetcher, "_fetch_html", lambda url: html)

    picked = fetcher._extract_prnewswire_url("https://www.ismworld.org/roundup", kind="services")
    assert picked is not None
    assert "services-pmi" in picked


def test_detects_ism_captcha_page():
    captcha_html = """
    <html><body>
    <form name="captcha_form"></form>
    <script src="https://www.google.com/recaptcha/api.js?render=x"></script>
    </body></html>
    """
    assert _looks_like_ism_captcha(captcha_html, url="https://www.ismworld.org/path")
    assert not _looks_like_ism_captcha(captcha_html, url="https://example.com/path")
