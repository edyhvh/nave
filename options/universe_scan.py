"""Reusable equity options universe scanning.

This module is intentionally UI-free so CLI commands, scripts, and Hermes tools
can share one scanning path without importing command modules.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from options.analyzer import OptionsAnalyzer
from options.exceptions import OptionsError

MIN_VALID_SCAN_COVERAGE = 0.60
MIN_VALID_SCAN_COUNT = 10


def payload_trade_candidate(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the best executable setup from an analyzer payload, if any."""
    overlay = payload.get("analysis_overlay") or {}
    decision = overlay.get("trade_decision") or {}
    if decision.get("status") not in {"trade_candidate", "directional_override"}:
        return None
    final_recs = overlay.get("final_recommendations") or {}
    executable = final_recs.get("best_overall_executable_setup") or {}
    if not executable:
        return None
    return dict(executable)


def scan_equity_options_universe(
    *,
    analyzer: OptionsAnalyzer,
    analyzer_factory: Callable[[], OptionsAnalyzer] | None = None,
    tickers: list[str],
    days_to_exp: int,
    top_trades: int,
    workers: int = 1,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Scan an equity ticker universe and rank executable options trades."""
    results: dict[str, dict[str, Any]] = {}
    ranked: list[dict[str, Any]] = []
    errors = 0
    scanned = 0

    def scan_one(ticker: str) -> dict[str, Any]:
        symbol = ticker.strip().upper()
        if not symbol:
            return {"ticker": symbol, "status": "skipped"}
        worker_analyzer = analyzer_factory() if analyzer_factory is not None else analyzer
        try:
            payload = worker_analyzer.run(ticker=symbol, days_to_exp=days_to_exp)
        except OptionsError as exc:
            return {"ticker": symbol, "status": "error", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - keep scan resilient per ticker.
            return {"ticker": symbol, "status": "error", "error": str(exc)}

        executable = payload_trade_candidate(payload)
        top = (payload.get("recommendations") or [{}])[0]
        top_metrics = top.get("metrics") or {}
        top_strategy = (top.get("strategy") or {}).get("name")
        overlay = payload.get("analysis_overlay") or {}
        decision = overlay.get("trade_decision") or {"status": "unknown"}

        decision_status = str(decision.get("status") or "unknown")
        row: dict[str, Any] = {
            "ticker": symbol,
            "status": decision_status if executable else "no_trade",
            "trade_decision": decision,
            "top_modeled_strategy": top_strategy,
            "top_modeled_metrics": {
                "composite_score": top_metrics.get("composite_score"),
                "pop": top_metrics.get("pop"),
                "expected_value": top_metrics.get("expected_value"),
                "probability_of_touch": top_metrics.get("probability_of_touch"),
            },
            "executable_strategy": None,
            "executable_metrics": {},
            "executable_setup": None,
            "warnings": list(overlay.get("warnings") or [])[:5],
        }

        if executable:
            metrics = executable.get("metrics") or {}
            row["executable_strategy"] = executable.get("strategy_name")
            row["executable_setup"] = {
                "strategy_name": executable.get("strategy_name"),
                "bias": executable.get("bias"),
                "thesis": executable.get("thesis"),
                "rationale": executable.get("rationale"),
                "setup_summary": executable.get("setup_summary"),
            }
            row["executable_metrics"] = {
                "composite_score": metrics.get("composite_score"),
                "pop": metrics.get("pop"),
                "expected_value": metrics.get("expected_value"),
                "probability_of_touch": metrics.get("probability_of_touch"),
                "theta_per_day": metrics.get("theta_per_day"),
                "max_loss": metrics.get("max_loss"),
            }
            ranked.append(
                {
                    "ticker": symbol,
                    "strategy_name": executable.get("strategy_name"),
                    "composite_score": metrics.get("composite_score"),
                    "expected_value": metrics.get("expected_value"),
                    "pop": metrics.get("pop"),
                    "probability_of_touch": metrics.get("probability_of_touch"),
                    "max_loss": metrics.get("max_loss"),
                    "setup_summary": executable.get("setup_summary"),
                    "rationale": executable.get("rationale"),
                }
            )
        return row

    symbols = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    max_workers = max(1, min(workers, len(symbols) or 1))

    def handle_row(row: dict[str, Any]) -> None:
        nonlocal errors, scanned
        if row.get("status") == "error":
            errors += 1
        elif row.get("status") != "skipped":
            scanned += 1
        if row.get("ticker"):
            results[str(row["ticker"])] = row
        if progress_callback is not None:
            progress_callback(row)

    if max_workers == 1:
        for symbol in symbols:
            handle_row(scan_one(symbol))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(scan_one, symbol): symbol for symbol in symbols}
            for future in as_completed(futures):
                handle_row(future.result())

    ranked = sorted(
        ranked,
        key=lambda item: (
            float(item.get("composite_score") or 0.0),
            float(item.get("expected_value") or 0.0),
            float(item.get("pop") or 0.0),
            -float(item.get("probability_of_touch") or 100.0),
        ),
        reverse=True,
    )
    tickers_requested = len(tickers)
    coverage_ratio = (scanned / tickers_requested) if tickers_requested else 0.0
    min_required_scanned = min(
        tickers_requested,
        max(MIN_VALID_SCAN_COUNT, int(tickers_requested * MIN_VALID_SCAN_COVERAGE)),
    )
    coverage_ok = scanned >= min_required_scanned
    scan_status = "complete" if coverage_ok else "inconclusive"
    warnings: list[str] = []
    if not coverage_ok:
        warnings.append(
            "Scan coverage too low to treat zero trade candidates as a valid no-trade signal. "
            "This commonly happens when option chains are incomplete before the regular US "
            "options session or when the data provider returns partial chains; rerun during "
            "regular market hours."
        )

    return {
        "strategy": "options_equity_universe_scan_v1",
        "universe": "sp500_top_100",
        "days_to_exp": days_to_exp,
        "summary": {
            "tickers_requested": tickers_requested,
            "tickers_scanned": scanned,
            "trade_candidates": len(ranked),
            "errors": errors,
            "top_trades_returned": min(top_trades, len(ranked)),
            "workers": max_workers,
            "scan_status": scan_status,
            "coverage_ratio": coverage_ratio,
            "min_required_scanned": min_required_scanned,
            "data_quality_warning": warnings[0] if warnings else None,
        },
        "warnings": warnings,
        "ranked": ranked[:top_trades],
        "results": results,
    }
