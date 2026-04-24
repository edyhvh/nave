"""
Massive.com fundamentals client.

Massive publishes a REST API with company fundamentals (PE ratio, forward
PE, EPS growth) and sector averages. Their free tier caps usage at
**5 requests per minute**, so this client enforces a conservative local
rate limit and exposes a small batch helper that interleaves tickers
sector-by-sector to maximize the information-per-call ratio.

Config (read from environment — see ``.env.example``):
    MASSIVE_API_KEY         — required for all calls
    MASSIVE_BASE_URL        — optional override, defaults to
                              https://api.massive.com/v1
    MASSIVE_RATE_LIMIT_RPM  — override rate limit (default 5)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

logger = logging.getLogger(__name__)


DEFAULT_BASE_URL = "https://api.massive.com/v1"
DEFAULT_RATE_LIMIT_RPM = 5  # free tier
RATE_WINDOW_SECONDS = 60.0


class MassiveRateLimitError(RuntimeError):
    """Raised when the local rate limiter couldn't drain in time."""


@dataclass
class FundamentalSnapshot:
    """Minimal per-ticker payload used by the screener."""

    symbol: str
    sector: str | None
    pe_ratio: float | None
    forward_pe: float | None
    eps_growth_next_year: float | None
    raw: dict[str, Any]


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
                raise MassiveRateLimitError(
                    f"Massive rate limit not drained after {max_wait_seconds:.0f}s; "
                    f"limit={self.rpm} rpm. Consider upgrading the plan or widening "
                    "the screener batch size."
                )
            logger.debug("Rate-limit pause: sleeping %.2fs", sleep_for)
            time.sleep(sleep_for)


class MassiveClient:
    """Thin, rate-limited REST client for Massive.com fundamentals."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        rpm: int | None = None,
        timeout_seconds: float = 15.0,
        http: httpx.Client | None = None,
    ):
        self.api_key = api_key or os.getenv("MASSIVE_API_KEY")
        if not self.api_key:
            logger.warning(
                "MASSIVE_API_KEY is not set. MassiveClient calls will fail at runtime."
            )
        self.base_url = (base_url or os.getenv("MASSIVE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        rpm_value = rpm if rpm is not None else int(
            os.getenv("MASSIVE_RATE_LIMIT_RPM", str(DEFAULT_RATE_LIMIT_RPM))
        )
        self._bucket = _TokenBucket(rpm=rpm_value)
        self.timeout_seconds = timeout_seconds
        self._http = http  # allow test injection; real client built lazily

    # ── Internals ----------------------------------------------------
    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        headers = {
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            "Accept": "application/json",
        }
        self._http = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        return self._http

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(
                "MASSIVE_API_KEY is not configured. Add it to .env or pass api_key= explicitly."
            )
        self._bucket.acquire()
        resp = self._client().get(path, params=params or {})
        if resp.status_code == 429:
            # Massive uses 429 with a Retry-After header when the server-side
            # limiter kicks in. Surface a clean error so the caller can back off.
            retry_after = resp.headers.get("Retry-After", "?")
            raise MassiveRateLimitError(
                f"Massive returned 429 (Retry-After={retry_after}). "
                "Raise MASSIVE_RATE_LIMIT_RPM or upgrade the plan."
            )
        resp.raise_for_status()
        return resp.json()

    # ── Public API ---------------------------------------------------
    def fundamentals(self, symbol: str) -> FundamentalSnapshot:
        """Fetch PE / forward PE / EPS growth for a single ticker."""
        raw = self._get(f"/fundamentals/{symbol.upper()}")
        return _snapshot_from_payload(symbol.upper(), raw)

    def sector_average_pe(self, sector: str) -> float | None:
        """Return the sector-average PE ratio, or ``None`` if unavailable."""
        raw = self._get("/sectors/averages", params={"sector": sector})
        value = raw.get("pe_ratio") if isinstance(raw, dict) else None
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def batch_fundamentals(self, symbols: Iterable[str]) -> list[FundamentalSnapshot]:
        """Fetch fundamentals for many tickers, one call each, rate-limited.

        Intentionally sequential. The free plan's 5-rpm ceiling makes
        parallelism useless — our local bucket would just serialize them
        anyway, and sequential calls make 429 handling simpler.
        """
        out: list[FundamentalSnapshot] = []
        for sym in symbols:
            try:
                out.append(self.fundamentals(sym))
            except MassiveRateLimitError:
                raise
            except Exception:
                logger.exception("Massive fundamentals fetch failed for %s", sym)
        return out


def _snapshot_from_payload(symbol: str, payload: dict[str, Any]) -> FundamentalSnapshot:
    """Map a Massive fundamentals JSON payload to our minimal dataclass.

    Field names follow Massive's public schema (pe_ratio, forward_pe,
    eps_growth). When the schema evolves, only this adapter needs to change.
    """
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    return FundamentalSnapshot(
        symbol=symbol,
        sector=data.get("sector"),
        pe_ratio=_to_float(data.get("pe_ratio")),
        forward_pe=_to_float(data.get("forward_pe")),
        eps_growth_next_year=_to_float(
            data.get("eps_growth_next_year") or data.get("eps_growth")
        ),
        raw=data,
    )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
