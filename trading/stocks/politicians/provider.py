"""FMP-backed Congressional disclosures (House + Senate).

Endpoints:
    GET /stable/house-latest   — most recent House (Representatives) PTRs
    GET /stable/senate-latest  — most recent Senate PTRs

Both are JSON arrays. Each row has a ``link`` to the official PDF/eFD page
which we use as a natural unique ID for deduplication across scans.

Config (environment):
    FMP_API_KEY    — credential, shared with the fundamentals client
    FMP_BASE_URL   — optional override, defaults to FMP /stable
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://financialmodelingprep.com/stable"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_429_RETRIES = 2
DEFAULT_RETRY_WAIT_SECONDS = 2.0
HOUSE_ENDPOINT = "/house-latest"
SENATE_ENDPOINT = "/senate-latest"


class PoliticianTradesError(RuntimeError):
    """Raised when the upstream provider returns an unexpected response."""


@dataclass(frozen=True)
class PoliticianTrade:
    """One disclosed transaction from House or Senate filings."""

    chamber: str  # "house" or "senate"
    symbol: str | None
    politician: str
    party: str | None
    state: str | None
    district: str | None
    owner: str | None  # Self / Spouse / Joint / Dependent
    asset_description: str | None
    asset_type: str | None  # Stock / Option / etc.
    transaction_type: str | None  # Purchase / Sale / Exchange
    amount_range: str | None  # bucket string, e.g. "$1,001 - $15,000"
    transaction_date: str | None  # ISO date
    disclosure_date: str | None  # ISO date
    link: str  # source URL — natural unique key for dedup

    @property
    def unique_id(self) -> str:
        return self.link


class FMPPoliticianTradesProvider:
    """Thin client over FMP house-latest + senate-latest endpoints."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        http: httpx.Client | None = None,
    ):
        from core.env import load_repo_dotenv

        load_repo_dotenv()
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise PoliticianTradesError(
                "FMP_API_KEY is not configured. Add it to .env or pass api_key= explicitly."
            )
        self.base_url = (
            base_url or os.getenv("FMP_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._http = http

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                base_url=self.base_url,
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
        return self._http

    def _get_list(self, path: str) -> list[dict[str, Any]]:
        retries = int(
            os.getenv("FMP_POLITICIANS_429_RETRIES")
            or os.getenv("FMP_429_RETRIES")
            or str(DEFAULT_429_RETRIES)
        )
        for attempt in range(retries + 1):
            resp = self._client().get(path, params={"apikey": self.api_key})
            if resp.status_code == 429:
                retry_after_raw = resp.headers.get("Retry-After")
                if attempt >= retries:
                    raise PoliticianTradesError(
                        f"FMP {path} rate-limited after {retries + 1} attempts "
                        f"(Retry-After={retry_after_raw or '?'}). "
                        "Quota likely exhausted; reduce frequency, split keys, or upgrade the plan."
                    )
                wait_seconds = _retry_wait_seconds(
                    attempt=attempt,
                    retry_after_raw=retry_after_raw,
                )
                logger.warning(
                    "FMP 429 for %s (attempt %d/%d); sleeping %.1fs",
                    path,
                    attempt + 1,
                    retries + 1,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
                continue

            if resp.status_code == 403:
                raise PoliticianTradesError(
                    f"FMP rejected {path} (403). Check FMP_API_KEY and plan permissions."
                )
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise PoliticianTradesError(
                    f"FMP {path} returned HTTP {resp.status_code}."
                ) from exc

            try:
                payload = resp.json()
            except Exception as exc:
                raise PoliticianTradesError(
                    f"FMP {path} returned non-JSON response ({resp.status_code})."
                ) from exc
            if not isinstance(payload, list):
                raise PoliticianTradesError(
                    f"FMP {path} returned non-list payload: {type(payload).__name__}"
                )
            return payload

        raise PoliticianTradesError(
            f"Unexpected retry termination for {path}.")

    def fetch_house(self) -> list[PoliticianTrade]:
        return [_parse_row("house", row) for row in self._get_list(HOUSE_ENDPOINT)]

    def fetch_senate(self) -> list[PoliticianTrade]:
        return [_parse_row("senate", row) for row in self._get_list(SENATE_ENDPOINT)]

    def fetch_all(self) -> list[PoliticianTrade]:
        return self.fetch_house() + self.fetch_senate()


def _parse_row(chamber: str, row: dict[str, Any]) -> PoliticianTrade:
    first = str(row.get("firstName") or "").strip()
    last = str(row.get("lastName") or "").strip()
    name = (f"{first} {last}".strip()) or str(
        row.get("office") or "").strip() or "Unknown"

    district_raw = row.get("district")
    district = str(district_raw).strip() if district_raw else None
    state: str | None = None
    if district:
        # "OH 05" / "IN03" — first two non-space chars are the state code.
        compact = district.replace(" ", "")
        state = compact[:2].upper() if len(compact) >= 2 else None

    link = str(row.get("link") or "").strip()
    if not link:
        # FMP occasionally omits the link; synthesize a stable surrogate so
        # dedup remains deterministic across scans.
        link = (
            "missing-link::"
            f"{chamber}::{row.get('disclosureDate', '')}::"
            f"{row.get('symbol', '')}::{name}::"
            f"{row.get('transactionDate', '')}::{row.get('amount', '')}"
        )

    return PoliticianTrade(
        chamber=chamber,
        symbol=(str(row.get("symbol")).strip()
                or None) if row.get("symbol") else None,
        politician=name,
        party=(str(row.get("party")).strip()
               or None) if row.get("party") else None,
        state=state,
        district=district,
        owner=(str(row.get("owner")).strip()
               or None) if row.get("owner") else None,
        asset_description=(
            str(row.get("assetDescription")).strip() or None
        ) if row.get("assetDescription") else None,
        asset_type=(str(row.get("assetType")).strip()
                    or None) if row.get("assetType") else None,
        transaction_type=(str(row.get("type")).strip()
                          or None) if row.get("type") else None,
        amount_range=(str(row.get("amount")).strip()
                      or None) if row.get("amount") else None,
        transaction_date=(
            str(row.get("transactionDate")).strip() or None
        ) if row.get("transactionDate") else None,
        disclosure_date=(
            str(row.get("disclosureDate")).strip() or None
        ) if row.get("disclosureDate") else None,
        link=link,
    )


def _retry_wait_seconds(*, attempt: int, retry_after_raw: str | None) -> float:
    retry_after = _to_float(retry_after_raw)
    if retry_after is not None:
        return max(1.0, min(retry_after, 65.0))
    return min(DEFAULT_RETRY_WAIT_SECONDS * (2 ** attempt), 65.0)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
