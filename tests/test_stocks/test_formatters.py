from __future__ import annotations

from trading.stocks.formatters import (
    render_ism_report_markdown_v2,
    render_x_summary_markdown_v2,
)


def test_render_ism_report_markdown_includes_top_sections() -> None:
    payload = {
        "kind": "manufacturing",
        "report_month": "April 2026",
        "pmi": 52.1,
        "criteria": {"top_n": 5, "min_confidence": 0.3},
        "freshness_status": "fresh",
        "expected_covers_month": "2026-04",
        "candidates": {
            "longs": [
                {
                    "symbol": "ETN",
                    "side": "long",
                    "sector": "Industrials",
                    "score": 0.82,
                    "confidence": 0.7,
                    "driver_industry": "Electrical Equipment",
                }
            ],
            "shorts": [
                {
                    "symbol": "GIS",
                    "side": "short",
                    "sector": "Consumer Staples",
                    "score": 0.23,
                    "confidence": 0.92,
                    "driver_industry": "food",
                }
            ],
            "ondo_shorts": [
                {
                    "symbol": "GIS",
                    "side": "short",
                    "sector": "Consumer Staples",
                    "score": 0.23,
                    "confidence": 0.92,
                    "driver_industry": "food",
                }
            ],
        },
    }

    messages = render_ism_report_markdown_v2(payload)

    assert messages
    assert "NAVE ISM MANUFACTURING" in messages[0]
    assert "ETN" in messages[0]
    assert "Top shorts" in messages[0]
    assert "Ondo\\-shortable shorts" in messages[0]
    assert "GIS" in messages[0]


def test_render_x_summary_markdown_includes_fallback_text() -> None:
    payload = {
        "tickers": ["MSFT", "PANW"],
        "days": 7,
        "total_posts": 4,
        "summary_stats": {
            "MSFT": {
                "post_count": 3,
                "total_likes": 50,
                "total_replies": 4,
                "total_retweets": 6,
                "top_post_url": "https://x.test/msft",
            },
            "PANW": {
                "post_count": 1,
                "total_likes": 10,
                "total_replies": 1,
                "total_retweets": 2,
                "top_post_url": None,
            },
        },
        "fetch_errors": {"PANW": "temporary scrape failure"},
    }

    messages = render_x_summary_markdown_v2(payload)

    assert messages
    assert "NAVE X digest" in messages[0]
    assert "Fallback" in messages[0]
    assert "MSFT" in "\n".join(messages)
    assert "PANW" in "\n".join(messages)
