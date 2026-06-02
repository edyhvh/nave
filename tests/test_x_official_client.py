"""Tests for X client backend selection."""

from __future__ import annotations

from trading.stocks.x_client import get_x_client


def test_get_x_client_prefers_official_when_token_set(monkeypatch) -> None:
    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    client = get_x_client()
    assert client.__class__.__name__ == "XOfficialClient"


def test_get_x_client_falls_back_to_scraper(monkeypatch) -> None:
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
    client = get_x_client()
    assert client.__class__.__name__ == "XClient"