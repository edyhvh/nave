"""Utilities to archive or delete invalid backtest JSON artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class BacktestFileStatus:
    path: Path
    kind: str
    total_trades: int
    has_real_prices: bool
    paired_path: Path | None = None


@dataclass
class BacktestCleanupReport:
    scanned: int
    invalid_count: int
    valid_files: list[BacktestFileStatus]
    affected_files: list[Path]
    archive_dir: Path | None
    action: str


def clean_backtest_outputs(
    output_dir: Path,
    archive_dir: Path | None = None,
    delete: bool = False,
    verbose: bool = True,
) -> BacktestCleanupReport:
    """Clean backtest summary/snapshot files that contain fake prices."""
    output_dir = output_dir.resolve()
    files = sorted(
        [
            p
            for p in output_dir.glob("backtest*.json")
            if p.is_file()
            and (p.name.startswith("backtest_snapshot") or p.name.startswith("backtest_summary"))
        ]
    )
    if delete:
        archive_target: Path | None = None
    else:
        archive_target = (
            archive_dir.resolve()
            if archive_dir is not None
            else (output_dir.parent / "backtest_archive" / "invalid").resolve()
        )
        archive_target.mkdir(parents=True, exist_ok=True)

    snapshots_by_stamp: dict[str, Path] = {}
    summaries_by_stamp: dict[str, Path] = {}
    for path in files:
        stamp = _extract_stamp(path.name)
        if stamp is None:
            continue
        if "snapshot" in path.name:
            snapshots_by_stamp[stamp] = path
        elif "summary" in path.name:
            summaries_by_stamp[stamp] = path

    inspected: list[BacktestFileStatus] = []
    invalid_paths: list[Path] = []
    for path in files:
        status = _inspect(path, snapshots_by_stamp=snapshots_by_stamp, summaries_by_stamp=summaries_by_stamp)
        inspected.append(status)
        if not status.has_real_prices:
            invalid_paths.append(path)

    affected: list[Path] = []
    for path in invalid_paths:
        if delete:
            path.unlink(missing_ok=True)
            affected.append(path)
        else:
            destination = (archive_target or output_dir) / path.name
            if destination.exists():
                destination.unlink()
            path.replace(destination)
            affected.append(destination)

    valid_files = [item for item in inspected if item.has_real_prices]
    report = BacktestCleanupReport(
        scanned=len(files),
        invalid_count=len(invalid_paths),
        valid_files=valid_files,
        affected_files=affected,
        archive_dir=archive_target,
        action="deleted" if delete else "archived",
    )
    if verbose:
        print(_format_report(report=report, output_dir=output_dir))
    return report


def _inspect(
    path: Path,
    snapshots_by_stamp: dict[str, Path],
    summaries_by_stamp: dict[str, Path],
) -> BacktestFileStatus:
    payload = _safe_load(path)
    kind = "snapshot" if "snapshot" in path.name else "summary"
    paired: Path | None = None
    trades = _extract_trades(payload)
    if not trades:
        stamp = _extract_stamp(path.name)
        if stamp:
            if kind == "summary":
                paired = snapshots_by_stamp.get(stamp)
            else:
                paired = summaries_by_stamp.get(stamp)
        if paired is not None:
            trades = _extract_trades(_safe_load(paired))
    has_real_prices = bool(trades) and not any(_is_fake_trade(trade) for trade in trades)
    return BacktestFileStatus(
        path=path,
        kind=kind,
        total_trades=len(trades),
        has_real_prices=has_real_prices,
        paired_path=paired,
    )


def _safe_load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _extract_trades(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("trades", "sample_recent_trades"):
        raw = payload.get(key)
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
    return []


def _extract_stamp(name: str) -> str | None:
    stem = Path(name).stem
    parts = stem.split("_")
    if len(parts) >= 4 and parts[-2].isdigit() and parts[-1].isdigit():
        return f"{parts[-2]}_{parts[-1]}"
    return None


def _is_fake_trade(trade: dict[str, Any]) -> bool:
    try:
        entry_price = float(trade.get("entry_price", 0.0) or 0.0)
        exit_price = float(trade.get("exit_price", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False
    return entry_price == 1.0 or exit_price == 1.0


def _format_report(report: BacktestCleanupReport, output_dir: Path) -> str:
    lines = []
    lines.append("Backtest artifact cleanup report")
    lines.append("=" * 34)
    lines.append(f"Scanned directory: {output_dir}")
    lines.append(f"Total files scanned: {report.scanned}")
    lines.append(f"Invalid files {report.action}: {report.invalid_count}")
    if report.archive_dir is not None:
        lines.append(f"Archive directory: {report.archive_dir}")
    lines.append("")
    lines.append("Files kept (real prices):")
    if not report.valid_files:
        lines.append("  (none)")
    for item in report.valid_files:
        lines.append(
            f"  - {item.path.name} | kind={item.kind} | trades={item.total_trades} | real_prices=yes"
        )
    return "\n".join(lines)
