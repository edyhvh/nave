"""Fundamentals client — rate-limit behavior + payload mapping."""

from __future__ import annotations

import threading
import time

import httpx
import pytest

from trading.stocks.data_provider import (
    MassiveClient,
    MassiveRateLimitError,
    _TokenBucket,
    _snapshot_from_payload,
    _snapshot_from_v2_financials,
)


def test_token_bucket_allows_burst_up_to_limit():
    bucket = _TokenBucket(rpm=3)
    # Three consecutive acquires within the same window should be instantaneous.
    t0 = time.monotonic()
    for _ in range(3):
        bucket.acquire()
    assert time.monotonic() - t0 < 0.1


def test_token_bucket_raises_when_deadline_exceeded():
    bucket = _TokenBucket(rpm=1)
    bucket.acquire()
    # A tight deadline can't possibly be met — bucket should surface a clean error.
    with pytest.raises(MassiveRateLimitError):
        bucket.acquire(max_wait_seconds=0.2)


def test_snapshot_mapping_handles_partial_payloads():
    payload = {
        "profile": {
            "data": [{"sector": "Information Technology", "industry": "Consumer Electronics", "price": 210.0, "eps": 7.0}]
        },
        "ratios_ttm": {
            "data": [{"peRatioTTM": "28.5"}]
        },
        "analyst_estimates": {
            "data": [{"year": 2027, "estimatedEpsAvg": 8.687, "forwardPE": 24.1}]
        },
    }
    snap = _snapshot_from_payload("AAPL", payload)
    assert snap.symbol == "AAPL"
    assert snap.sector == "Information Technology"
    assert snap.pe_ratio == 28.5
    assert snap.forward_pe == 24.1
    assert round(snap.eps_growth_next_year or 0.0, 1) == 24.1


def test_snapshot_mapping_returns_none_for_missing_fields():
    snap = _snapshot_from_payload(
        "XYZ", {"profile": {"data": [{"sector": "Unknown"}]}})
    assert snap.pe_ratio is None
    assert snap.forward_pe is None
    assert snap.eps_growth_next_year is None


def test_derived_eps_growth_discards_near_zero_base():
    payload = {
        "results": [
            {
                "reportPeriod": "2026-03-31",
                "sector": "Industrials",
                "industry": "Aerospace & Defense",
                "priceToEarningsRatio": 38.0,
                "earningsPerDilutedShare": 7.2,
            },
            {
                "reportPeriod": "2025-12-31",
                "sector": "Industrials",
                "industry": "Aerospace & Defense",
                "earningsPerDilutedShare": 0.01,
            },
        ]
    }
    snap = _snapshot_from_v2_financials("GE", payload)
    assert snap.eps_growth_next_year is None
    assert snap.eps_growth_confidence == 0.0


def test_derived_eps_growth_discards_extreme_values():
    payload = {
        "results": [
            {
                "reportPeriod": "2026-03-31",
                "sector": "Industrials",
                "industry": "Aerospace & Defense",
                "priceToEarningsRatio": 38.0,
                "earningsPerDilutedShare": 7.2,
            },
            {
                "reportPeriod": "2025-12-31",
                "sector": "Industrials",
                "industry": "Aerospace & Defense",
                "earningsPerDilutedShare": 1.0,
            },
        ]
    }
    snap = _snapshot_from_v2_financials("GE", payload)
    assert snap.eps_growth_next_year is None
    assert snap.eps_growth_confidence == 0.0


def test_client_raises_on_429(monkeypatch):
    """_get() should raise MassiveRateLimitError on 429, not httpx HTTPError.
    fundamentals() catches that and falls back gracefully (no exception)."""
    monkeypatch.setattr(
        "trading.stocks.data_provider.time.sleep", lambda _: None)

    class StubTransport(httpx.BaseTransport):
        def handle_request(self, request):
            return httpx.Response(
                429,
                headers={"Retry-After": "30"},
                json={"error": "rate limit"},
                request=request,
            )

    http = httpx.Client(base_url="https://api.massive.com/v1",
                        transport=StubTransport())
    client = MassiveClient(api_key="test", http=http)

    # _get() itself still raises MassiveRateLimitError
    with pytest.raises(MassiveRateLimitError, match="Retry-After=30"):
        client._get("/profile", params={"symbol": "AAPL"})

    # fundamentals() catches the 429 and falls back; no exception propagates
    import trading.stocks.data_provider as _dp
    monkeypatch.setattr(_dp, "_yfinance_enrich", lambda snap: snap)
    result = client.fundamentals("AAPL")
    from trading.stocks.data_provider import FundamentalSnapshot
    assert isinstance(result, FundamentalSnapshot)


def test_client_calls_go_through_bucket(monkeypatch):
    """Confirm each FMP HTTP call passes through the local limiter."""
    calls = []

    class StubTransport(httpx.BaseTransport):
        def handle_request(self, request):
            path = request.url.path
            if path.endswith("/profile"):
                payload = {
                    "data": [{"sector": "x", "industry": "y", "price": 100.0, "eps": 10.0}]}
            elif path.endswith("/ratios-ttm"):
                payload = {
                    "data": [{"peRatioTTM": 10.0, "forwardPERatio": 9.0}]}
            else:
                payload = {"data": [{"year": 2027, "estimatedEpsAvg": 11.0}]}
            return httpx.Response(
                200,
                json=payload,
                request=request,
            )

    http = httpx.Client(base_url="https://api.massive.com/v1",
                        transport=StubTransport())
    client = MassiveClient(api_key="test", rpm=100, http=http)
    acquire = client._bucket.acquire

    def traced(*a, **kw):
        calls.append(threading.get_ident())
        return acquire(*a, **kw)

    client._bucket.acquire = traced  # type: ignore[assignment]
    client.fundamentals("AAPL")
    client.fundamentals("MSFT")
    assert len(calls) == 6


def test_optional_endpoint_is_suppressed_after_first_429() -> None:
    call_count = {"value": 0}

    class StubTransport(httpx.BaseTransport):
        def handle_request(self, request):
            call_count["value"] += 1
            return httpx.Response(
                429,
                headers={"Retry-After": "30"},
                json={"error": "rate limit"},
                request=request,
            )

    http = httpx.Client(base_url="https://api.massive.com/v1",
                        transport=StubTransport())
    client = MassiveClient(api_key="test", http=http)

    first = client._get_optional("/ratios-ttm", params={"symbol": "AAPL"})
    second = client._get_optional("/ratios-ttm", params={"symbol": "MSFT"})

    assert first == {}
    assert second == {}
    assert call_count["value"] == 1
