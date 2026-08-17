"""
X (Twitter) post fetcher for stock tickers.

**Preferred:** official X API v2 when ``X_BEARER_TOKEN`` is set (see
``XOfficialClient`` in ``x_official_client.py``).

**Fallback:** twscrape + logged-in accounts in ``X_ACCOUNTS_DB``.

``get_x_client()`` picks the best available backend automatically.

Usage:
    client = get_x_client()
    posts = await client.fetch_recent_posts("NVDA", days=7, limit=50)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


DEFAULT_LIMIT_PER_TICKER = 50
DEFAULT_LOOKBACK_DAYS = 7


class XClientError(RuntimeError):
    """Raised when twscrape isn't installed or no accounts are configured."""


@dataclass
class XPost:
    """One X post normalized for downstream analysis / LLM consumption."""

    id: str
    ticker: str
    text: str
    username: str
    display_name: str | None
    created_at: str          # ISO 8601
    likes: int
    replies: int
    retweets: int
    views: int | None
    url: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class XClient:
    """Async X search client backed by twscrape.

    The constructor is cheap; the heavy lifting (twscrape import + API
    pool init) happens inside ``fetch_recent_posts`` so importing this
    module never fails on an environment without twscrape.
    """

    def __init__(self, *, accounts_db: str | Path | None = None):
        env_db = os.getenv("X_ACCOUNTS_DB")
        self.accounts_db = (
            Path(accounts_db) if accounts_db is not None
            else Path(env_db) if env_db
            else _default_accounts_db()
        )

    async def fetch_recent_posts(
        self,
        ticker: str,
        *,
        days: int = DEFAULT_LOOKBACK_DAYS,
        limit: int = DEFAULT_LIMIT_PER_TICKER,
    ) -> list[XPost]:
        """Search X for recent posts about ``ticker`` and return them normalized."""
        api = await self._build_api()
        query = _build_query(ticker, days=days)
        posts: list[XPost] = []
        try:
            async for tweet in api.search(query, limit=limit):
                posts.append(_to_xpost(tweet, ticker=ticker))
        except Exception as exc:  # twscrape can throw on rate limits / login fail
            raise XClientError(
                f"X search for {ticker!r} failed: {exc}. "
                "Check that X_ACCOUNTS_DB has at least one logged-in account."
            ) from exc
        return posts

    async def _build_api(self) -> Any:
        try:
            from twscrape import API  # type: ignore[import-not-found]
        except ImportError as exc:
            raise XClientError(
                "twscrape is not installed. Run: pip install twscrape, then "
                "add at least one X account via `twscrape add_accounts ...`."
            ) from exc

        if not self.accounts_db.exists():
            raise XClientError(
                f"No X accounts DB at {self.accounts_db}. "
                "Create one with `twscrape add_accounts <file> ...` and set "
                "X_ACCOUNTS_DB in .env."
            )
        return API(str(self.accounts_db))


def _build_query(ticker: str, *, days: int) -> str:
    """Build a permissive X search query for a ticker symbol."""
    sym = ticker.strip().upper()
    if ticker.strip().lower().endswith("on") and len(sym) > 3:
        sym = sym[:-2]
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    # Search the underlying cashtag; ONDO suffixes are not X cashtags.
    return f"${sym} lang:en -is:retweet since:{since}"


def _to_xpost(tweet: Any, *, ticker: str) -> XPost:
    """Map a twscrape tweet object onto our normalized XPost."""
    user = getattr(tweet, "user", None)
    username = getattr(user, "username", "") if user else ""
    display_name = getattr(user, "displayname", None) if user else None
    created = getattr(tweet, "date", None)
    if isinstance(created, datetime):
        created_iso = created.astimezone(UTC).isoformat()
    else:
        created_iso = str(created) if created else ""
    return XPost(
        id=str(getattr(tweet, "id", "")),
        ticker=ticker.upper(),
        text=_clean_text(getattr(tweet, "rawContent", "") or getattr(tweet, "content", "")),
        username=username,
        display_name=display_name,
        created_at=created_iso,
        likes=int(getattr(tweet, "likeCount", 0) or 0),
        replies=int(getattr(tweet, "replyCount", 0) or 0),
        retweets=int(getattr(tweet, "retweetCount", 0) or 0),
        views=_optional_int(getattr(tweet, "viewCount", None)),
        url=getattr(tweet, "url", "") or "",
    )


def _clean_text(text: str) -> str:
    if not text:
        return ""
    # Collapse runs of whitespace; keep the rest untouched so the LLM can
    # judge tone (capitalization, emoji etc.) faithfully.
    return re.sub(r"\s+", " ", text).strip()


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _default_accounts_db() -> Path:
    return Path(__file__).resolve().parents[2] / "var" / "x_accounts.db"


def get_x_client() -> XClient | Any:
    """Return official X API client if Bearer token is set, else twscrape."""
    try:
        from trading.stocks.data_provider import _maybe_load_repo_dotenv_once

        _maybe_load_repo_dotenv_once()
    except Exception:  # noqa: BLE001, S110
        pass

    from trading.stocks.x_official_client import XOfficialClient, official_x_configured

    if official_x_configured():
        return XOfficialClient()
    return XClient()
