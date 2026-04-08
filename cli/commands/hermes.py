"""Hermes integration command group for Nave CLI."""

from __future__ import annotations

import json

import typer

from core.exceptions import HermesIntegrationError
from hermes.integration import HermesNaveIntegration

hermes_app = typer.Typer(help="Hermes Agent integration commands")


@hermes_app.command("tools")
def list_tools(
    json_out: bool = typer.Option(True, "--json/--no-json", help="Print JSON metadata"),
) -> None:
    """List Hermes skill/tool registration metadata."""
    integration = HermesNaveIntegration()
    payload = integration.list_tools()
    if json_out:
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo("Hermes skill: nave_trading")
    for tool in payload["tools"]:
        typer.echo(f"- {tool['name']}: {tool['description']}")


@hermes_app.command("call")
def call_tool(
    tool: str = typer.Option(..., "--tool", help="Tool name (cot_report|cot_history|weekly_plan)"),
    args_json: str = typer.Option("{}", "--args-json", help="JSON object with tool arguments"),
) -> None:
    """Invoke a Hermes-registered tool and print a structured JSON result."""
    integration = HermesNaveIntegration()
    try:
        arguments = json.loads(args_json)
        if not isinstance(arguments, dict):
            raise typer.BadParameter("--args-json must decode to an object")
        payload = integration.dispatch_tool_call(tool, arguments)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON for --args-json: {exc}") from exc
    except HermesIntegrationError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(json.dumps(payload, indent=2))


@hermes_app.command("gateway-invoke")
def gateway_invoke(payload_json: str = typer.Argument(..., help="Gateway payload JSON")) -> None:
    """Invoke Hermes gateway payload contract directly."""
    integration = HermesNaveIntegration()
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON payload: {exc}") from exc

    try:
        result = integration.gateway_invoke(payload)
    except HermesIntegrationError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(json.dumps(result, indent=2))
