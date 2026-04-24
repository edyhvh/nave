"""
ISM "Report On Business®" scraper.

Two data paths:

  1. **Headline PMI via FRED** — the FRED series ``NAPM`` (Manufacturing
     composite PMI) and ``NMFBAI`` (Services Business Activity Index) are
     already accessible through the ``FRED_API_KEY`` this repo already
     ships with. Fast, free, low-risk.

  2. **Industry rankings via the ISM press release** — the monthly
     "Manufacturing ISM® Report On Business®" press releases publish an
     ordered list of industries *reporting growth* and *reporting
     contraction*. These lists are rendered as plain static HTML on
     ismworld.org, so ``httpx`` + ``BeautifulSoup`` is enough. A
     ``Playwright``-backed fetcher is reserved as a fallback for sources
     that turn out to be JS-rendered (e.g. Investing.com).

Only the industry ordering matters for the screener — the raw PMI value
is a sanity check.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

import httpx

logger = logging.getLogger(__name__)


# ── ISM industry → GICS sector mapping ────────────────────────────────────
# Published ISM categories are industry-level; we roll them up to the 11
# GICS sectors used by the Massive.com fundamentals API so the downstream
# screener can ask "which tickers belong to this sector?".
GICS_MAPPING: dict[str, str] = {
    # Manufacturing industries
    "apparel, leather & allied products": "Consumer Discretionary",
    "chemical products": "Materials",
    "computer & electronic products": "Information Technology",
    "electrical equipment, appliances & components": "Industrials",
    "fabricated metal products": "Industrials",
    "food, beverage & tobacco products": "Consumer Staples",
    "furniture & related products": "Consumer Discretionary",
    "machinery": "Industrials",
    "miscellaneous manufacturing": "Industrials",
    "nonmetallic mineral products": "Materials",
    "paper products": "Materials",
    "petroleum & coal products": "Energy",
    "plastics & rubber products": "Materials",
    "primary metals": "Materials",
    "printing & related support activities": "Industrials",
    "textile mills": "Consumer Discretionary",
    "transportation equipment": "Industrials",
    "wood products": "Materials",
    # Services industries (selected — full list is longer but these cover
    # the screeners we ship today)
    "accommodation & food services": "Consumer Discretionary",
    "agriculture, forestry, fishing & hunting": "Materials",
    "arts, entertainment & recreation": "Communication Services",
    "construction": "Industrials",
    "educational services": "Consumer Discretionary",
    "finance & insurance": "Financials",
    "health care & social assistance": "Health Care",
    "information": "Communication Services",
    "management of companies & support services": "Industrials",
    "mining": "Materials",
    "professional, scientific & technical services": "Industrials",
    "public administration": "Industrials",
    "real estate, rental & leasing": "Real Estate",
    "retail trade": "Consumer Discretionary",
    "transportation & warehousing": "Industrials",
    "utilities": "Utilities",
    "wholesale trade": "Industrials",
}


# Known press-release URLs. These change monthly; the landing pages we hit
# contain links to the latest report, so we also support passing a URL
# directly to :meth:`ISMReportFetcher.fetch_report`.
ISM_MANUFACTURING_LANDING = (
    "https://www.ismworld.org/supply-management-news-and-reports/reports/"
    "ism-report-on-business/pmi/"
)
ISM_SERVICES_LANDING = (
    "https://www.ismworld.org/supply-management-news-and-reports/reports/"
    "ism-report-on-business/services/"
)


ReportKind = Literal["manufacturing", "services"]


@dataclass
class ISMIndustryRanking:
    """An ISM industry labelled as expanding, contracting, or unchanged."""

    industry: str
    trend: Literal["expanding", "contracting", "unchanged"]
    rank: int
    gics_sector: str | None = None


@dataclass
class ISMReport:
    """Parsed ISM report: headline PMI + ordered industry rankings."""

    kind: ReportKind
    report_month: str  # e.g. "March 2026"
    pmi: float | None
    expanding: list[ISMIndustryRanking] = field(default_factory=list)
    contracting: list[ISMIndustryRanking] = field(default_factory=list)
    source_url: str | None = None

    def by_sector(self, trend: str = "expanding") -> list[str]:
        """Unique GICS sectors in the requested trend bucket, ranked."""
        bucket = self.expanding if trend == "expanding" else self.contracting
        seen: dict[str, None] = {}
        for item in bucket:
            if item.gics_sector and item.gics_sector not in seen:
                seen[item.gics_sector] = None
        return list(seen.keys())


class ISMReportFetcher:
    """
    Hybrid ISM fetcher: httpx+BS4 primary, Playwright fallback.

    The default implementation uses ``httpx`` against ismworld.org press
    releases — the industry ranking sentences are plain HTML paragraphs,
    so no browser engine is required. Consumers that need to scrape a
    JS-heavy mirror (Investing.com, Trading Economics) can pass
    ``use_playwright=True`` to fall back to the async browser driver.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        use_playwright: bool = False,
        user_agent: str = (
            "Mozilla/5.0 (compatible; nave-research/0.1; +https://github.com/edyhvh/nave)"
        ),
    ):
        self.timeout_seconds = timeout_seconds
        self.use_playwright = use_playwright
        self.user_agent = user_agent

    # ── Public API ---------------------------------------------------
    def fetch_report(
        self,
        kind: ReportKind = "manufacturing",
        *,
        url: str | None = None,
    ) -> ISMReport:
        """Fetch and parse the latest ISM report for ``kind``."""
        target = url or self._resolve_latest_release(kind)
        html = self._fetch_html(target)
        return self._parse(html, kind=kind, source_url=target)

    # ── Fetch layer --------------------------------------------------
    def _fetch_html(self, url: str) -> str:
        if self.use_playwright:
            return self._fetch_with_playwright(url)
        headers = {"User-Agent": self.user_agent}
        with httpx.Client(timeout=self.timeout_seconds, headers=headers) as c:
            resp = c.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.text

    def _fetch_with_playwright(self, url: str) -> str:
        """Async Playwright path; compiled on demand so the import stays optional."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - optional path
            raise RuntimeError(
                "Playwright is not installed. Run `pip install playwright` and "
                "`python -m playwright install chromium`, or set use_playwright=False."
            ) from exc

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(user_agent=self.user_agent)
            page.goto(url, wait_until="networkidle", timeout=int(self.timeout_seconds * 1000))
            html = page.content()
            browser.close()
            return html

    def _resolve_latest_release(self, kind: ReportKind) -> str:
        """Best-effort latest-release link resolver.

        ISM keeps report-page URLs stable per month, so the landing pages
        above link to the current release. Without a verified network call
        this method returns the landing URL, which itself renders the
        latest report inline. Tests can still pass fixtures via ``url``.
        """
        return ISM_MANUFACTURING_LANDING if kind == "manufacturing" else ISM_SERVICES_LANDING

    # ── Parse layer --------------------------------------------------
    def _parse(self, html: str, *, kind: ReportKind, source_url: str) -> ISMReport:
        """Extract PMI + expanding/contracting industry ordering from the HTML."""
        text = _strip_html(html)

        month = _extract_report_month(text)
        pmi = _extract_pmi(text, kind)
        expanding = _parse_industry_list(text, trend="expanding")
        contracting = _parse_industry_list(text, trend="contracting")

        _attach_sectors(expanding)
        _attach_sectors(contracting)

        return ISMReport(
            kind=kind,
            report_month=month,
            pmi=pmi,
            expanding=expanding,
            contracting=contracting,
            source_url=source_url,
        )


# ── Parsing helpers ---------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

_MONTH_RE = re.compile(
    r"(January|February|March|April|May|June|July|"
    r"August|September|October|November|December)\s+\d{4}"
)

_PMI_RE_MANUF = re.compile(
    r"(?:Manufacturing\s+PMI|PMI®)[^\d]{0,40}(\d{2}\.\d)", re.IGNORECASE
)
_PMI_RE_SERVICES = re.compile(
    r"Services\s+(?:PMI|Index)[^\d]{0,40}(\d{2}\.\d)", re.IGNORECASE
)


def _strip_html(html: str) -> str:
    """Return plain text with normalized whitespace."""
    try:
        from bs4 import BeautifulSoup  # lazy import so the rest stays testable

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
    except ImportError:
        text = _TAG_RE.sub(" ", html)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _extract_report_month(text: str) -> str:
    match = _MONTH_RE.search(text)
    return match.group(0) if match else "Unknown"


def _extract_pmi(text: str, kind: ReportKind) -> float | None:
    pattern = _PMI_RE_MANUF if kind == "manufacturing" else _PMI_RE_SERVICES
    match = pattern.search(text)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


# Phrasing used in both Manufacturing and Services reports. ISM lists
# industries in order: "The 10 industries reporting growth ... in order are:
# X; Y; Z. The four industries reporting contraction ... are: A; B;"
_EXPANDING_RE = re.compile(
    r"industries\s+reporting\s+(?:growth|an increase in new orders)[^:]*:\s*(?P<body>[^.]+)\.",
    re.IGNORECASE,
)
_CONTRACTING_RE = re.compile(
    r"industries\s+reporting\s+(?:a\s+decrease\s+in|contraction)[^:]*:\s*(?P<body>[^.]+)\.",
    re.IGNORECASE,
)


def _parse_industry_list(
    text: str, *, trend: Literal["expanding", "contracting"]
) -> list[ISMIndustryRanking]:
    pattern = _EXPANDING_RE if trend == "expanding" else _CONTRACTING_RE
    match = pattern.search(text)
    if match is None:
        return []
    body = match.group("body")
    items = _split_industries(body)
    return [
        ISMIndustryRanking(industry=name, trend=trend, rank=i)
        for i, name in enumerate(items, start=1)
    ]


def _split_industries(body: str) -> list[str]:
    """Split a ``"; "``-delimited industry list into clean names.

    ISM uses ``;`` as the item separator, and the Oxford comma style
    ``"...; and <last>"`` to introduce the tail. Normalize that tail to
    a plain ``";"`` before splitting so ``"and "`` doesn't survive as a
    prefix on the final item (e.g. ``"and Computer Products"``).
    """
    normalized = re.sub(r"[;,]\s*and\s+", "; ", body, flags=re.IGNORECASE)
    # Fallback: catch a bare " and " between the last two items.
    normalized = re.sub(r"\s+and\s+", "; ", normalized, flags=re.IGNORECASE)
    raw = re.split(r"\s*;\s*", normalized)
    cleaned: list[str] = []
    for chunk in raw:
        name = chunk.strip().rstrip(".").strip('"')
        if not name:
            continue
        cleaned.append(name.lower())
    return cleaned


def _attach_sectors(rankings: Iterable[ISMIndustryRanking]) -> None:
    """Resolve the GICS sector for each ranking, in place."""
    for r in rankings:
        key = r.industry.strip().lower()
        r.gics_sector = GICS_MAPPING.get(key)
