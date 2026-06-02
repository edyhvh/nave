"""Full per-ticker strategy iteration: replay → walk-forward → journal → registry → gems."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from options.gems_pipeline import format_gem_digest, run_hidden_gems_scan
from options.journal_learning import load_options_journal_rows
from options.ticker_registry import (
    DEFAULT_REGISTRY_DIR,
    RegistryPaths,
    build_registry,
    load_yearly_replay_rows,
)
from options.universe import get_sp500_top40
from options.merge_readiness import summarize_registry_merge_readiness
from options.walkforward import walkforward_universe_summary


def _latest_replay_path(raw_dir: Path) -> Path | None:
    candidates = sorted(raw_dir.glob("options_yearly_*.json"))
    return candidates[-1] if candidates else None


def run_replay_backtest(
    *,
    limit: int = 40,
    months: int = 12,
    workers: int = 2,
    output: Path | None = None,
) -> Path:
    """Run monthly options replay; returns path to JSON."""
    import subprocess
    import sys

    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts" / "options_yearly_backtest.py"),
        "--limit",
        str(limit),
        "--months",
        str(months),
        "--workers",
        str(workers),
    ]
    if output:
        cmd.extend(["--output", str(output)])
    subprocess.run(cmd, check=True)
    raw = Path(__file__).resolve().parents[1] / "docs" / "analysis" / "raw"
    return output or _latest_replay_path(raw) or raw / "options_yearly_missing.json"


def run_strategy_iteration(
    *,
    tickers: list[str] | None = None,
    replay_json: Path | None = None,
    run_backtest: bool = False,
    backtest_months: int = 12,
    backtest_limit: int = 40,
    registry_dir: Path | None = None,
    run_gems: bool = True,
    gems_limit: int = 40,
    gems_top: int = 10,
    gems_workers: int = 2,
    journal_dir: Path | None = None,
    n_folds: int = 4,
    scan_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    One full learning iteration (no X):

    1. Optional fresh yearly replay backtest
    2. Walk-forward validate per ticker
    3. Merge manual options journal rows
    4. Rebuild registry with learned + walk-forward blocks
    5. Optional hidden-gems scan (registry-aware scoring)
    """
    symbols = [t.strip().upper() for t in (tickers or get_sp500_top40()) if t.strip()]
    root = Path(__file__).resolve().parents[1]
    raw_dir = root / "docs" / "analysis" / "raw"
    iter_dir = root / "docs" / "analysis" / "iterations"
    iter_dir.mkdir(parents=True, exist_ok=True)

    if run_backtest:
        replay_path = run_replay_backtest(
            limit=backtest_limit,
            months=backtest_months,
            workers=gems_workers,
        )
    elif replay_json and replay_json.is_file():
        replay_path = replay_json
    else:
        replay_path = _latest_replay_path(raw_dir)

    if replay_path is None or not replay_path.is_file():
        raise FileNotFoundError(
            "No replay JSON found. Run with --backtest or pass --replay-json."
        )

    replay_rows = json.loads(replay_path.read_text(encoding="utf-8")).get("rows") or []
    journal_rows = load_options_journal_rows(journal_dir)
    combined_rows = list(replay_rows) + list(journal_rows)

    from options.ticker_strategy import INCOME_STRATEGIES

    wf = walkforward_universe_summary(
        replay_rows,
        symbols,
        n_folds=n_folds,
        strategies=INCOME_STRATEGIES,
    )

    reg_paths = RegistryPaths(registry_dir or DEFAULT_REGISTRY_DIR)
    reg_result = build_registry(
        symbols,
        paths=reg_paths,
        replay_json=replay_path,
        include_live_options=False,
        extra_rows=journal_rows,
        walkforward_by_ticker=wf.get("per_ticker"),
    )
    merge_summary = summarize_registry_merge_readiness(reg_result["profiles"])

    gems_payload: dict[str, Any] | None = None
    if run_gems and scan_fn is not None:
        scan = scan_fn(
            tickers=symbols[:gems_limit],
            days_to_exp=30,
            top_trades=gems_top,
            workers=gems_workers,
        )
        gems_payload = run_hidden_gems_scan(scan, top=gems_top, fetch_x_for_top=0)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "iteration": ts,
        "replay_source": str(replay_path),
        "journal_trades_merged": len(journal_rows),
        "walkforward": {
            "n_folds": n_folds,
            "with_oos_trades": wf.get("with_oos_trades"),
            "leaderboard": wf.get("leaderboard"),
        },
        "merge_readiness": merge_summary,
        "registry": {
            "root": str(reg_paths.root),
            "tickers": symbols,
        },
        "hidden_gems": gems_payload,
    }

    report_path = iter_dir / f"ticker_strategy_{ts}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    md_lines = _format_iteration_markdown(report, reg_result, wf, merge_summary)
    md_path = iter_dir / f"ticker_strategy_{ts}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return {
        **report,
        "report_json": str(report_path),
        "report_md": str(md_path),
        "registry_index": reg_result["index"],
    }


def _format_iteration_markdown(
    report: dict[str, Any],
    reg_result: dict[str, Any],
    wf: dict[str, Any],
    merge_summary: dict[str, Any],
) -> list[str]:
    ready = merge_summary.get("ready_to_merge")
    lines = [
        f"# Ticker strategy iteration — {report.get('iteration')}",
        "",
        f"- Replay: `{report.get('replay_source')}`",
        f"- Journal rows merged: {report.get('journal_trades_merged')}",
        f"- Registry: `{report.get('registry', {}).get('root')}`",
        f"- **Merge ready:** {ready}",
        "",
        "## Merge readiness",
        "",
        f"- Approved: {merge_summary['counts']['approved']} "
        f"(need {merge_summary.get('min_approved')})",
        f"- Watch: {merge_summary['counts']['watch']} "
        f"(need {merge_summary.get('min_watch')})",
        f"- Reject: {merge_summary['counts']['reject']}",
        "",
    ]
    if merge_summary.get("blockers"):
        lines.append("**Blockers:**")
        for b in merge_summary["blockers"]:
            lines.append(f"- {b}")
        lines.append("")
    lines.append("**Approved tickers:** " + ", ".join(merge_summary.get("approved_tickers") or []) or "—")
    lines.append("")
    lines.extend(
        [
            "## Walk-forward OOS (top 15)",
            "",
            "| Ticker | OOS win | OOS n | Primary | Stable |",
            "|--------|---------|-------|---------|--------|",
        ]
    )
    for row in (wf.get("leaderboard") or [])[:15]:
        wr = row.get("oos_win_rate")
        wr_s = f"{wr:.0%}" if isinstance(wr, (int, float)) else "—"
        lines.append(
            f"| {row['ticker']} | {wr_s} | {row.get('oos_trades')} | "
            f"{row.get('last_primary') or '—'} | {row.get('primary_stable')} |"
        )

    lines.extend(["", "## Learned primary per ticker", ""])
    index = reg_result.get("index") or {}
    for sym in sorted((index.get("profiles") or {}).keys()):
        meta = index["profiles"][sym]
        lines.append(
            f"- **{sym}** [{meta.get('merge_status', '?')}]: {meta.get('preferred_setup')} "
            f"(edge {meta.get('learned_edge_score')}, conf {meta.get('learned_confidence')}, "
            f"replay WR {meta.get('best_win_rate')}, OOS {meta.get('oos_win_rate')})"
        )

    gems = report.get("hidden_gems") or {}
    hg = gems.get("hidden_gems") or {}
    gem_list = hg.get("gems") or []
    lines.extend(["", "## Hidden gems today", ""])
    if gem_list:
        lines.append(format_gem_digest(gem_list))
    else:
        lines.append("_No gems passed filters._")
        for w in (hg.get("watchlist") or [])[:5]:
            lines.append(
                f"- Watch: {w.get('ticker')} score {w.get('gem_score')} "
                f"{w.get('strategy')}"
            )

    return lines