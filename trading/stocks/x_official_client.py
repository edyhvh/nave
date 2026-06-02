"""Official X API v2 client (Bearer token) — preferred when configured."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from trading.stocks.x_client import (
    DEFAULT_LIMIT_PER_TICKER,
    DEFAULT_LOOKBACK_DAYS,
    XClientError,
    XPost,
    _build_query,
    _clean_text,
)


def official_x_configured() -> bool:
    return bool(os.getenv("X_BEARER_TOKEN") or os.getenv("TWITTER_BEARER_TOKEN"))


def _bearer_token() -> str:
    token = os.getenv("X_BEARER_TOKEN") or os.getenv("TWITTER_BEARER_TOKEN")
    if not token:
        raise XClientError(
            "X API Bearer token not set. Add X_BEARER_TOKEN to .env from "
            "https://developer.x.com/ (App → Keys → Bearer Token)."
        )
    return token.strip()


class XOfficialClient:
    """Fetch recent posts via X API v2 ``/2/tweets/search/recent`` (official)."""

    def __init__(self, *, bearer_token: str | None = None) -> None:
        self._token = bearer_token

    async def fetch_recent_posts(
        self,
        ticker: str,
        *,
        days: int = DEFAULT_LOOKBACK_DAYS,
        limit: int = DEFAULT_LIMIT_PER_TICKER,
    ) -> list[XPost]:
        try:
            import httpx
        except ImportError as exc:
            raise XClientError("httpx is required for official X API calls") from exc

        token = (self._token or _bearer_token()).strip()
        query = _build_query(ticker, days=days)
        start_time = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        max_results = max(10, min(int(limit), 100))
        params: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "start_time": start_time,
            "tweet.fields": "created_at,public_metrics,author_id",
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        headers = {"Authorization": f"Bearer {token}"}
        url = "https://api.twitter.com/2/tweets/search/recent"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 401:
                raise XClientError("X API 401 — invalid or expired Bearer token")
            if resp.status_code == 429:
                raise XClientError("X API rate limit (429) — retry later or reduce batch size")
            if resp.status_code >= 400:
                raise XClientError(f"X API error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()

        users = {
            str(u.get("id")): u
            for u in (data.get("includes") or {}).get("users") or []
        }
        posts: list[XPost] = []
        for tweet in data.get("data") or []:
            author_id = str(tweet.get("author_id") or "")
            user = users.get(author_id, {})
            metrics = tweet.get("public_metrics") or {}
            tid = str(tweet.get("id") or "")
            username = str(user.get("username") or "unknown")
            posts.append(
                XPost(
                    id=tid,
                    ticker=ticker.upper(),
                    text=_clean_text(str(tweet.get("text") or "")),
                    username=username,
                    display_name=user.get("name"),
                    created_at=str(tweet.get("created_at") or ""),
                    likes=int(metrics.get("like_count") or 0),
                    replies=int(metrics.get("reply_count") or 0),
                    retweets=int(metrics.get("retweet_count") or 0),
                    views=metrics.get("impression_count"),
                    url=f"https://x.com/{username}/status/{tid}" if tid else "",
                )
            )
        return posts