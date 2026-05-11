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

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30):
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

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30):
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

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30):
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

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30):
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

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30):
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

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30):
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

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30):
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

        def run(self, ticker: str = "MSFT", days_to_exp: int = 30):
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
