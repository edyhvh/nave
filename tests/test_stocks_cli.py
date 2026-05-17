from __future__ import annotations

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_stocks_ism_report_telegram_preview(monkeypatch) -> None:
    monkeypatch.setattr(
        "cli.commands.stocks.build_ism_industry_report",
        lambda **kwargs: {
            "kind": kwargs.get("kind", "manufacturing"),
            "report_month": "April 2026",
            "criteria": {"top_n": 5, "min_confidence": 0.3},
            "candidates": {
                "longs": [
                    {
                        "symbol": "ETN",
                        "side": "long",
                        "sector": "Industrials",
                        "score": 0.8,
                        "confidence": 0.7,
                        "driver_industry": "Electrical Equipment",
                    }
                ],
                "shorts": [],
            },
        },
    )

    result = runner.invoke(app, ["stocks", "ism-report", "--telegram-markdown-v2"])

    assert result.exit_code == 0
    assert "NAVE ISM MANUFACTURING" in result.stdout
    assert "ETN" in result.stdout


def test_stocks_x_analyze_telegram_preview(monkeypatch) -> None:
    monkeypatch.setattr(
        "cli.commands.stocks.analyze_tickers",
        lambda *args, **kwargs: {
            "tickers": ["MSFT"],
            "days": 7,
            "total_posts": 3,
            "summary_stats": {
                "MSFT": {
                    "post_count": 3,
                    "total_likes": 12,
                    "total_replies": 2,
                    "total_retweets": 1,
                    "top_post_url": "https://x.test/msft",
                }
            },
            "fetch_errors": {},
            "analysis_prompt": {"system": "sys", "user": "usr"},
        },
    )

    result = runner.invoke(
        app,
        ["stocks", "x-analyze", "--tickers", "MSFT", "--telegram-markdown-v2"],
    )

    assert result.exit_code == 0
    assert "NAVE X digest" in result.stdout
    assert "MSFT" in result.stdout
