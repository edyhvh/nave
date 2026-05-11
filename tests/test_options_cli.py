from __future__ import annotations

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_cli_registers_options_group() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "options" in result.stdout


def test_options_analyze_command_outputs_json(monkeypatch) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def run(self, ticker: str = "MSFT", days_to_exp: int = 30):
            return {
                "ticker": ticker,
                "underlying_analysis": {"price": 420.0},
                "recommendations": [],
                "charts": {},
            }

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)
    result = runner.invoke(
        app, ["options", "analyze", "--ticker", "MSFT", "--days-to-exp", "30"])

    assert result.exit_code == 0
    assert '"ticker": "MSFT"' in result.stdout
