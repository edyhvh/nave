import json

from typer.testing import CliRunner

from cli.main import app
from research.core.contracts import ResearchResult
from cli.commands.portfolio import _load_watches
from research.portfolio import PortfolioState


def test_research_help_is_registered():
    result = CliRunner().invoke(app, ["research", "--help"])
    assert result.exit_code == 0
    assert "status" in result.stdout
    assert "report" in result.stdout


def test_research_report_renders_json_and_markdown(tmp_path):
    fixture = {
        "schema_version": 1,
        "workflow": "fixture.scan",
        "status": "NO_SETUP",
        "metadata": {
            "strategy_name": "fixture",
            "strategy_version": "1",
            "run_id": "run-1",
            "decision_time": "2026-09-04T12:00:00+00:00",
            "started_at": "2026-09-04T11:59:00+00:00",
            "completed_at": "2026-09-04T12:00:00+00:00",
            "input_available_at": "2026-09-04T11:58:00+00:00",
        },
        "generated_at": "2026-09-04T12:00:00+00:00",
        "payload": {"scanned": 1},
        "evidence": [],
        "warnings": [],
        "safety_boundary": "READ_ONLY_RESEARCH_ONLY_HUMAN_GATED",
    }
    path = tmp_path / "result.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    json_result = CliRunner().invoke(app, ["research", "report", "--json-file", str(path)])
    assert json_result.exit_code == 0
    assert json.loads(json_result.stdout)["status"] == "NO_SETUP"
    markdown_result = CliRunner().invoke(
        app, ["research", "report", "--json-file", str(path), "--markdown"]
    )
    assert markdown_result.exit_code == 0
    assert "# fixture.scan" in markdown_result.stdout


def test_missing_status_is_explicit_index_envelope(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv('NAVE_RESEARCH_STATE_DIR', str(tmp_path))
    result = CliRunner().invoke(app, ['research', 'status', '--workflow', 'absent', '--json'])
    assert result.exit_code == 0
    value = json.loads(result.stdout)
    assert value['envelope_type'] == 'research_result_index'
    with pytest.raises(ValueError):
        ResearchResult.from_dict(value)
def test_portfolio_watch_without_file_uses_only_user_state(tmp_path, monkeypatch):
    empty_watch_state = tmp_path / "empty-watches.json"
    empty_watch_state.write_text(json.dumps({"watches": []}), encoding="utf-8")
    monkeypatch.setenv("NAVE_QUANT_WATCH_STATE_FILE", str(empty_watch_state))
    state = PortfolioState(watchlist=({"ticker": "SPCX", "condition": "BELOW", "threshold": 120},))
    assert _load_watches(None, state) == [
        {"ticker": "SPCX", "condition": "BELOW", "threshold": 120}
    ]
    assert _load_watches(None, PortfolioState()) == []


def test_portfolio_watch_accepts_explicit_private_state_file(tmp_path):
    state_file = tmp_path / "portfolio.json"
    state_file.write_text(
        json.dumps({"positions": [], "watchlist": [{"ticker": "SPCX", "condition": "BELOW", "threshold": 120}]}),
        encoding="utf-8",
    )
    prices_file = tmp_path / "prices.json"
    from datetime import UTC, datetime
    prices_file.write_text(json.dumps({"prices": {"SPCX": 119.0}, "observed_at": {"SPCX": datetime.now(UTC).isoformat()}}), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "portfolio",
            "watch",
            "--portfolio-file",
            str(state_file),
            "--prices-file",
            str(prices_file),
            "--state-dir",
            str(tmp_path / "research-state"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["payload"]["events"][0]["ticker"] == "SPCX"
    assert payload["payload"]["watchlist_source"] == str(state_file)
    assert payload["payload"]["watchlist_source_kind"] == "user_local_portfolio_state"
