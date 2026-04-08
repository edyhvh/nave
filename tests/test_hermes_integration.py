"""Tests for Hermes integration contracts and CLI registration."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cli.main import app
from core.exceptions import HermesIntegrationError
from hermes.integration import HermesNaveIntegration

runner = CliRunner()


def test_list_tools_contains_required_toolset() -> None:
    integration = HermesNaveIntegration()
    payload = integration.list_tools()

    assert payload["skill"]["name"] == "nave_trading"
    tool_names = {tool["name"] for tool in payload["tools"]}
    assert {"cot_report", "cot_history", "weekly_plan"}.issubset(tool_names)


def test_gateway_invoke_requires_tool_name() -> None:
    integration = HermesNaveIntegration()

    with pytest.raises(HermesIntegrationError):
        integration.gateway_invoke({"arguments": {}})


def test_dispatch_tool_call_uses_registered_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    integration = HermesNaveIntegration()

    def fake_report(**kwargs):
        return {"ok": True, "args": kwargs}

    monkeypatch.setattr(integration, "cot_report", fake_report)
    result = integration.dispatch_tool_call("cot_report", {"coins": "BTC ETH"})

    assert result["ok"] is True
    assert result["tool"] == "cot_report"
    assert result["result"]["args"]["coins"] == "BTC ETH"


def test_cli_registers_hermes_group() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "hermes" in result.stdout
