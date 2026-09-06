"""Inspection commands for structured NAVE research artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from cli.professional_typer import ProfessionalTyper
from research.core.contracts import ResearchResult
from research.core.store import ResearchStore
from research.orchestration import present_result

research_app = ProfessionalTyper(help="Inspect read-only structured research results.")


@research_app.command("run")
def run_quant(
    workflow: str = typer.Option(..., "--workflow", help="cava, watch, portfolio, ism, disclosures, crypto, memecoin, or shorts"),
    state_dir: Path = typer.Option(..., "--state-dir"),
    channel_id: str = typer.Option(..., "--channel-id"),
    input_file: Path | None = typer.Option(None, "--input-file", exists=True, readable=True),
) -> None:
    """Execute a bounded NAVE CLI workflow and emit only its Discord report; never sends."""
    from research.quant_runner import run
    try:
        view = run(workflow, state_dir=state_dir, channel_id=channel_id, input_file=input_file)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(view["discord_text"])


@research_app.command("status")
def status(
    workflow: str | None = typer.Option(None, "--workflow", help="Workflow name to inspect."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Show the latest stored result or the available result index."""
    store = ResearchStore()
    if workflow:
        result = store.load_result(workflow)
        payload = result.to_dict() if result else {
            "envelope_type": "research_result_index",
            "workflow": workflow,
            "status": "DATA_UNAVAILABLE",
            "results": [],
        }
    else:
        payload = {"envelope_type": "research_result_index", "results": store.list_results()}
    if json_out:
        typer.echo(json.dumps(payload, indent=2, allow_nan=False))
        return
    if workflow and payload.get("status"):
        typer.echo(f"{payload.get('workflow')}: {payload.get('status')}")
        return
    typer.echo(f"stored research results: {len(payload['results'])}")
    for item in payload["results"]:
        typer.echo(f"- {item.get('workflow', '?')}: {item.get('status', '?')}")


@research_app.command("report")
def report(
    json_file: Path = typer.Option(..., "--json-file", exists=True, readable=True),
    markdown: bool = typer.Option(False, "--markdown", help="Render Markdown instead of JSON."),
) -> None:
    """Validate and render a saved structured result."""
    result = ResearchResult.from_dict(json.loads(json_file.read_text(encoding="utf-8")))
    typer.echo(result.to_markdown() if markdown else result.to_json())


@research_app.command("present")
def present(
    json_file: Path = typer.Option(..., "--json-file", exists=True, readable=True),
    channel_id: str | None = typer.Option(None, "--channel-id", help="Explicit parent Discord channel; never inferred from origin."),
    origin_file: Path | None = typer.Option(None, "--origin-file", exists=True, readable=True, help="Explicit interactive Discord origin JSON; omitted for scheduled reports."),
    discord: bool = typer.Option(False, "--discord", help="Emit only the Spanish report for Hermes' chunking Discord adapter."),
) -> None:
    """Render the concise evidence-aware view intended for Quant delivery."""
    result = ResearchResult.from_dict(json.loads(json_file.read_text(encoding="utf-8")))
    view = present_result(result, channel_id=channel_id, origin=json.loads(origin_file.read_text()) if origin_file else None)
    typer.echo(view["discord_text"] if discord else json.dumps(view, indent=2, allow_nan=False))
