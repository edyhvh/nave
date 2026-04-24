"""Massive.com client — rate-limit behavior + payload mapping."""

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
        "data": {
            "sector": "Information Technology",
            "pe_ratio": "28.5",
            "forward_pe": 24.1,
            "eps_growth": 15.3,
        }
    }
    snap = _snapshot_from_payload("AAPL", payload)
    assert snap.symbol == "AAPL"
    assert snap.sector == "Information Technology"
    assert snap.pe_ratio == 28.5
    assert snap.forward_pe == 24.1
    assert snap.eps_growth_next_year == 15.3


def test_snapshot_mapping_returns_none_for_missing_fields():
    snap = _snapshot_from_payload("XYZ", {"data": {"sector": "Unknown"}})
    assert snap.pe_ratio is None
    assert snap.forward_pe is None
    assert snap.eps_growth_next_year is None


def test_client_raises_on_429(monkeypatch):
    """A server-side 429 should raise MassiveRateLimitError, not httpx HTTPError."""

    class StubTransport(httpx.BaseTransport):
        def handle_request(self, request):
            return httpx.Response(
                429,
                headers={"Retry-After": "30"},
                json={"error": "rate limit"},
                request=request,
            )

    http = httpx.Client(base_url="https://api.massive.com/v1", transport=StubTransport())
    client = MassiveClient(api_key="test", http=http)
    with pytest.raises(MassiveRateLimitError, match="Retry-After=30"):
        client.fundamentals("AAPL")


def test_client_calls_go_through_bucket(monkeypatch):
    """Confirm each HTTP call passes through the local limiter."""
    calls = []

    class StubTransport(httpx.BaseTransport):
        def handle_request(self, request):
            return httpx.Response(
                200,
                json={"data": {"sector": "x", "pe_ratio": 10, "forward_pe": 9, "eps_growth": 5}},
                request=request,
            )

    http = httpx.Client(base_url="https://api.massive.com/v1", transport=StubTransport())
    client = MassiveClient(api_key="test", rpm=100, http=http)
    acquire = client._bucket.acquire

    def traced(*a, **kw):
        calls.append(threading.get_ident())
        return acquire(*a, **kw)

    client._bucket.acquire = traced  # type: ignore[assignment]
    client.fundamentals("AAPL")
    client.fundamentals("MSFT")
    assert len(calls) == 2
