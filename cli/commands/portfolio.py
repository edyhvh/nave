"""NAVE-owned human-gated portfolio research commands."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import typer

from cli.professional_typer import ProfessionalTyper
from research.core.store import ResearchStore
from research.portfolio_providers import PortfolioContextProvider, load_current_ism_inputs
from research.portfolio import (
    PortfolioState,
    PortfolioWorkflow,
    check_watch,
    default_portfolio_state_path,
    ism_rank,
    load_portfolio_state,
    portfolio_candidates,
    review_positions,
)
from research.quant_state import load_quant_watch_state

portfolio_app = ProfessionalTyper(help="Human-gated read-only portfolio research.")


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter(f"{path} must contain a JSON object")
    return payload


def _load_watches(path: Path | None, state: PortfolioState) -> list[dict]:
    watches, _metadata = _load_watch_input(path, state)
    return watches


def _load_watch_input(
    path: Path | None,
    state: PortfolioState,
    *,
    state_source: Path | None = None,
) -> tuple[list[dict], dict[str, object]]:
    if path is not None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        watches = raw.get("watches", raw.get("stocks", raw)) if isinstance(raw, dict) else raw
        if not isinstance(watches, list):
            raise typer.BadParameter(f"{path} must contain a watch list")
        return [dict(item) for item in watches if isinstance(item, dict)], {
            "source": str(path),
            "source_kind": "explicit_file",
            "warnings": (),
        }
    if state.watchlist:
        return [dict(item) for item in state.watchlist], {
            "source": str(state_source or default_portfolio_state_path()),
            "source_kind": "user_local_portfolio_state",
            "warnings": (),
        }
    try:
        quant_state = load_quant_watch_state()
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if quant_state and quant_state.deterministic_watches:
        return [dict(item) for item in quant_state.deterministic_watches], {
            "source": str(quant_state.source_path),
            "source_kind": "user_local_quant_watch_store",
            "warnings": quant_state.warnings,
            "unparsed_responsibilities": list(quant_state.unparsed_responsibilities),
        }
    return [], {
        "source": str(default_portfolio_state_path()),
        "source_kind": "user_local_portfolio_state",
        "warnings": quant_state.warnings if quant_state else (),
        "unparsed_responsibilities": list(quant_state.unparsed_responsibilities) if quant_state else [],
    }


def _emit(result, *, json_out: bool, markdown: bool) -> None:
    if markdown:
        typer.echo(result.to_markdown())
    elif json_out:
        typer.echo(result.to_json())
    else:
        typer.echo(f"{result.workflow}: {result.status.value}")
        if result.warnings:
            typer.echo("Warnings: " + "; ".join(result.warnings))


@portfolio_app.command("review")
def review(
    refresh_ledger: bool = typer.Option(False, "--refresh-ledger", help="Refresh the private wallet ledger before reviewing; never submits orders."),
    evidence_file: Path | None = typer.Option(None, "--evidence-file", exists=True, readable=True),
    portfolio_file: Path | None = typer.Option(None, "--portfolio-file", exists=True, readable=True),
    state_dir: Path | None = typer.Option(None, "--state-dir"),
    json_out: bool = typer.Option(False, "--json"),
    markdown: bool = typer.Option(False, "--markdown"),
) -> None:
    """Review current positions from user-local state."""
    if refresh_ledger:
        from trading.stocks.portfolio_ledger import refresh

        ledger_path = portfolio_file or default_portfolio_state_path()
        try:
            refresh(state_path=ledger_path, audit_path=ledger_path.with_name("ledger_audit.json"))
        except Exception as exc:
            raise typer.BadParameter("ledger refresh failed; review was not produced") from exc
    state = load_portfolio_state(portfolio_file)
    if evidence_file:
        evidence = _load_json(evidence_file)
    else:
        store = ResearchStore(state_dir)
        tickers = [position.ticker for position in state.positions]
        evidence = PortfolioContextProvider().build_review_context(
            tickers,
            macro_context=store.load_context("cava"),
        )
    result = review_positions(state, evidence, now=None)
    _emit(PortfolioWorkflow(store=ResearchStore(state_dir)).save(result), json_out=json_out, markdown=markdown)


@portfolio_app.command("candidates")
def candidates(
    ism_file: Path | None = typer.Option(None, "--ism-file", exists=True, readable=True),
    portfolio_file: Path | None = typer.Option(None, "--portfolio-file", exists=True, readable=True),
    state_dir: Path | None = typer.Option(None, "--state-dir"),
    json_out: bool = typer.Option(False, "--json"),
    markdown: bool = typer.Option(False, "--markdown"),
) -> None:
    """Build provenance-preserving candidates from both ISM reports."""
    payload = _load_json(ism_file) if ism_file else load_current_ism_inputs()
    state = load_portfolio_state(portfolio_file)
    watches, _ = _load_watch_input(None, state, state_source=portfolio_file)
    state = replace(state, watchlist=tuple(watches))
    result = portfolio_candidates(
        payload.get("manufacturing") or {},
        payload.get("services") or {},
        state=state,
    )
    _emit(PortfolioWorkflow(store=ResearchStore(state_dir)).save(result), json_out=json_out, markdown=markdown)


@portfolio_app.command("ism")
def ism(
    ism_file: Path | None = typer.Option(None, "--ism-file", exists=True, readable=True),
    portfolio_file: Path | None = typer.Option(None, "--portfolio-file", exists=True, readable=True),
    state_dir: Path | None = typer.Option(None, "--state-dir"),
    json_out: bool = typer.Option(False, "--json"),
    markdown: bool = typer.Option(False, "--markdown"),
) -> None:
    """Rank the actual Manufacturing and Services ISM industry/company mapping."""
    payload = _load_json(ism_file) if ism_file else load_current_ism_inputs()
    state = load_portfolio_state(portfolio_file)
    watches, _ = _load_watch_input(None, state, state_source=portfolio_file)
    result = ism_rank(
        payload.get("manufacturing") or {},
        payload.get("services") or {},
        state=replace(state, watchlist=tuple(watches)),
    )
    _emit(PortfolioWorkflow(store=ResearchStore(state_dir)).save(result), json_out=json_out, markdown=markdown)


@portfolio_app.command("watch")
def watch(
    watch_file: Path | None = typer.Option(None, "--watch-file", exists=True, readable=True),
    portfolio_file: Path | None = typer.Option(None, "--portfolio-file", exists=True, readable=True),
    prices_file: Path | None = typer.Option(None, "--prices-file", exists=True, readable=True),
    state_dir: Path | None = typer.Option(None, "--state-dir"),
    json_out: bool = typer.Option(False, "--json"),
    markdown: bool = typer.Option(False, "--markdown"),
) -> None:
    """Run a cheap deterministic price threshold check on explicit/user-local state."""
    store = ResearchStore(state_dir)
    state = load_portfolio_state(portfolio_file)
    watches, watch_metadata = _load_watch_input(watch_file, state, state_source=portfolio_file)
    previous = store.load_context("portfolio_watch_prices") or {}
    if prices_file:
        raw_prices = _load_json(prices_file)
        prices = raw_prices.get("prices", raw_prices)
        price_timestamps = raw_prices.get("observed_at", {})
    else:
        context = PortfolioContextProvider().build_review_context(
            [str(item.get("ticker") or "") for item in watches],
            macro_context=store.load_context("cava"),
        )
        prices = {
            ticker: value.get("market_state", {}).get("current_price")
            for ticker, value in context.items()
            if value.get("market_state", {}).get("current_price") is not None
        }
        price_timestamps = {ticker: value.get("market_state", {}).get("as_of") for ticker, value in context.items()}
    result = check_watch(watches, prices, previous_prices=previous, price_timestamps=price_timestamps)
    result_payload = dict(result.payload)
    result_payload["watchlist_source"] = str(watch_metadata["source"])
    result_payload["watchlist_source_kind"] = str(watch_metadata["source_kind"])
    result_payload["unparsed_responsibilities"] = watch_metadata.get("unparsed_responsibilities", [])
    result_warnings = tuple(result.warnings) + tuple(str(item) for item in watch_metadata["warnings"])
    result = result.__class__(
        workflow=result.workflow,
        status=result.status,
        metadata=result.metadata,
        payload=result_payload,
        evidence=result.evidence,
        warnings=result_warnings,
        generated_at=result.generated_at,
        safety_boundary=result.safety_boundary,
    )
    _emit(PortfolioWorkflow(store=store).save(result), json_out=json_out, markdown=markdown)
    # Persist only accepted observations, after the result is durably recorded.
    store.save_context("portfolio_watch_prices", {**previous, **{ticker: price for ticker, price in result.payload["prices"].items() if price is not None}})
