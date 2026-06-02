"""Tests for X entry/target price extraction."""

from __future__ import annotations

from trading.stocks.x_interest import build_x_market_view


def test_extract_entry_and_target_prices() -> None:
    posts = [
        {
            "text": "Buying $WFC on dips under $65, target $72 by Q3. Bullish breakout setup.",
        },
        {"text": "PT 75 if rates stay soft. Entry zone 64-66."},
    ]
    view = build_x_market_view("WFC", posts, {"post_count": 2, "total_likes": 10})
    assert view.entry_prices
    assert view.target_prices
    assert view.entry_zone is not None
    assert view.sentiment in {"bullish", "mixed", "neutral"}
    assert "bullish" in view.opinion.lower() or "Bullish" in view.opinion or view.sentiment == "bullish"


def test_x_market_view_serializes() -> None:
    view = build_x_market_view("AAPL", [], {"post_count": 0})
    data = view.as_dict()
    assert data["ticker"] == "AAPL"
    assert "entry_prices" in data