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
        },
    )

    result = runner.invoke(app, ["stocks", "ism-report", "--telegram-markdown-v2"])

    assert result.exit_code == 0
    assert "NAVE ISM MANUFACTURING" in result.stdout
    assert "ETN" in result.stdout
    assert "GIS" in result.stdout
    assert "Ondo\\-shortable shorts" in result.stdout


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


def test_stocks_screen_shorts_rejects_invalid_mode() -> None:
    result = runner.invoke(app, ["stocks", "screen-shorts", "--mode", "service"])

    assert result.exit_code != 0
    assert "--mode must be manufacturing or services" in result.output


def test_stocks_ism_short_backtest_passes_window_options(monkeypatch) -> None:
    captured = {}

    class _FakeBacktester:
        def evaluate(self, **kwargs):
            captured.update(kwargs)
            return {
                "summary": {
                    "trade_count": 0,
                    "win_rate": 0.0,
                    "avg_return_pct": 0.0,
                },
                "lookback": {
                    "from_month": kwargs.get("from_month"),
                    "to_month": kwargs.get("to_month"),
                    "latest_months": kwargs.get("latest_months"),
                },
                "snapshots_used": [],
                "by_kind": {},
            }

    monkeypatch.setattr("cli.commands.stocks.ISMShortBacktester", _FakeBacktester)

    result = runner.invoke(
        app,
        [
            "stocks",
            "ism-short-backtest",
            "--latest-months",
            "4",
            "--min-short-score",
            "0.05",
            "--research-mode",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert captured["latest_months"] == 4
    assert captured["min_short_score"] == 0.05
    assert captured["research_mode"] is True


def test_stocks_ism_short_backtest_all_disables_latest_window(monkeypatch) -> None:
    captured = {}

    class _FakeBacktester:
        def evaluate(self, **kwargs):
            captured.update(kwargs)
            return {
                "summary": {
                    "trade_count": 0,
                    "win_rate": 0.0,
                    "avg_return_pct": 0.0,
                },
                "lookback": {
                    "from_month": kwargs.get("from_month"),
                    "to_month": kwargs.get("to_month"),
                    "latest_months": kwargs.get("latest_months"),
                },
                "snapshots_used": [],
                "by_kind": {},
            }

    monkeypatch.setattr("cli.commands.stocks.ISMShortBacktester", _FakeBacktester)

    result = runner.invoke(app, ["stocks", "ism-short-backtest", "--all", "--json"])

    assert result.exit_code == 0
    assert captured["latest_months"] is None
