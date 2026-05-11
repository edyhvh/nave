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
                    }
                ],
                "charts": {"strategy_ranking": "/tmp/ranking.html"},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app, ["options", "analyze", "--ticker", "MSFT", "--days-to-exp", "30"])

    assert result.exit_code == 0
    assert "Options Summary - MSFT" in result.stdout
    assert "Top Strategy Ranking" in result.stdout
    assert "Chart Artifacts" in result.stdout
    assert "Copyable JSON" in result.stdout
    assert any(tmp_path.glob("*.json"))


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
