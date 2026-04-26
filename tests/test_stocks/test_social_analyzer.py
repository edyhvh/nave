from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from trading.stocks.social_analyzer import (
    X_POSTS_ANALYSIS_SYSTEM_PROMPT,
    analyze_tickers,
    render_sheet,
)
from trading.stocks.x_client import XClient, XClientError, XPost


class _StubXClient(XClient):
    """Returns canned posts; never touches twscrape or the network."""

    def __init__(self, posts_by_ticker: dict[str, list[XPost]], *, raise_for: set[str] | None = None):
        self._posts_by_ticker = posts_by_ticker
        self._raise_for = raise_for or set()

    async def fetch_recent_posts(self, ticker, *, days, limit):  # noqa: ARG002
        if ticker in self._raise_for:
            raise XClientError(f"forced failure for {ticker}")
        return list(self._posts_by_ticker.get(ticker, []))


def _make_post(ticker: str, *, idx: int, likes: int = 10) -> XPost:
    return XPost(
        id=f"{ticker}-{idx}",
        ticker=ticker,
        text=f"$"f"{ticker} looks good at this level — earnings beat, guidance raised.",
        username=f"user{idx}",
        display_name=f"User {idx}",
        created_at=datetime(2026, 4, 25, 10, idx, tzinfo=timezone.utc).isoformat(),
        likes=likes,
        replies=2,
        retweets=3,
        views=1000 + idx,
        url=f"https://x.com/user{idx}/status/{ticker}-{idx}",
    )


def test_analyze_tickers_packages_prompt_and_posts(tmp_path) -> None:
    posts = {
        "NVDA": [_make_post("NVDA", idx=i, likes=100 - i) for i in range(3)],
        "AAPL": [_make_post("AAPL", idx=i) for i in range(2)],
    }
    payload = analyze_tickers(
        ["NVDA", "AAPL"],
        days=7,
        limit_per_ticker=10,
        client=_StubXClient(posts),
        snapshot_dir=tmp_path,
    )

    assert payload["tickers"] == ["NVDA", "AAPL"]
    assert payload["total_posts"] == 5
    assert payload["fetch_errors"] == {}
    assert payload["summary_stats"]["NVDA"]["post_count"] == 3
    assert payload["summary_stats"]["NVDA"]["top_post_url"].endswith("NVDA-0")

    prompt = payload["analysis_prompt"]
    assert prompt["system"] == X_POSTS_ANALYSIS_SYSTEM_PROMPT
    assert "NVDA, AAPL" in prompt["user"]
    assert "last 7 days" in prompt["user"]
    assert "Total posts analyzed: 5" in prompt["user"]
    # Posts must be inlined so the LLM has them in-context.
    assert "@user0" in prompt["user"]
    assert "earnings beat" in prompt["user"]


def test_analyze_tickers_persists_snapshot_to_repo_dir(tmp_path) -> None:
    posts = {"NVDA": [_make_post("NVDA", idx=0)]}
    payload = analyze_tickers(
        ["NVDA"],
        client=_StubXClient(posts),
        snapshot_dir=tmp_path,
    )
    saved = payload.get("saved_to")
    assert isinstance(saved, str)
    reloaded = json.loads(open(saved).read())
    assert reloaded["tickers"] == ["NVDA"]
    assert reloaded["analysis_prompt"]["system"] == X_POSTS_ANALYSIS_SYSTEM_PROMPT


def test_analyze_tickers_records_fetch_errors_without_failing(tmp_path) -> None:
    posts = {"NVDA": [_make_post("NVDA", idx=0)]}
    payload = analyze_tickers(
        ["NVDA", "BROKEN"],
        client=_StubXClient(posts, raise_for={"BROKEN"}),
        persist=False,
    )
    assert payload["total_posts"] == 1
    assert "BROKEN" in payload["fetch_errors"]
    assert payload["summary_stats"]["BROKEN"]["post_count"] == 0


def test_analyze_tickers_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        analyze_tickers([], client=_StubXClient({}), persist=False)


def test_default_snapshot_dir_lives_in_repo_root() -> None:
    from trading.stocks.social_analyzer import _default_snapshot_dir

    default = _default_snapshot_dir()
    assert default.name == "stocks_history"
    assert "var" not in default.parts


def test_render_sheet_does_not_crash() -> None:
    posts = {"NVDA": [_make_post("NVDA", idx=0)]}
    payload = analyze_tickers(
        ["NVDA"],
        client=_StubXClient(posts),
        persist=False,
    )
    # Smoke test — must not raise on a real Rich console.
    render_sheet(payload)
