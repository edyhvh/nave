"""
FMP-backed fundamentals client for the ISM stocks workflow.

Financial Modeling Prep exposes stable endpoints for company profiles,
TTM valuation ratios, analyst estimates, and sector PE snapshots. This
module maps those responses into the narrow screening snapshot used by
the ISM integration.

Config (read from environment):
    FMP_API_KEY            — primary credential for all calls
    FMP_BASE_URL           — optional override, defaults to
                             https://financialmodelingprep.com/stable
    FMP_RATE_LIMIT_RPM     — override local rate limit (default 300)

Backwards compatibility:
    MASSIVE_API_KEY / MASSIVE_BASE_URL / MASSIVE_RATE_LIMIT_RPM are still
    honored as fallbacks so existing scripts do not break immediately.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

import httpx

logger = logging.getLogger(__name__)

_DOTENV_ATTEMPTED = False


DEFAULT_BASE_URL = "https://financialmodelingprep.com/stable"
DEFAULT_RATE_LIMIT_RPM = 300
RATE_WINDOW_SECONDS = 60.0
DEFAULT_429_RETRIES = 2
DEFAULT_CACHE_TTL_SECONDS = 60 * 60 * 24
EPS_NEAR_ZERO_THRESHOLD = 0.10
EPS_GROWTH_HARD_CAP = 150.0


class FMPRateLimitError(RuntimeError):
    """Raised when the local rate limiter couldn't drain in time."""


MassiveRateLimitError = FMPRateLimitError


@dataclass
class FundamentalSnapshot:
    """Minimal per-ticker payload used by the screener."""

    symbol: str
    sector: str | None
    pe_ratio: float | None
    forward_pe: float | None
    eps_growth_next_year: float | None
    raw: dict[str, Any]
    industry: str | None = None
    eps_growth_source: str | None = None
    eps_growth_confidence: float = 0.0
    company_name: str | None = None
    # Long-term / multi-year revenue growth forecast — used by Services mode.
    # FMP analyst-estimates multi-year CAGR first, yfinance trailing
    # revenueGrowth as fallback. Percent units (e.g. 12.5 means +12.5%).
    revenue_growth_long_term: float | None = None
    revenue_growth_source: str | None = None


class _TokenBucket:
    """Sliding-window rate limiter: at most ``rpm`` calls per 60 seconds."""

    def __init__(self, rpm: int):
        self.rpm = max(1, rpm)
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, *, max_wait_seconds: float = 90.0) -> None:
        deadline = time.monotonic() + max_wait_seconds
        while True:
            with self._lock:
                now = time.monotonic()
                # Drop entries older than the window.
                while self._calls and (now - self._calls[0]) >= RATE_WINDOW_SECONDS:
                    self._calls.popleft()
                if len(self._calls) < self.rpm:
                    self._calls.append(now)
                    return
                sleep_for = RATE_WINDOW_SECONDS - (now - self._calls[0]) + 0.05
            if time.monotonic() + sleep_for > deadline:
                raise FMPRateLimitError(
                    f"FMP rate limit not drained after {max_wait_seconds:.0f}s; "
                    f"limit={self.rpm} rpm. Consider upgrading the plan or widening "
                    "the screener batch size."
                )
            logger.debug("Rate-limit pause: sleeping %.2fs", sleep_for)
            time.sleep(sleep_for)


class FMPClient:
    """Thin, rate-limited REST client for FMP fundamentals."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        rpm: int | None = None,
        timeout_seconds: float = 15.0,
        http: httpx.Client | None = None,
    ):
        _maybe_load_repo_dotenv_once()
        self.api_key = api_key or os.getenv("FMP_API_KEY") or os.getenv("MASSIVE_API_KEY")
        if not self.api_key:
            logger.warning(
                "FMP_API_KEY is not set. FMPClient calls will fail at runtime."
            )
        self.base_url = (
            base_url or os.getenv("FMP_BASE_URL") or os.getenv("MASSIVE_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        rpm_value = rpm if rpm is not None else int(
            os.getenv("FMP_RATE_LIMIT_RPM")
            or os.getenv("MASSIVE_RATE_LIMIT_RPM")
            or str(DEFAULT_RATE_LIMIT_RPM)
        )
        self._bucket = _TokenBucket(rpm=rpm_value)
        self.timeout_seconds = timeout_seconds
        self._http = http  # allow test injection; real client built lazily
        self._fundamentals_cache: dict[str, FundamentalSnapshot] = {}
        self._sector_avg_cache: dict[str, float | None] = {}
        self._unsupported_endpoints: set[str] = set()
        self.cache_ttl_seconds = int(
            os.getenv("FMP_CACHE_TTL_SECONDS")
            or os.getenv("MASSIVE_CACHE_TTL_SECONDS")
            or str(DEFAULT_CACHE_TTL_SECONDS)
        )
        self.cache_dir: Path | None = None
        if http is None:
            default_cache_dir = Path(__file__).resolve().parents[2] / "var" / "fmp_cache"
            self.cache_dir = Path(
                os.getenv("FMP_CACHE_DIR")
                or os.getenv("MASSIVE_CACHE_DIR")
                or str(default_cache_dir)
            )
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ── Internals ----------------------------------------------------
    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        headers = {
            "Accept": "application/json",
        }
        self._http = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        return self._http

    def _get(self, path: str, *, params: dict[str, Any] | None = None, max_retries: int | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(
                "FMP_API_KEY is not configured. Add it to .env or pass api_key= explicitly."
            )
        retries = max_retries if max_retries is not None else int(
            os.getenv("FMP_429_RETRIES")
            or os.getenv("MASSIVE_429_RETRIES")
            or str(DEFAULT_429_RETRIES)
        )
        request_params = dict(params or {})
        request_params["apikey"] = self.api_key
        for attempt in range(retries + 1):
            self._bucket.acquire()
            resp = self._client().get(path, params=request_params)
            if resp.status_code != 429:
                if resp.status_code == 403:
                    raise RuntimeError(
                        "FMP rejected the request. Check FMP_API_KEY and account permissions."
                    )
                resp.raise_for_status()
                return resp.json()

            retry_after_raw = resp.headers.get("Retry-After")
            retry_after = _to_float(retry_after_raw) or RATE_WINDOW_SECONDS
            if attempt >= retries:
                raise FMPRateLimitError(
                    f"FMP returned 429 (Retry-After={retry_after_raw or '?'}) after retries. "
                    "Raise FMP_RATE_LIMIT_RPM, reduce universe size, or upgrade the plan."
                )

            wait_seconds = max(1.0, min(retry_after, RATE_WINDOW_SECONDS + 5.0))
            logger.warning(
                "FMP 429 for %s (attempt %d/%d); sleeping %.1fs",
                path,
                attempt + 1,
                retries + 1,
                wait_seconds,
            )
            time.sleep(wait_seconds)

        raise FMPRateLimitError("Unexpected 429 retry loop termination")

    def _get_optional(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path in self._unsupported_endpoints:
            return {}
        try:
            return self._get(path, params=params, max_retries=0)
        except FMPRateLimitError:
            logger.debug("FMP rate-limited for optional endpoint %s; skipping", path)
            return {}
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {402, 404}:
                self._unsupported_endpoints.add(path)
                logger.info(
                    "FMP endpoint %s is unavailable on the current plan (status=%s); using fallback data",
                    path,
                    exc.response.status_code,
                )
                return {}
            raise

    def _cache_path(self, namespace: str, key: str) -> Path:
        if self.cache_dir is None:
            raise RuntimeError("Persistent cache is disabled for this client instance")
        safe_key = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in key.lower())
        return self.cache_dir / f"{namespace}_{safe_key}.json"

    def _cache_get(self, namespace: str, key: str) -> Any | None:
        if self.cache_dir is None:
            return None
        path = self._cache_path(namespace, key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        expires_at = _to_float(payload.get("expires_at"))
        if expires_at is not None and time.time() > expires_at:
            return None
        return payload.get("value")

    def _cache_put(self, namespace: str, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        if self.cache_dir is None:
            return
        path = self._cache_path(namespace, key)
        payload = {
            "expires_at": time.time() + float(ttl_seconds or self.cache_ttl_seconds),
            "value": value,
        }
        try:
            path.write_text(json.dumps(payload, default=str))
        except Exception:
            logger.debug("Failed to persist FMP cache for %s:%s", namespace, key, exc_info=True)

    # ── Public API ---------------------------------------------------
    def fundamentals(self, symbol: str) -> FundamentalSnapshot:
        """Fetch PE / forward PE / EPS growth for a single ticker."""
        key = symbol.upper()
        cached = self._fundamentals_cache.get(key)
        if cached is not None:
            return cached
        cached_payload = self._cache_get("fundamentals", key)
        if isinstance(cached_payload, dict):
            try:
                snap = FundamentalSnapshot(**cached_payload)
                # If the cached snapshot is missing pe/eps, company_name,
                # or long-term revenue growth (e.g. stored before a given
                # enrichment was added), enrich now and re-cache.
                if (
                    (snap.pe_ratio is None and snap.eps_growth_next_year is None)
                    or snap.company_name is None
                    or snap.revenue_growth_long_term is None
                ):
                    snap = _yfinance_enrich(snap)
                    self._cache_put("fundamentals", key, asdict(snap))
                self._fundamentals_cache[key] = snap
                return snap
            except TypeError:
                logger.debug("Ignoring stale fundamentals cache for %s", key, exc_info=True)

        try:
            profile = self._get("/profile", params={"symbol": key}, max_retries=0)
            ratios_ttm = self._get_optional("/ratios-ttm", params={"symbol": key})
            analyst_estimates = self._get_optional(
                "/analyst-estimates",
                params={"symbol": key, "period": "annual", "page": 0, "limit": 4},
            )
            raw = {
                "profile": profile,
                "ratios_ttm": ratios_ttm,
                "analyst_estimates": analyst_estimates,
            }
            snap = _snapshot_from_payload(key, raw)
        except FMPRateLimitError:
            logger.debug("FMP rate-limited for %s; falling back to yfinance", key)
            snap = _snapshot_from_payload(key, {})

        # FMP free tier omits pe/eps from /profile and gates /ratios-ttm
        # behind a paid plan — fill the gaps from Yahoo Finance. Also enrich
        # when the long-term revenue growth forecast (used by Services mode)
        # isn't available from FMP analyst estimates.
        if (
            (snap.pe_ratio is None and snap.eps_growth_next_year is None)
            or snap.company_name is None
            or snap.revenue_growth_long_term is None
        ):
            snap = _yfinance_enrich(snap)
        self._fundamentals_cache[key] = snap
        self._cache_put("fundamentals", key, asdict(snap))
        return snap

    def sector_average_pe(self, sector: str, *, symbols: Iterable[str] | None = None) -> float | None:
        """Return a sector-average PE from FMP snapshot data or local fallbacks."""
        cached = self._sector_avg_cache.get(sector)
        if cached is not None:
            return cached
        cached_value = self._cache_get("sector_pe", sector)
        if cached_value is not None:
            value = _to_float(cached_value)
            self._sector_avg_cache[sector] = value
            return value

        try:
            payload = self._get_optional("/sector-pe-snapshot")
            rows = _records_from_payload(payload)
            normalized_sector = _normalize_label(sector)
            for row in rows:
                candidate_sector = _first_non_empty_text(
                    row,
                    "sector",
                    "name",
                    "sectorName",
                    "sector_name",
                )
                if candidate_sector and _normalize_label(candidate_sector) == normalized_sector:
                    pe_value = _first_float(
                        row,
                        "pe",
                        "peRatio",
                        "pe_ratio",
                        "averagePE",
                        "sectorPE",
                    )
                    if pe_value is not None:
                        self._sector_avg_cache[sector] = pe_value
                        self._cache_put("sector_pe", sector, pe_value)
                        return pe_value
        except Exception:
            logger.debug("FMP sector PE snapshot unavailable for %s", sector, exc_info=True)

        pe_values: list[float] = []
        for sym in symbols or []:
            try:
                snap = self.fundamentals(sym)
            except Exception:
                continue
            if snap.pe_ratio is not None and snap.pe_ratio > 0:
                pe_values.append(snap.pe_ratio)
        avg = (sum(pe_values) / len(pe_values)) if pe_values else None
        self._sector_avg_cache[sector] = avg
        if avg is not None:
            self._cache_put("sector_pe", sector, avg)
        return avg

    def batch_fundamentals(self, symbols: Iterable[str]) -> list[FundamentalSnapshot]:
        """Fetch fundamentals for many tickers, one call each, rate-limited.

        Intentionally sequential. The free plan's 5-rpm ceiling makes
        parallelism unnecessary for the current ISM universe, and sequential
        calls keep retry handling simple.
        """
        out: list[FundamentalSnapshot] = []
        for sym in symbols:
            try:
                out.append(self.fundamentals(sym))
            except FMPRateLimitError:
                raise
            except Exception as exc:
                logger.warning("FMP fundamentals fetch failed for %s: %s", sym, exc)
        return out


MassiveClient = FMPClient


def _snapshot_from_payload(symbol: str, payload: dict[str, Any]) -> FundamentalSnapshot:
    """Map vendor payloads to our screening snapshot.

    The FMP-backed path passes a merged payload containing profile,
    ratios-ttm, and analyst estimates. The adapter remains tolerant of the
    older flat payload shape so compatibility tests and fixtures keep working.
    """
    if not isinstance(payload, dict):
        payload = {}

    profile = _record_from_payload(payload.get("profile", payload.get("data", payload)))
    ratios = _record_from_payload(payload.get("ratios_ttm", payload.get("ratios", {})))
    estimate_row = _pick_best_analyst_estimate(payload.get("analyst_estimates", []))

    sector = _first_non_empty_text(profile, "sector", "gicsSector", "gics_sector")
    industry = _first_non_empty_text(
        profile,
        "industry",
        "sicDescription",
        "sic_description",
        "gicsIndustry",
        "gics_industry",
        "naics_description",
    )
    company_name = _first_non_empty_text(profile, "companyName", "name", "company_name")
    pe_ratio = _first_float(
        ratios,
        "peRatioTTM",
        "priceToEarningsRatioTTM",
        "peRatio",
        "priceEarningsRatio",
        "pe_ratio",
    ) or _first_float(profile, "pe")

    current_price = _first_float(profile, "price")
    current_eps = _first_float(profile, "eps", "epsTTM") or _first_float(
        ratios,
        "netIncomePerShareTTM",
        "epsTTM",
    )
    next_eps = _first_float(
        estimate_row,
        "estimatedEpsAvg",
        "estimatedEPSAvg",
        "estimatedEps",
        "epsEstimate",
        "epsAvg",
    )
    eps_growth_value, eps_growth_confidence = _estimate_eps_growth_from_fmp(
        current_eps=current_eps,
        next_eps=next_eps,
        estimate_row=estimate_row,
    )
    revenue_lt_growth = _estimate_long_term_revenue_growth_from_fmp(
        payload.get("analyst_estimates", []),
    )
    forward_pe = _first_float(
        estimate_row,
        "forwardPE",
        "forwardPe",
    ) or _first_float(
        ratios,
        "forwardPERatio",
        "forwardPERatioTTM",
        "forwardPeRatio",
    )
    if forward_pe is None and current_price is not None and next_eps not in (None, 0):
        forward_pe = current_price / next_eps

    raw = {
        "profile": profile,
        "ratios_ttm": ratios,
        "analyst_estimate": estimate_row,
    }

    if sector is None and "sector" in payload:
        sector = _first_non_empty_text(payload, "sector")
    if pe_ratio is None:
        pe_ratio = _to_float(payload.get("pe_ratio"))
    if forward_pe is None:
        forward_pe = _to_float(payload.get("forward_pe"))
    if eps_growth_value is None:
        eps_growth_value, eps_growth_confidence = _sanitize_vendor_eps_growth(
            symbol,
            _to_float(payload.get("eps_growth_next_year") or payload.get("eps_growth")),
        )

    return FundamentalSnapshot(
        symbol=symbol,
        sector=sector,
        pe_ratio=pe_ratio,
        forward_pe=forward_pe,
        eps_growth_next_year=eps_growth_value,
        raw=raw,
        industry=industry,
        eps_growth_source="fmp_analyst_estimate" if next_eps is not None else "vendor_estimate",
        eps_growth_confidence=eps_growth_confidence,
        company_name=company_name,
        revenue_growth_long_term=revenue_lt_growth,
        revenue_growth_source="fmp_analyst_estimate" if revenue_lt_growth is not None else None,
    )


def _estimate_long_term_revenue_growth_from_fmp(payload: Any) -> float | None:
    """Compute a multi-year revenue CAGR from FMP analyst-estimate rows.

    Services mode wants a "5-year / long-term" revenue growth forecast.
    FMP's /analyst-estimates returns up to ~4 forward years with
    ``estimatedRevenueAvg``; the CAGR across those rows is our best
    free-tier proxy for a long-term forecast.
    """
    rows = _records_from_payload(payload)
    revenue_by_year: list[tuple[int, float]] = []
    for row in rows:
        year = _to_int(row.get("year") or row.get("calendarYear") or row.get("fiscalYear"))
        revenue = _first_float(
            row,
            "estimatedRevenueAvg",
            "estimatedRevenue",
            "revenueEstimate",
            "revenueAvg",
        )
        if year is not None and revenue is not None and revenue > 0:
            revenue_by_year.append((year, revenue))
    if len(revenue_by_year) < 2:
        return None
    revenue_by_year.sort()
    first_year, first_rev = revenue_by_year[0]
    last_year, last_rev = revenue_by_year[-1]
    span = last_year - first_year
    if span <= 0 or first_rev <= 0:
        return None
    cagr = ((last_rev / first_rev) ** (1.0 / span) - 1.0) * 100.0
    # Keep obviously broken projections out of the screener.
    if abs(cagr) > 200.0:
        return None
    return cagr


def _yfinance_enrich(snap: FundamentalSnapshot) -> FundamentalSnapshot:
    """Fill pe_ratio / forward_pe / eps_growth from Yahoo Finance when FMP is silent."""
    try:
        import yfinance as yf  # optional dependency — soft import

        info: dict[str, Any] = yf.Ticker(snap.symbol).info

        pe_ratio = snap.pe_ratio
        if pe_ratio is None:
            pe_ratio = _to_float(info.get("trailingPE"))

        forward_pe = snap.forward_pe
        if forward_pe is None:
            forward_pe = _to_float(info.get("forwardPE"))

        eps_growth = snap.eps_growth_next_year
        eps_conf = snap.eps_growth_confidence
        eps_source = snap.eps_growth_source
        # Only use yfinance EPS when FMP has no analyst estimate at all.
        # FMP data takes priority; yfinance is a fallback of last resort.
        if eps_growth is None:
            trailing_eps = _to_float(info.get("trailingEps"))
            forward_eps = _to_float(info.get("forwardEps"))
            if (
                trailing_eps is not None
                and forward_eps is not None
                and abs(trailing_eps) > EPS_NEAR_ZERO_THRESHOLD
            ):
                raw_pct = (forward_eps - trailing_eps) / abs(trailing_eps) * 100.0
                if abs(raw_pct) <= EPS_GROWTH_HARD_CAP:
                    eps_growth = raw_pct
                    eps_conf = 0.8
                    eps_source = "yfinance"
                else:
                    eps_conf = 0.5
            else:
                eps_conf = 0.5

        logger.debug(
            "yfinance enrichment for %s: pe=%s fpe=%s eps_growth=%s",
            snap.symbol,
            pe_ratio,
            forward_pe,
            eps_growth,
        )
        sector = snap.sector or (info.get("sector") or None)
        industry = snap.industry or (info.get("industry") or None)
        company_name = snap.company_name or (info.get("longName") or info.get("shortName") or None)

        # yfinance fallback for long-term revenue growth. ``revenueGrowth`` is
        # a trailing YoY figure (decimal, e.g. 0.12 = 12%), not a 5Y forecast —
        # but it's the only readily-available free signal. Used only when FMP
        # couldn't provide a multi-year CAGR.
        rev_growth_lt = snap.revenue_growth_long_term
        rev_growth_source = snap.revenue_growth_source
        if rev_growth_lt is None:
            yf_revenue_growth = _to_float(info.get("revenueGrowth"))
            if yf_revenue_growth is not None:
                rev_growth_lt = yf_revenue_growth * 100.0
                rev_growth_source = "yfinance_trailing_revenue_growth"

        return FundamentalSnapshot(
            symbol=snap.symbol,
            sector=sector,
            pe_ratio=pe_ratio,
            forward_pe=forward_pe,
            eps_growth_next_year=eps_growth,
            raw=snap.raw,
            industry=industry,
            eps_growth_source=eps_source,
            eps_growth_confidence=eps_conf,
            company_name=company_name,
            revenue_growth_long_term=rev_growth_lt,
            revenue_growth_source=rev_growth_source,
        )
    except Exception as exc:
        logger.debug("yfinance enrichment failed for %s: %s", snap.symbol, exc)
        return snap


def _record_from_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    return item
            return {}
        if isinstance(data, dict):
            return data
        return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
    return {}


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [data]
        return [payload]
    return []


def _pick_best_analyst_estimate(payload: Any) -> dict[str, Any]:
    rows = _records_from_payload(payload)
    if not rows:
        return {}

    current_year = datetime.now(timezone.utc).year
    best_row: dict[str, Any] | None = None
    best_score: tuple[int, int, int, str] | None = None
    for row in rows:
        year = _to_int(row.get("year") or row.get("calendarYear") or row.get("fiscalYear"))
        has_eps = 1 if _first_float(
            row,
            "estimatedEpsAvg",
            "estimatedEPSAvg",
            "estimatedEps",
            "epsEstimate",
            "epsAvg",
        ) is not None else 0
        future_bias = 1 if year is not None and year >= current_year else 0
        year_sort = -(year or 0)
        date_sort = str(row.get("date") or row.get("period") or "")
        score = (future_bias, has_eps, year_sort, date_sort)
        if best_score is None or score > best_score:
            best_score = score
            best_row = row
    return best_row or rows[0]


def _estimate_eps_growth_from_fmp(
    *,
    current_eps: float | None,
    next_eps: float | None,
    estimate_row: dict[str, Any],
) -> tuple[float | None, float]:
    explicit_growth = _first_float(
        estimate_row,
        "estimatedEpsGrowth",
        "epsGrowth",
        "growth",
        "growthPercentage",
    )
    if explicit_growth is not None:
        return explicit_growth, 1.0
    if next_eps is None or current_eps is None:
        return None, 0.0
    if abs(current_eps) < EPS_NEAR_ZERO_THRESHOLD:
        return None, 0.0
    growth = ((next_eps - current_eps) / abs(current_eps)) * 100.0
    confidence = 0.9
    if abs(growth) > 150.0:
        confidence = 0.65
    elif abs(growth) > 80.0:
        confidence = 0.8
    return growth, confidence


def _snapshot_from_v2_financials(symbol: str, payload: dict[str, Any]) -> FundamentalSnapshot:
    """Map Massive v2 financial rows into our screening snapshot.

    We estimate next-year EPS growth from the latest two filing rows and
    derive forward PE from the implied EPS acceleration.
    """
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []

    rows = sorted(
        (row for row in rows if isinstance(row, dict)),
        key=lambda row: _report_period_sort_key(row),
        reverse=True,
    )

    latest = rows[0] if rows else {}
    previous = _pick_previous_row(rows, latest)

    pe_ratio = _first_float(
        latest,
        "priceToEarningsRatio",
        "priceEarnings",
        "pe_ratio",
    )
    if pe_ratio is None:
        market_cap = _first_float(latest, "marketCapitalization", "market_cap")
        net_income = _first_float(latest, "netIncome", "netIncomeLoss")
        if market_cap is not None and net_income not in (None, 0):
            pe_ratio = market_cap / net_income

    eps_now = _first_float(latest, "earningsPerDilutedShare", "earningsPerBasicShare")
    eps_prev = _first_float(previous, "earningsPerDilutedShare", "earningsPerBasicShare")

    eps_growth, eps_growth_confidence = _sanitize_derived_eps_growth(symbol, eps_now, eps_prev)

    forward_pe = None
    if pe_ratio is not None and eps_growth is not None and (1.0 + eps_growth / 100.0) > 0:
        forward_pe = pe_ratio / (1.0 + eps_growth / 100.0)

    return FundamentalSnapshot(
        symbol=symbol,
        sector=_first_non_empty_text(
            latest,
            "sector",
            "gicsSector",
            "gics_sector",
        ),
        pe_ratio=pe_ratio,
        forward_pe=forward_pe,
        eps_growth_next_year=eps_growth,
        raw=latest if isinstance(latest, dict) else {},
        industry=_first_non_empty_text(
            latest,
            "industry",
            "sic_description",
            "gicsIndustry",
            "gics_industry",
            "naics_description",
        ),
        eps_growth_source="derived_from_recent_filings",
        eps_growth_confidence=eps_growth_confidence,
    )


def _sanitize_vendor_eps_growth(symbol: str, eps_growth: float | None) -> tuple[float | None, float]:
    if eps_growth is None:
        return None, 0.5  # neutral: missing data is uncertainty, not a negative signal
    return _sanitize_eps_growth_value(symbol, eps_growth, source="vendor")


def _sanitize_derived_eps_growth(
    symbol: str,
    eps_now: float | None,
    eps_prev: float | None,
) -> tuple[float | None, float]:
    if eps_now is None or eps_prev is None:
        return None, 0.5  # neutral: missing data is uncertainty, not a negative signal
    if abs(eps_prev) < EPS_NEAR_ZERO_THRESHOLD:
        logger.warning(
            "Suspicious EPS growth for %s: previous EPS %.4f is near zero; discarding growth metric",
            symbol,
            eps_prev,
        )
        return None, 0.0
    raw_growth = ((eps_now - eps_prev) / abs(eps_prev)) * 100.0
    return _sanitize_eps_growth_value(symbol, raw_growth, source="derived")


def _sanitize_eps_growth_value(
    symbol: str,
    eps_growth: float,
    *,
    source: str,
) -> tuple[float | None, float]:
    if abs(eps_growth) > EPS_GROWTH_HARD_CAP:
        logger.warning(
            "Suspicious EPS growth for %s from %s data: %.2f%% exceeds hard cap %.1f%%; discarding metric",
            symbol,
            source,
            eps_growth,
            EPS_GROWTH_HARD_CAP,
        )
        return None, 0.0
    if abs(eps_growth) > 100.0:
        logger.warning(
            "Elevated EPS growth for %s from %s data: %.2f%% flagged for lower confidence",
            symbol,
            source,
            eps_growth,
        )
        return eps_growth, 0.45 if source == "derived" else 0.6
    if abs(eps_growth) > 60.0:
        return eps_growth, 0.7 if source == "derived" else 0.85
    return eps_growth, 0.85 if source == "derived" else 1.0


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_float(obj: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in obj:
            value = _to_float(obj.get(key))
            if value is not None:
                return value
    return None


def _first_non_empty_text(obj: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None


def _normalize_label(value: str) -> str:
    return " ".join(value.lower().replace("&", "and").split())


def _pick_previous_row(rows: list[dict[str, Any]], latest: dict[str, Any]) -> dict[str, Any]:
    if not rows or not latest:
        return {}

    latest_period = str(latest.get("period") or "").strip()
    for row in rows[1:]:
        if latest_period and str(row.get("period") or "").strip() == latest_period:
            if _first_float(row, "earningsPerDilutedShare", "earningsPerBasicShare") is not None:
                return row

    for row in rows[1:]:
        if _first_float(row, "earningsPerDilutedShare", "earningsPerBasicShare") is not None:
            return row

    return {}


def _report_period_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    raw = str(row.get("reportPeriod") or row.get("calendarDate") or "")
    try:
        return (1, datetime.fromisoformat(raw).isoformat())
    except ValueError:
        return (0, raw)


def _maybe_load_repo_dotenv_once() -> None:
    """Best-effort .env bootstrap so CLI/MCP/Hermes share local credentials."""
    global _DOTENV_ATTEMPTED
    if _DOTENV_ATTEMPTED:
        return
    _DOTENV_ATTEMPTED = True

    if os.getenv("FMP_API_KEY") or os.getenv("MASSIVE_API_KEY"):
        return

    try:
        from dotenv import load_dotenv
    except Exception:
        return

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(env_path)
