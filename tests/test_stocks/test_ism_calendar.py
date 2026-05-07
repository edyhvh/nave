from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from trading.stocks.ism_calendar import (
    ISMCalendarError,
    fetch_ism_calendar,
    load_calendar,
    next_release,
    recent_release,
    release_for_month,
)


# Sample shaped exactly like FMP /stable/economic-calendar.
_FMP_SAMPLE = [
    # Manufacturing PMI — modern label.
    {"date": "2026-04-01 14:00:00", "country": "US",
     "event": "ISM Manufacturing PMI (Mar)", "impact": "High"},
    {"date": "2026-04-01 14:00:00", "country": "US",
     "event": "ISM Manufacturing Employment (Mar)", "impact": "Medium"},
    {"date": "2026-05-01 14:00:00", "country": "US",
     "event": "ISM Manufacturing PMI (Apr)", "impact": "High"},
    # Services PMI — modern label.
    {"date": "2026-04-06 14:00:00", "country": "US",
     "event": "ISM Services PMI (Mar)", "impact": "High"},
    # Same Services release also published under the legacy "Non-Manufacturing"
    # label — must be deduped to the modern one.
    {"date": "2026-04-06 14:00:00", "country": "US",
     "event": "ISM Non-Manufacturing PMI (Mar)", "impact": "High"},
    # December data, released in January of the following year.
    {"date": "2027-01-05 15:00:00", "country": "US",
     "event": "ISM Manufacturing PMI (Dec)", "impact": "High"},
    # Noise we should drop:
    {"date": "2026-04-01 14:00:00", "country": "US",
     "event": "ISM Manufacturing Prices (Mar)", "impact": "Low"},
    {"date": "2026-04-01 14:00:00", "country": "EU",
     "event": "ISM Manufacturing PMI (Mar)", "impact": "High"},
]


def _client_returning(rows: list[dict]) -> httpx.Client:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert "economic-calendar" in str(request.url)
        return httpx.Response(200, json=rows)

    return httpx.Client(transport=httpx.MockTransport(_handler))


def test_fetch_filters_to_headline_us_pmis(tmp_path) -> None:
    calendar = fetch_ism_calendar(
        2026,
        api_key="test",
        http=_client_returning(_FMP_SAMPLE),
        snapshot_dir=tmp_path,
    )

    kinds = [r.kind for r in calendar.releases]
    # 2 mfg (Mar, Apr) + 1 svc (Mar) for 2026, plus 1 mfg Dec data published Jan 2027.
    # Persisted under year 2026 because we asked for year=2026; the Jan 2027 release
    # is included since it was returned by FMP for our window.
    assert kinds.count("manufacturing") == 3
    assert kinds.count("services") == 1
    # Subindex / non-US events filtered out.
    for r in calendar.releases:
        assert r.event.startswith("ISM ")
        assert "Prices" not in r.event
        assert "Employment" not in r.event


def test_services_dedupe_prefers_modern_label(tmp_path) -> None:
    calendar = fetch_ism_calendar(
        2026, api_key="test",
        http=_client_returning(_FMP_SAMPLE),
        snapshot_dir=tmp_path,
    )
    services = calendar.by_kind("services")
    assert len(services) == 1
    assert services[0].event == "ISM Services PMI (Mar)"
    assert services[0].covers_month == "2026-03"


def test_covers_month_handles_january_release_for_december_data(tmp_path) -> None:
    calendar = fetch_ism_calendar(
        2026, api_key="test",
        http=_client_returning(_FMP_SAMPLE),
        snapshot_dir=tmp_path,
    )
    dec_release = next(
        r for r in calendar.releases if r.release_date == "2027-01-05"
    )
    assert dec_release.kind == "manufacturing"
    assert dec_release.covers_month == "2026-12"


def test_persists_to_calendar_dir_and_overwrites(tmp_path) -> None:
    fetch_ism_calendar(
        2026, api_key="test",
        http=_client_returning(_FMP_SAMPLE),
        snapshot_dir=tmp_path,
    )
    path = tmp_path / "ism_2026.json"
    assert path.exists()
    first = json.loads(path.read_text())

    # Refresh with a different (smaller) payload — file must be overwritten.
    fetch_ism_calendar(
        2026, api_key="test",
        http=_client_returning(_FMP_SAMPLE[:2]),
        snapshot_dir=tmp_path,
    )
    second = json.loads(path.read_text())
    assert len(second["releases"]) < len(first["releases"])


def test_load_calendar_round_trips(tmp_path) -> None:
    fetch_ism_calendar(
        2026, api_key="test",
        http=_client_returning(_FMP_SAMPLE),
        snapshot_dir=tmp_path,
    )
    loaded = load_calendar(2026, snapshot_dir=tmp_path)
    assert loaded is not None
    assert loaded.year == 2026
    assert {r.kind for r in loaded.releases} == {"manufacturing", "services"}


def test_next_release_returns_first_after_today(tmp_path) -> None:
    fetch_ism_calendar(
        2026, api_key="test",
        http=_client_returning(_FMP_SAMPLE),
        snapshot_dir=tmp_path,
    )
    nxt = next_release(today=date(2026, 4, 2), snapshot_dir=tmp_path)
    assert nxt is not None
    assert nxt.release_date == "2026-04-06"
    assert nxt.kind == "services"

    # Filter by kind.
    nxt_mfg = next_release(
        kind="manufacturing", today=date(2026, 4, 2), snapshot_dir=tmp_path
    )
    assert nxt_mfg is not None
    assert nxt_mfg.release_date == "2026-05-01"


def test_recent_release_returns_latest_within_lookback(tmp_path) -> None:
    fetch_ism_calendar(
        2026, api_key="test",
        http=_client_returning(_FMP_SAMPLE),
        snapshot_dir=tmp_path,
    )

    rel = recent_release(today=date(2026, 4, 7), lookback_days=2, snapshot_dir=tmp_path)
    assert rel is not None
    assert rel.release_date == "2026-04-06"
    assert rel.kind == "services"


def test_recent_release_returns_none_outside_lookback(tmp_path) -> None:
    fetch_ism_calendar(
        2026, api_key="test",
        http=_client_returning(_FMP_SAMPLE),
        snapshot_dir=tmp_path,
    )

    rel = recent_release(today=date(2026, 4, 10), lookback_days=2, snapshot_dir=tmp_path)
    assert rel is None


def test_release_for_month_lookup(tmp_path) -> None:
    fetch_ism_calendar(
        2026, api_key="test",
        http=_client_returning(_FMP_SAMPLE),
        snapshot_dir=tmp_path,
    )
    rel = release_for_month(
        kind="services", data_year=2026, data_month=3, snapshot_dir=tmp_path
    )
    assert rel is not None
    assert rel.release_date == "2026-04-06"


def test_fetch_raises_without_api_key(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    # Block dotenv from re-loading and leaking the real key.
    monkeypatch.setattr(
        "trading.stocks.ism_calendar._maybe_load_repo_dotenv_once",
        lambda: None,
    )
    with pytest.raises(ISMCalendarError):
        fetch_ism_calendar(2026, snapshot_dir=tmp_path, persist=False)


def test_default_calendar_dir_is_repo_committed() -> None:
    from trading.stocks.ism_calendar import _default_calendar_dir

    p = _default_calendar_dir()
    assert p.parts[-2:] == ("stocks_history", "calendar")
    assert "var" not in p.parts
