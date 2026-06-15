from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_cli_registers_options_group() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "options" in result.stdout


def test_options_analyze_command_outputs_json(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            return {
                "ticker": ticker,
                "underlying_analysis": {
                    "price": 420.0,
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "recommendations": [],
                "charts": {},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app, ["options", "analyze", "--ticker", "MSFT", "--days-to-exp", "30", "--json"])

    assert result.exit_code == 0
    assert result.stdout.strip().startswith("{")
    assert '"ticker": "MSFT"' in result.stdout
    assert "JSON report:" not in result.stdout
    assert '"charts": {}' in result.stdout
    report_files = list(tmp_path.glob("*.json"))
    assert report_files
    report_payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert "charts" in report_payload
    assert "artifacts" in report_payload


def test_options_analyze_command_defaults_to_sheet(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            return {
                "ticker": ticker,
                "underlying_analysis": {
                    "price": 420.0,
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "recommendations": [
                    {
                        "strategy": {"name": "covered_call"},
                        "metrics": {
                            "composite_score": 81.2,
                            "pop": 63.1,
                            "expected_value": 24.3,
                            "probability_of_touch": 41.0,
                        },
                        "tradeoff_comment": "Balanced income profile.",
                    },
                    {
                        "strategy": {"name": "iron_condor"},
                        "metrics": {
                            "composite_score": 74.2,
                            "pop": 59.1,
                            "expected_value": 11.3,
                            "probability_of_touch": 52.0,
                        },
                        "tradeoff_comment": "Neutral premium-selling setup.",
                    },
                    {
                        "strategy": {"name": "long_strangle"},
                        "metrics": {
                            "composite_score": 69.7,
                            "pop": 34.2,
                            "expected_value": 7.4,
                            "probability_of_touch": 47.0,
                        },
                        "tradeoff_comment": "Cheaper breakout structure.",
                    }
                ],
                "charts": {"strategy_ranking": "/tmp/ranking.html"},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app, ["options", "analyze", "--ticker", "MSFT", "--days-to-exp", "30"])

    assert result.exit_code == 0
    assert "Options Summary - MSFT" in result.stdout
    assert "Bullish Strategy Ranking" in result.stdout
    assert "Neutral Strategy Ranking" in result.stdout
    assert "Long Volatility Strategy Ranking" in result.stdout
    assert "Chart Artifacts" in result.stdout
    assert "Copyable JSON" in result.stdout
    assert any(tmp_path.glob("*.json"))


def test_options_analyze_plain_output_groups_strategies_by_bias(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            return {
                "ticker": ticker,
                "underlying_analysis": {
                    "price": 420.0,
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "recommendations": [
                    {
                        "strategy": {"name": "bull_put_credit_spread"},
                        "metrics": {
                            "composite_score": 71.0,
                            "pop": 65.0,
                            "expected_value": 9.0,
                            "probability_of_touch": 41.0,
                        },
                        "tradeoff_comment": "Defined-risk bullish credit spread.",
                    },
                    {
                        "strategy": {"name": "iron_condor"},
                        "metrics": {
                            "composite_score": 69.0,
                            "pop": 58.0,
                            "expected_value": -3.0,
                            "probability_of_touch": 63.0,
                        },
                        "tradeoff_comment": "Neutral premium-selling setup.",
                    },
                    {
                        "strategy": {"name": "long_straddle"},
                        "metrics": {
                            "composite_score": 62.0,
                            "pop": 31.0,
                            "expected_value": 6.0,
                            "probability_of_touch": 50.0,
                        },
                        "tradeoff_comment": "Long volatility ATM setup.",
                    },
                ],
                "charts": {},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app, ["options", "analyze", "--ticker", "MSFT", "--days-to-exp", "30", "--no-sheet"])

    assert result.exit_code == 0
    assert "Bullish strategies:" in result.stdout
    assert "Neutral strategies:" in result.stdout
    assert "Long Volatility strategies:" in result.stdout
    assert "bull_put_credit_spread" in result.stdout
    assert "iron_condor" in result.stdout
    assert "long_straddle" in result.stdout


def test_options_analyze_sheet_warns_when_top_strategy_has_negative_ev(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            return {
                "ticker": ticker,
                "underlying_analysis": {
                    "price": 420.0,
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "recommendations": [
                    {
                        "strategy": {"name": "iron_condor"},
                        "metrics": {
                            "composite_score": 67.5,
                            "pop": 68.2,
                            "expected_value": -12.5,
                            "probability_of_touch": 44.0,
                        },
                        "tradeoff_comment": "Premium collection with weak expectancy.",
                    }
                ],
                "charts": {"strategy_ranking": "/tmp/ranking.html"},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app, ["options", "analyze", "--ticker", "MSFT", "--days-to-exp", "30"])

    assert result.exit_code == 0
    assert "NEG EV -12.50" in result.stdout
    assert "Risk Warning" in result.stdout
    assert "negative modeled expected value" in result.stdout
    assert "-12.50" in result.stdout


def test_options_analyze_llm_prompt(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            return {
                "ticker": ticker,
                "underlying_analysis": {
                    "price": 420.0,
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "recommendations": [
                    {
                        "strategy": {"name": "covered_call"},
                        "metrics": {
                            "composite_score": 81.2,
                            "pop": 63.1,
                            "expected_value": 24.3,
                            "probability_of_touch": 41.0,
                        },
                        "tradeoff_comment": "Balanced income profile.",
                    }
                ],
                "charts": {"strategy_ranking": "/tmp/ranking.html"},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app,
        ["options", "analyze", "--ticker", "MSFT",
            "--days-to-exp", "30", "--llm-prompt"],
    )

    assert result.exit_code == 0
    assert "LLM Prompt (Copy/Paste)" in result.stdout
    assert "LLM Paths (Separate Block)" in result.stdout
    assert "Input JSON report path:" not in result.stdout
    report_files = list(tmp_path.glob("*.json"))
    assert report_files
    report_payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert "llm_prompt" in report_payload
    assert "llm_paths" in report_payload
    assert "JSON data (paths removed):" in report_payload["llm_prompt"]
    assert '"charts": {' in report_payload["llm_prompt"]
    assert "[path omitted]" in report_payload["llm_prompt"]
    assert '"json_report_path"' not in report_payload["llm_prompt"]


def test_options_analyze_llm_prompt_filters_low_quality_top_strategies(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            return {
                "ticker": ticker,
                "underlying_analysis": {
                    "price": 420.0,
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "recommendations": [
                    {
                        "strategy": {"name": "covered_call"},
                        "metrics": {
                            "composite_score": 74.0,
                            "pop": 61.2,
                            "expected_value": -5.0,
                            "probability_of_touch": 40.0,
                        },
                        "tradeoff_comment": "Negative EV but still well ranked.",
                    },
                    {
                        "strategy": {"name": "cash_secured_put"},
                        "metrics": {
                            "composite_score": 20.0,
                            "pop": 55.0,
                            "expected_value": 9.5,
                            "probability_of_touch": 35.0,
                        },
                        "tradeoff_comment": "Positive EV with a lower composite score.",
                    },
                    {
                        "strategy": {"name": "iron_condor"},
                        "metrics": {
                            "composite_score": 18.0,
                            "pop": 57.0,
                            "expected_value": -2.0,
                            "probability_of_touch": 37.0,
                        },
                        "tradeoff_comment": "Should be excluded from the prompt list.",
                    },
                ],
                "charts": {"strategy_ranking": "/tmp/ranking.html"},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app,
        ["options", "analyze", "--ticker", "MSFT",
            "--days-to-exp", "30", "--json", "--llm-prompt"],
    )

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    prompt = parsed["llm_prompt"]
    assert "Top strategies in report: covered_call, cash_secured_put" in prompt
    assert "iron_condor" not in prompt.split(
        "JSON data (paths removed):", maxsplit=1)[0]
    assert "Warn the user if the highest-ranked strategy has negative expected value." in prompt


def test_options_analyze_llm_prompt_references_structured_overlay(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            return {
                "ticker": ticker,
                "underlying_analysis": {
                    "price": 420.0,
                    "historical_volatility": {"hv_30": 0.24},
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "analysis_overlay": {
                    "executive_summary": ["IV is slightly rich to HV."],
                    "final_recommendations": {
                        "best_conservative_executable_setup": {"strategy_name": "bull_put_credit_spread"}
                    },
                },
                "recommendations": [
                    {
                        "strategy": {"name": "bull_put_credit_spread"},
                        "metrics": {
                            "composite_score": 64.0,
                            "pop": 65.0,
                            "expected_value": 8.0,
                            "probability_of_touch": 40.0,
                        },
                        "tradeoff_comment": "Defined-risk bullish credit spread.",
                    }
                ],
                "charts": {"strategy_ranking": "/tmp/ranking.html"},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app,
        ["options", "analyze", "--ticker", "MSFT",
            "--days-to-exp", "30", "--json", "--llm-prompt"],
    )

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    prompt = parsed["llm_prompt"]
    assert "Structured practical overlay sections: executive_summary, final_recommendations" in prompt
    assert "Use the analyzer's structured overlay as the preferred practical interpretation layer when it is present." in prompt
    assert "Distinguish clearly between the highest modeled setup, the best conservative executable setup, and the best aggressive setup." in prompt


def test_options_analyze_includes_llm_prompt_in_json_mode(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            return {
                "ticker": ticker,
                "underlying_analysis": {
                    "price": 420.0,
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "recommendations": [],
                "charts": {},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app,
        ["options", "analyze", "--ticker", "MSFT",
            "--days-to-exp", "30", "--json", "--llm-prompt"],
    )

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert "llm_prompt" in parsed
    assert "llm_paths" in parsed
    assert "charts" in parsed
    assert "Input JSON report path:" not in parsed["llm_prompt"]
    assert "JSON data (paths removed):" in parsed["llm_prompt"]
    assert '"json_report_path"' not in parsed["llm_prompt"]
    assert isinstance(parsed["llm_paths"].get("charts"), dict)
    assert "json_report_path" in parsed["llm_paths"]


def test_options_analyze_terminal_mode_orders_blocks(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            return {
                "ticker": ticker,
                "generated_at": "2026-05-11T00:00:00+00:00",
                "underlying_analysis": {
                    "price": 420.0,
                    "historical_volatility": {"hv_30": 0.24},
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"horizon_days": 30, "one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "recommendations": [
                    {
                        "strategy": {
                            "name": "bull_put_credit_spread",
                            "days_to_expiration": 30,
                            "legs": [
                                {
                                    "instrument_type": "option",
                                    "side": "sell",
                                    "quantity": 1,
                                    "premium": 2.5,
                                    "strike": 400.0,
                                    "option_type": "put",
                                },
                                {
                                    "instrument_type": "option",
                                    "side": "buy",
                                    "quantity": 1,
                                    "premium": 1.0,
                                    "strike": 390.0,
                                    "option_type": "put",
                                },
                            ],
                        },
                        "metrics": {
                            "composite_score": 71.0,
                            "pop": 65.0,
                            "expected_value": 9.0,
                            "probability_of_touch": 41.0,
                            "theta_per_day": 0.14,
                            "vega_exposure": 0.08,
                        },
                        "tradeoff_comment": "Defined-risk bullish credit spread.",
                    }
                ],
                "all_recommendations_ranked": [
                    {
                        "strategy": {"name": "bull_put_credit_spread"},
                        "metrics": {"composite_score": 71.0},
                    },
                    {
                        "strategy": {"name": "iron_condor"},
                        "metrics": {"composite_score": 63.0},
                    },
                ],
                "analysis_overlay": {"warnings": ["Model warning example"]},
                "charts": {"strategy_ranking": "/tmp/ranking.html"},
            }

    def _fake_terminal_renderer(report_json: dict, console):
        _ = report_json
        console.print("TERMINAL_CHART_RENDERED")

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    monkeypatch.setattr(options_cmd, "render_terminal_charts",
                        _fake_terminal_renderer)

    result = runner.invoke(
        app,
        [
            "options",
            "analyze",
            "--ticker",
            "MSFT",
            "--days-to-exp",
            "30",
            "--terminal",
            "--llm-prompt",
        ],
    )

    assert result.exit_code == 0
    output = result.stdout
    prompt_idx = output.index("=== Prompt and Data ===")
    graph_idx = output.index("=== Graphs ===")
    summary_idx = output.index("=== Summary ===")
    assert prompt_idx < graph_idx < summary_idx
    assert "TERMINAL_CHART_RENDERED" in output
    assert "Options Summary - MSFT" in output
    assert "Bullish Strategy Ranking" in output
    assert "Risk Warning" in output


def test_options_analyze_ascii_alias_matches_terminal_mode(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            _ = days_to_exp
            return {
                "ticker": ticker,
                "generated_at": "2026-05-11T00:00:00+00:00",
                "underlying_analysis": {
                    "price": 420.0,
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"horizon_days": 30, "one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "recommendations": [],
                "charts": {},
            }

    call_count = {"value": 0}

    def _fake_terminal_renderer(report_json: dict, console):
        _ = report_json
        call_count["value"] += 1
        console.print("ASCII_MODE_RENDER")

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    monkeypatch.setattr(options_cmd, "render_terminal_charts",
                        _fake_terminal_renderer)

    result = runner.invoke(
        app,
        [
            "options",
            "analyze",
            "--ticker",
            "MSFT",
            "--days-to-exp",
            "30",
            "--ascii",
        ],
    )

    assert result.exit_code == 0
    assert call_count["value"] == 1
    assert "=== Graphs ===" in result.stdout
    assert "ASCII_MODE_RENDER" in result.stdout


def test_options_opportunities_command_outputs_json(monkeypatch) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def scan_crypto_opportunities(self, **kwargs):
            assert kwargs["coins"] == ["BTC", "ETH"]
            return {
                "strategy": "options_momentum_bridge_v1",
                "summary": {
                    "coins_requested": 2,
                    "coins_supported": 2,
                    "momentum_allowed": 1,
                    "options_ready": 1,
                },
                "opportunities": {
                    "BTC": {
                        "status": "ready",
                        "top_strategy": "bull_put_credit_spread",
                        "top_metrics": {"expected_value": 11.0},
                        "momentum": {"confidence_score": 84},
                    },
                    "ETH": {
                        "status": "filtered_by_momentum",
                        "reason": "No momentum-qualified setup met the current gate.",
                    },
                },
                "ranked": [
                    {
                        "coin": "BTC",
                        "strategy_name": "bull_put_credit_spread",
                        "strategy_score": 80.0,
                        "expected_value": 11.0,
                    }
                ],
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)

    result = runner.invoke(
        app,
        [
            "options",
            "opportunities",
            "--coins",
            "BTC,ETH",
            "--json",
        ],
    )

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["strategy"] == "options_momentum_bridge_v1"
    assert parsed["summary"]["options_ready"] == 1
    assert parsed["opportunities"]["BTC"]["status"] == "ready"
    assert parsed["opportunities"]["ETH"]["status"] == "filtered_by_momentum"


def test_options_opportunities_command_sheet_render(monkeypatch) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def scan_crypto_opportunities(self, **kwargs):
            _ = kwargs
            return {
                "summary": {
                    "coins_requested": 2,
                    "coins_supported": 2,
                    "momentum_allowed": 1,
                    "options_ready": 1,
                },
                "momentum": {
                    "timeframes": {"bias": "1d", "setup": "4h", "trigger": "1h"}
                },
                "opportunities": {
                    "BTC": {
                        "status": "ready",
                        "top_strategy": "bull_put_credit_spread",
                        "top_metrics": {"expected_value": 11.0},
                        "momentum": {"confidence_score": 84},
                    },
                    "ETH": {
                        "status": "options_unavailable",
                        "error": "No options expirations available",
                        "momentum": {"confidence_score": 79},
                    },
                },
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app, ["options", "opportunities", "--coins", "BTC,ETH", "--sheet"])

    assert result.exit_code == 0
    assert "Options Opportunities Summary" in result.stdout
    assert "BTC/ETH Opportunity Details" in result.stdout
    assert "BTC" in result.stdout
    assert "ETH" in result.stdout
    assert "ready" in result.stdout


def test_options_opportunities_command_defaults_to_plain_output(monkeypatch) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def scan_crypto_opportunities(self, **kwargs):
            _ = kwargs
            return {
                "summary": {
                    "coins_requested": 2,
                    "momentum_allowed": 1,
                    "options_ready": 1,
                },
                "opportunities": {
                    "BTC": {
                        "status": "ready",
                        "top_strategy": "bull_put_credit_spread",
                    },
                    "ETH": {
                        "status": "filtered_by_momentum",
                        "top_strategy": None,
                    },
                },
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app, ["options", "opportunities", "--coins", "BTC,ETH"])

    assert result.exit_code == 0
    assert "Options opportunities" in result.stdout
    assert "- coins_requested=2" in result.stdout
    assert "- BTC: status=ready top_strategy=bull_put_credit_spread" in result.stdout


def test_options_opportunities_sheet_takes_precedence_over_json(monkeypatch) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def scan_crypto_opportunities(self, **kwargs):
            _ = kwargs
            return {
                "summary": {
                    "coins_requested": 2,
                    "coins_supported": 2,
                    "momentum_allowed": 1,
                    "options_ready": 1,
                },
                "momentum": {
                    "timeframes": {"bias": "1d", "setup": "4h", "trigger": "1h"}
                },
                "opportunities": {
                    "BTC": {
                        "status": "ready",
                        "top_strategy": "bull_put_credit_spread",
                        "top_metrics": {"expected_value": 11.0},
                        "momentum": {"confidence_score": 84},
                    }
                },
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app,
        ["options", "opportunities", "--coins", "BTC,ETH", "--json", "--sheet"],
    )

    assert result.exit_code == 0
    assert "Options Opportunities Summary" in result.stdout
    assert not result.stdout.strip().startswith("{")


def test_options_analyze_accepts_positional_ticker_and_source(monkeypatch) -> None:
    from cli.commands import options as options_cmd

    captured: dict[str, str] = {}

    class _DummyAnalyzer:
        def __init__(self, fetcher_source: str = "yfinance") -> None:
            captured["source"] = fetcher_source
            self.config = SimpleNamespace(reports_dir=Path("."))

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            _ = days_to_exp
            return {
                "ticker": ticker,
                "underlying_analysis": {
                    "price": 420.0,
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "recommendations": [],
                "charts": {},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)

    result = runner.invoke(
        app,
        ["options", "analyze", "BTC", "--source",
            "deribit", "--json", "--no-save-json"],
    )

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["ticker"] == "BTC"
    assert captured["source"] == "deribit"


def test_options_analyze_forwards_manual_bull_put_strategy(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    captured: dict[str, object] = {}

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, **kwargs):
            captured.update(kwargs)
            return {
                "ticker": kwargs["ticker"],
                "underlying_analysis": {
                    "price": 410.0,
                    "manual_strategy": {
                        "strategy": "bull_put",
                        "expiration": kwargs["expiration"],
                        "net_credit": 160.0,
                        "max_loss": 340.0,
                        "breakeven": 393.4,
                    },
                    "implied_volatility": {"iv_mean": 0.25, "iv_rank": 60.0},
                    "expected_move": {"one_std_move": 11.0},
                    "options_market_snapshot": {"contracts": 120.0, "put_call_oi_ratio": 0.95},
                },
                "analysis_overlay": {
                    "trade_decision": {
                        "status": "trade_candidate",
                        "reason": "manual",
                    },
                    "warnings": [],
                },
                "recommendations": [
                    {
                        "strategy": {"name": "bull_put_credit_spread"},
                        "metrics": {
                            "composite_score": 65.0,
                            "pop": 62.0,
                            "expected_value": 8.0,
                            "probability_of_touch": 42.0,
                        },
                        "tradeoff_comment": "Manual bull put.",
                    }
                ],
                "charts": {},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app,
        [
            "options",
            "analyze",
            "--ticker",
            "MSFT",
            "--strategy",
            "bull-put",
            "--short-put",
            "395",
            "--long-put",
            "390",
            "--short-premium",
            "8.50",
            "--long-premium",
            "6.90",
            "--expiration",
            "2026-06-18",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert captured["strategy"] == "bull-put"
    assert captured["short_put"] == 395.0
    assert captured["long_put"] == 390.0
    assert captured["short_premium"] == 8.5
    assert captured["long_premium"] == 6.9
    parsed = json.loads(result.stdout)
    assert parsed["underlying_analysis"]["manual_strategy"]["net_credit"] == 160.0


def test_options_analyze_sp500_scan_returns_top_trade_candidates(monkeypatch, tmp_path: Path) -> None:
    from cli.commands import options as options_cmd

    monkeypatch.setattr(options_cmd, "SP500_TOP_100_TICKERS", ("AAA", "BBB", "CCC"))

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            _ = days_to_exp
            candidates = {
                "AAA": {
                    "status": "trade_candidate",
                    "strategy": "bull_put_credit_spread",
                    "score": 72.0,
                    "ev": 14.0,
                    "touch": 41.0,
                },
                "BBB": {
                    "status": "no_trade",
                    "strategy": "bull_call_debit_spread",
                    "score": 20.0,
                    "ev": -2.57,
                    "touch": 87.6,
                },
                "CCC": {
                    "status": "trade_candidate",
                    "strategy": "covered_call",
                    "score": 81.0,
                    "ev": 20.0,
                    "touch": 38.0,
                },
            }
            item = candidates[ticker]
            executable = (
                {
                    "strategy_name": item["strategy"],
                    "metrics": {
                        "composite_score": item["score"],
                        "expected_value": item["ev"],
                        "pop": 63.0,
                        "probability_of_touch": item["touch"],
                        "theta_per_day": 0.2,
                        "max_loss": 700.0,
                    },
                }
                if item["status"] == "trade_candidate"
                else None
            )
            return {
                "ticker": ticker,
                "analysis_overlay": {
                    "trade_decision": {
                        "status": item["status"],
                        "reason": item["status"],
                    },
                    "final_recommendations": {
                        "best_overall_executable_setup": executable,
                    },
                    "warnings": [],
                },
                "recommendations": [
                    {
                        "strategy": {"name": item["strategy"]},
                        "metrics": {
                            "composite_score": item["score"],
                            "expected_value": item["ev"],
                            "pop": 55.0,
                            "probability_of_touch": item["touch"],
                        },
                    }
                ],
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app,
        [
            "options",
            "analyze",
            "--sp500-scan",
            "--sp500-limit",
            "3",
            "--top-trades",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["strategy"] == "options_equity_universe_scan_v1"
    assert parsed["summary"]["tickers_scanned"] == 3
    assert parsed["summary"]["trade_candidates"] == 2
    assert [item["ticker"] for item in parsed["ranked"]] == ["CCC", "AAA"]
    assert parsed["results"]["BBB"]["status"] == "no_trade"
    assert parsed["results"]["BBB"]["executable_strategy"] is None


def test_options_analyze_sp500_scan_marks_low_coverage_inconclusive(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from cli.commands import options as options_cmd
    from options.exceptions import OptionsDataError

    tickers = tuple(f"T{i:02d}" for i in range(40))
    monkeypatch.setattr(options_cmd, "SP500_TOP_100_TICKERS", tickers)

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            _ = days_to_exp
            _ = kwargs
            if ticker != "T00":
                raise OptionsDataError(
                    f"No contracts passed liquidity filters for {ticker}"
                )
            return {
                "ticker": ticker,
                "analysis_overlay": {
                    "trade_decision": {"status": "no_trade", "reason": "no setup"},
                    "final_recommendations": {
                        "best_overall_executable_setup": None,
                    },
                    "warnings": [
                        "No conservative income setup passed the executable filter."
                    ],
                },
                "recommendations": [
                    {
                        "strategy": {"name": "bear_call_credit_spread"},
                        "metrics": {
                            "composite_score": 55.0,
                            "expected_value": 10.0,
                            "pop": 100.0,
                            "probability_of_touch": 0.0,
                        },
                    }
                ],
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app,
        [
            "options",
            "analyze",
            "--sp500-scan",
            "--sp500-limit",
            "40",
            "--json",
        ],
    )

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["summary"]["tickers_requested"] == 40
    assert parsed["summary"]["tickers_scanned"] == 1
    assert parsed["summary"]["trade_candidates"] == 0
    assert parsed["summary"]["scan_status"] == "inconclusive"
    assert parsed["summary"]["coverage_ratio"] == 0.025
    assert parsed["summary"]["min_required_scanned"] == 24
    assert parsed["warnings"]
    assert "rerun during regular market hours" in parsed["warnings"][0]


def test_options_analyze_sp500_scan_sheet_keeps_single_ticker_mode_additive(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from cli.commands import options as options_cmd

    monkeypatch.setattr(options_cmd, "SP500_TOP_100_TICKERS", ("AAA",))

    class _DummyAnalyzer:
        def __init__(self) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30, **kwargs):
            _ = days_to_exp
            return {
                "ticker": ticker,
                "analysis_overlay": {
                    "trade_decision": {"status": "no_trade", "reason": "no setup"},
                    "final_recommendations": {
                        "best_overall_executable_setup": None,
                    },
                    "warnings": ["No trade"],
                },
                "recommendations": [],
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app,
        ["options", "analyze", "--sp500-scan", "--sp500-limit", "1"],
    )

    assert result.exit_code == 0
    assert "Options Equity Universe Scan" in result.stdout
    assert "Top Executable Trades" in result.stdout
    assert "Trade Candidates" in result.stdout


def test_options_daily_json_keeps_stdout_parseable_when_refreshing_congress(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from cli.commands import congress as congress_cmd
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self, fetcher_source: str = "yfinance") -> None:
            _ = fetcher_source
            self.config = SimpleNamespace(reports_dir=tmp_path)

    def _fake_congress_scan(*, persist: bool, save_report: bool) -> dict:
        assert persist is True
        assert save_report is True
        return {"new_trades": [{"symbol": "WFC"}]}

    def _fake_universe_scan(**kwargs) -> dict:
        assert kwargs["days_to_exp"] == 30
        return {
            "strategy": "options_equity_universe_scan_v1",
            "days_to_exp": 30,
            "summary": {
                "tickers_requested": 10,
                "tickers_scanned": 10,
                "trade_candidates": 0,
                "errors": 0,
                "top_trades_returned": 0,
                "workers": 1,
            },
            "ranked": [],
            "results": {},
        }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    monkeypatch.setattr(congress_cmd, "_run_congress_scan", _fake_congress_scan)
    monkeypatch.setattr(options_cmd, "_scan_equity_options_universe", _fake_universe_scan)

    result = runner.invoke(
        app,
        [
            "options",
            "daily",
            "--limit",
            "10",
            "--top",
            "1",
            "--scan-workers",
            "1",
            "--json",
            "--no-save-json",
        ],
    )

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["hidden_gems"]["gems"] == []
    assert parsed["scan"]["summary"]["tickers_scanned"] == 10
    assert "Refreshing congressional disclosures" not in result.stdout
    assert "Congress scan: 1 new filing(s)" not in result.stdout


def test_options_opportunities_forwards_source(monkeypatch) -> None:
    from cli.commands import options as options_cmd

    captured: dict[str, str] = {}

    class _DummyAnalyzer:
        def __init__(self, fetcher_source: str = "yfinance") -> None:
            captured["source"] = fetcher_source

        def scan_crypto_opportunities(self, **kwargs):
            _ = kwargs
            return {
                "strategy": "options_momentum_bridge_v1",
                "summary": {
                    "coins_requested": 2,
                    "coins_supported": 2,
                    "momentum_allowed": 1,
                    "options_ready": 1,
                },
                "opportunities": {},
                "ranked": [],
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app,
        ["options", "opportunities", "--coins",
            "BTC,ETH", "--json", "--source", "deribit"],
    )

    assert result.exit_code == 0
    assert captured["source"] == "deribit"
