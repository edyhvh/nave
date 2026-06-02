"""FMP social sentiment (Stocktwits-style aggregate) — complements X post text."""

from __future__ import annotations

import os
from typing import Any

import httpx


class FMPSocialError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.getenv("FMP_API_KEY")
    if not key:
        raise FMPSocialError("FMP_API_KEY is not set")
    return key.strip()


def fetch_social_sentiment(symbol: str, *, limit: int = 30) -> dict[str, Any]:
    """Historical social sentiment rows for a ticker (FMP stable API)."""
    sym = symbol.upper().strip()
    base = os.getenv("FMP_BASE_URL", "https://financialmodelingprep.com").rstrip("/")
    url = f"{base}/stable/historical-social-sentiment"
    params = {"symbol": sym, "apikey": _api_key()}

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, params=params)
        if resp.status_code == 404:
            # Legacy path fallback
            url = f"{base}/api/v4/historical/social-sentiment"
            resp = client.get(url, params={"symbol": sym, "page": 0, "apikey": _api_key()})
        if resp.status_code in {402, 403, 404}:
            return {
                "status": "not_on_plan",
                "symbol": sym,
                "note": (
                    "FMP social/X aggregate endpoints require a higher tier or legacy access. "
                    "Use official X API (X_BEARER_TOKEN) for post-level entry/targets."
                ),
                "http_status": resp.status_code,
            }
        if resp.status_code >= 400:
            raise FMPSocialError(f"FMP social sentiment {resp.status_code}: {resp.text[:200]}")
        rows = resp.json()

    if not isinstance(rows, list):
        rows = rows.get("data") if isinstance(rows, dict) else []
    rows = list(rows or [])[:limit]
    if not rows:
        return {"status": "none", "symbol": sym, "rows": []}

    latest = rows[0] if rows else {}
    return {
        "status": "ok",
        "symbol": sym,
        "source": "fmp_historical_social_sentiment",
        "latest": latest,
        "rows": rows,
        "summary": _summarize_rows(rows),
    }


def _summarize_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No FMP social sentiment rows."
    latest = rows[0]
    parts = []
    for key in ("stocktwitsPosts", "twitterPosts", "stocktwitsComments", "twitterComments"):
        if key in latest and latest[key] is not None:
            parts.append(f"{key}={latest[key]}")
    for key in ("stocktwitsSentiment", "twitterSentiment"):
        if key in latest and latest[key] is not None:
            parts.append(f"{key}={latest[key]}")
    date = latest.get("date") or latest.get("symbol")
    return f"FMP social snapshot ({date}): " + (", ".join(parts) if parts else "aggregate counts only")