"""
Internal ISM release calendar, sourced from FMP.

Why FMP and not the ISM website: the official calendar at
https://www.ismworld.org/.../rob-report-calendar/ redirects to an SSO
login wall. FMP's ``/stable/economic-calendar`` mirrors the same release
dates and is reachable with the API key the rest of this module already
uses.

We persist a normalized calendar per year into
``stocks_history/calendar/ism_<year>.json`` so the repo always has the
last refresh on hand. The file is intentionally overwritten on each
refresh — these dates are forward-looking forecasts and FMP fills in
later months as they get closer (it currently publishes ~4 months
ahead). Run a refresh periodically to extend the horizon.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

import httpx

from trading.stocks.data_provider import _maybe_load_repo_dotenv_once

logger = logging.getLogger(__name__)


FMP_CALENDAR_URL = "https://financialmodelingprep.com/stable/economic-calendar"


CalendarKind = Literal["manufacturing", "services"]


# FMP renames Services back and forth with "Non-Manufacturing"; older
# releases use the legacy label. We accept both and tag them as services.
_KIND_FROM_EVENT = {
    "ISM Manufacturing PMI": "manufacturing",
    "ISM Services PMI": "services",
    "ISM Non-Manufacturing PMI": "services",
}

_MONTH_ABBREV = {
    name: idx + 1
    for idx, name in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    )
}


class ISMCalendarError(RuntimeError):
    """Raised when the FMP economic calendar can't be fetched or parsed."""


@dataclass
class ISMCalendarRelease:
    """One ISM headline release (Manufacturing or Services PMI)."""

    kind: CalendarKind
    release_at_utc: str          # ISO 8601, e.g. "2026-04-01T14:00:00+00:00"
    release_date: str            # YYYY-MM-DD
    covers_month: str | None     # YYYY-MM the release describes (may be None)
    event: str                   # original FMP event label
    impact: str | None
    source: str = "fmp"


@dataclass
class ISMCalendar:
    """The full year of normalized ISM releases."""

    year: int
    generated_at: str
    source: str
    source_url: str
    releases: list[ISMCalendarRelease] = field(default_factory=list)

    def by_kind(self, kind: CalendarKind) -> list[ISMCalendarRelease]:
        return [r for r in self.releases if r.kind == kind]

    def as_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "generated_at": self.generated_at,
            "source": self.source,
            "source_url": self.source_url,
            "releases": [asdict(r) for r in self.releases],
        }


# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch_ism_calendar(
    year: int,
    *,
    api_key: str | None = None,
    http: httpx.Client | None = None,
    persist: bool = True,
    snapshot_dir: str | Path | None = None,
) -> ISMCalendar:
    """Pull the ISM release calendar for ``year`` from FMP and normalize it."""
    _maybe_load_repo_dotenv_once()
    key = api_key or os.getenv("FMP_API_KEY") or os.getenv("MASSIVE_API_KEY")
    if not key:
        raise ISMCalendarError(
            "FMP_API_KEY is not set. Add it to .env or pass api_key= explicitly."
        )

    params = {
        "from": f"{year:04d}-01-01",
        "to": f"{year:04d}-12-31",
        "apikey": key,
    }
    rows = _http_get_json(FMP_CALENDAR_URL, params=params, http=http)
    releases = _normalize_releases(rows)

    calendar = ISMCalendar(
        year=year,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source="fmp_economic_calendar",
        source_url=FMP_CALENDAR_URL,
        releases=releases,
    )

    if persist:
        _persist_calendar(calendar, snapshot_dir=snapshot_dir)
    return calendar


def _http_get_json(
    url: str,
    *,
    params: dict[str, Any],
    http: httpx.Client | None,
) -> list[dict[str, Any]]:
    client = http or httpx.Client(timeout=20.0)
    try:
        resp = client.get(url, params=params)
    finally:
        if http is None:
            client.close()
    if resp.status_code != 200:
        raise ISMCalendarError(
            f"FMP economic-calendar returned HTTP {resp.status_code}: "
            f"{resp.text[:200]}"
        )
    payload = resp.json()
    if not isinstance(payload, list):
        raise ISMCalendarError(
            f"FMP economic-calendar payload is not a list (got {type(payload).__name__}): "
            f"{str(payload)[:200]}"
        )
    return payload


def _normalize_releases(
    rows: Iterable[dict[str, Any]],
) -> list[ISMCalendarRelease]:
    """Filter for ISM headline PMIs, dedupe per (kind, covers_month, date)."""
    by_key: dict[tuple[str, str, str], ISMCalendarRelease] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (row.get("country") or "").upper() != "US":
            continue
        event = (row.get("event") or "").strip()
        kind = _kind_for_event(event)
        if kind is None:
            continue

        release_at = _parse_release_at(row.get("date"))
        if release_at is None:
            continue
        covers_month = _covers_month(release_at, event)
        release = ISMCalendarRelease(
            kind=kind,  # type: ignore[arg-type]
            release_at_utc=release_at.isoformat(),
            release_date=release_at.date().isoformat(),
            covers_month=covers_month,
            event=event,
            impact=row.get("impact"),
        )
        # Dedupe: prefer the modern "Services" label over legacy
        # "Non-Manufacturing" when both exist for the same month.
        key = (kind, covers_month or release.release_date, release.release_date)
        existing = by_key.get(key)
        if existing is None or _prefer(release, existing):
            by_key[key] = release

    out = list(by_key.values())
    out.sort(key=lambda r: (r.release_at_utc, r.kind))
    return out


def _kind_for_event(event: str) -> str | None:
    """Map an FMP event string to our normalized kind."""
    base = re.sub(r"\s*\(.*\)$", "", event).strip()
    return _KIND_FROM_EVENT.get(base)


def _prefer(new: ISMCalendarRelease, existing: ISMCalendarRelease) -> bool:
    """Modern naming wins; otherwise stable on first-seen."""
    new_modern = "Services" in new.event or "Manufacturing" in new.event and "Non" not in new.event
    existing_modern = (
        "Services" in existing.event
        or ("Manufacturing" in existing.event and "Non" not in existing.event)
    )
    if new_modern and not existing_modern:
        return True
    return False


def _parse_release_at(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # FMP uses "YYYY-MM-DD HH:MM:SS" without explicit timezone — treat as UTC.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def _covers_month(release_at: datetime, event: str) -> str | None:
    """Derive the data month covered by the release.

    Prefers the "(Mar)" / "(Mar 2026)" parenthetical suffix when present;
    falls back to "release month - 1" since ISM publishes the prior month.
    """
    suffix = re.search(r"\(([A-Za-z]{3})(?:\s+(\d{4}))?\)", event)
    if suffix:
        month_token = suffix.group(1).title()
        month_idx = _MONTH_ABBREV.get(month_token)
        if month_idx is not None:
            year = int(suffix.group(2)) if suffix.group(2) else _infer_data_year(
                release_at, month_idx
            )
            return f"{year:04d}-{month_idx:02d}"
    # Fallback: prior month relative to the release.
    if release_at.month == 1:
        return f"{release_at.year - 1:04d}-12"
    return f"{release_at.year:04d}-{release_at.month - 1:02d}"


def _infer_data_year(release_at: datetime, data_month: int) -> int:
    """If a release in January describes December, the data year is prior."""
    if release_at.month == 1 and data_month == 12:
        return release_at.year - 1
    return release_at.year


# ── Persistence ───────────────────────────────────────────────────────────────
def _persist_calendar(
    calendar: ISMCalendar,
    *,
    snapshot_dir: str | Path | None,
) -> Path:
    root = Path(snapshot_dir) if snapshot_dir is not None else _default_calendar_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"ism_{calendar.year}.json"
    # Overwrite on purpose — these dates are forward-looking forecasts that
    # FMP extends as months approach, unlike the immutable monthly snapshots.
    path.write_text(json.dumps(calendar.as_dict(), indent=2, default=str))
    return path


def load_calendar(
    year: int,
    *,
    snapshot_dir: str | Path | None = None,
    fetch_if_missing: bool = False,
) -> ISMCalendar | None:
    """Read the persisted calendar for ``year``; optionally fetch on miss."""
    root = Path(snapshot_dir) if snapshot_dir is not None else _default_calendar_dir()
    path = root / f"ism_{year}.json"
    if path.exists():
        payload = json.loads(path.read_text())
        return _calendar_from_dict(payload)
    if fetch_if_missing:
        return fetch_ism_calendar(year, snapshot_dir=snapshot_dir)
    return None


def _calendar_from_dict(payload: dict[str, Any]) -> ISMCalendar:
    releases = [
        ISMCalendarRelease(
            kind=r["kind"],
            release_at_utc=r["release_at_utc"],
            release_date=r["release_date"],
            covers_month=r.get("covers_month"),
            event=r.get("event", ""),
            impact=r.get("impact"),
            source=r.get("source", "fmp"),
        )
        for r in payload.get("releases", [])
    ]
    return ISMCalendar(
        year=int(payload["year"]),
        generated_at=str(payload.get("generated_at", "")),
        source=str(payload.get("source", "fmp_economic_calendar")),
        source_url=str(payload.get("source_url", FMP_CALENDAR_URL)),
        releases=releases,
    )


# ── Helpers consumed by CLI / Hermes / agent ──────────────────────────────────
def next_release(
    *,
    kind: CalendarKind | None = None,
    today: date | None = None,
    snapshot_dir: str | Path | None = None,
) -> ISMCalendarRelease | None:
    """Return the next upcoming release after ``today`` from stored calendars."""
    today = today or datetime.now(timezone.utc).date()
    candidates: list[ISMCalendarRelease] = []
    for year in (today.year, today.year + 1):
        calendar = load_calendar(year, snapshot_dir=snapshot_dir)
        if calendar is None:
            continue
        for release in calendar.releases:
            if kind is not None and release.kind != kind:
                continue
            if datetime.fromisoformat(release.release_at_utc).date() >= today:
                candidates.append(release)
    if not candidates:
        return None
    candidates.sort(key=lambda r: r.release_at_utc)
    return candidates[0]


def release_for_month(
    *,
    kind: CalendarKind,
    data_year: int,
    data_month: int,
    snapshot_dir: str | Path | None = None,
) -> ISMCalendarRelease | None:
    """Return the release that publishes data for ``data_year-data_month``."""
    target = f"{data_year:04d}-{data_month:02d}"
    # Data published in month N+1 of release_year (or +1 year for Dec data).
    release_year = data_year + (1 if data_month == 12 else 0)
    calendar = load_calendar(release_year, snapshot_dir=snapshot_dir)
    if calendar is None:
        return None
    for release in calendar.releases:
        if release.kind == kind and release.covers_month == target:
            return release
    return None


def _default_calendar_dir() -> Path:
    # Repo-committed alongside the monthly ISM snapshots.
    return Path(__file__).resolve().parents[2] / "stocks_history" / "calendar"
