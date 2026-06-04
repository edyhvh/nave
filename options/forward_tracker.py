"""Record daily options recommendations and mark forward outcomes."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from options.replay import analyze_ticker_at_date, bulk_price_history, summarize_replay_rows
from options.ticker_strategy import load_strategy_index, registry_tape_alignment

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACKER_DIR = PROJECT_ROOT / "var" / "trackers" / "options_daily"


def tracker_dir(path: Path | None = None) -> Path:
    root = path or DEFAULT_TRACKER_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _day_path(root: Path, day: date) -> Path:
    return root / f"recommendations_{day.isoformat()}.json"


def _marks_path(root: Path) -> Path:
    return root / "marks.jsonl"


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _extract_picks(
    daily_payload: Mapping[str, Any],
    *,
    entry_day: date,
    strategy_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Flatten gems, scan picks, and registry-approved tickers into trackable rows."""
    idx = strategy_index
    if idx is None:
        try:
            idx = load_strategy_index()
        except Exception:
            idx = {}

    gems_block = daily_payload.get("hidden_gems") or daily_payload
    recorded_at = str(
        daily_payload.get("generated_at")
        or gems_block.get("generated_at")
        or datetime.now(timezone.utc).isoformat()
    )
    days_to_exp = int(
        (daily_payload.get("scan") or {}).get("days_to_exp")
        or gems_block.get("days_to_exp")
        or 30
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_row(
        *,
        ticker: str,
        tier: str,
        strategy: str | None,
        bias: str | None,
        setup_summary: str | None,
        gem_score: float | None = None,
        registry_primary: str | None = None,
        registry_warning: str | None = None,
    ) -> None:
        sym = ticker.upper()
        if not sym or sym in seen:
            return
        seen.add(sym)
        alignment = registry_tape_alignment(
            sym,
            strategy or "",
            tape_bias=bias,
            strategy_index=idx,
        )
        out.append(
            {
                "id": _new_id(),
                "recorded_at": recorded_at,
                "entry_date": entry_day.isoformat(),
                "ticker": sym,
                "tier": tier,
                "strategy": strategy,
                "bias": bias,
                "setup_summary": setup_summary,
                "days_to_exp": days_to_exp,
                "gem_score": gem_score,
                "registry_primary": registry_primary or alignment.get("registry_primary"),
                "registry_merge_status": alignment.get("registry_merge_status"),
                "registry_warning": registry_warning or alignment.get("warning"),
                "status": "open",
            }
        )

    for item in gems_block.get("gems") or []:
        ctx = item.get("position") or item
        add_row(
            ticker=str(item.get("ticker") or ctx.get("ticker")),
            tier="gem",
            strategy=str(item.get("strategy") or ctx.get("strategy") or ""),
            bias=ctx.get("bias"),
            setup_summary=ctx.get("setup_summary"),
            gem_score=float(item["gem_score"]) if item.get("gem_score") is not None else None,
        )

    for item in gems_block.get("scan_picks") or []:
        ctx = item.get("position") or item
        add_row(
            ticker=str(item.get("ticker") or ctx.get("ticker")),
            tier="scan_pick",
            strategy=str(item.get("strategy") or ctx.get("strategy") or ""),
            bias=ctx.get("bias"),
            setup_summary=ctx.get("setup_summary") or item.get("setup_summary"),
        )

    for sym, meta in sorted((idx or {}).items()):
        if meta.get("merge_status") != "approved":
            continue
        primary = meta.get("strategy")
        add_row(
            ticker=sym,
            tier="registry_approved",
            strategy=primary,
            bias=None,
            setup_summary=None,
            registry_primary=primary,
        )

    return out


def record_daily_recommendations(
    daily_payload: Mapping[str, Any],
    *,
    entry_day: date | None = None,
    tracker_root: Path | None = None,
    merge_with_existing: bool = True,
) -> dict[str, Any]:
    """Persist today's gems / scan picks / approved registry names."""
    root = tracker_dir(tracker_root)
    day = entry_day or datetime.now(timezone.utc).date()
    path = _day_path(root, day)
    rows = _extract_picks(daily_payload, entry_day=day)

    existing: list[dict[str, Any]] = []
    if merge_with_existing and path.is_file():
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
            existing = list(prior.get("recommendations") or [])
        except (OSError, json.JSONDecodeError):
            existing = []

    by_ticker = {str(r["ticker"]).upper(): r for r in existing}
    for row in rows:
        sym = row["ticker"]
        if sym in by_ticker:
            prev = by_ticker[sym]
            row["id"] = prev.get("id") or row["id"]
            if prev.get("status") == "marked":
                row["status"] = "marked"
                row["marks"] = prev.get("marks")
        by_ticker[sym] = row

    merged = sorted(by_ticker.values(), key=lambda r: (r.get("tier", ""), r["ticker"]))
    payload = {
        "entry_date": day.isoformat(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "recommendation_count": len(merged),
        "recommendations": merged,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"path": str(path), **payload}


def load_open_recommendations(
    *,
    tracker_root: Path | None = None,
    max_age_days: int = 45,
) -> list[dict[str, Any]]:
    root = tracker_dir(tracker_root)
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=max_age_days)
    open_rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("recommendations_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entry_date = date.fromisoformat(str(payload.get("entry_date")))
        if entry_date < cutoff:
            continue
        for row in payload.get("recommendations") or []:
            if row.get("status") != "open":
                continue
            row = dict(row)
            row["_source_file"] = str(path)
            row["_entry_date"] = entry_date
            open_rows.append(row)
    return open_rows


def mark_open_recommendations(
    *,
    as_of: date | None = None,
    offsets_days: list[int] | None = None,
    tracker_root: Path | None = None,
    source: str = "yfinance",
) -> dict[str, Any]:
    """Mark open rows at ``as_of`` for each offset (days since entry)."""
    from options.analyzer import OptionsAnalyzer

    exit_day = as_of or datetime.now(timezone.utc).date()
    offsets = sorted(set(offsets_days or [1, 3, 5, 7]))
    open_rows = load_open_recommendations(tracker_root=tracker_root)
    if not open_rows:
        return {
            "as_of": exit_day.isoformat(),
            "marked": 0,
            "summary": {},
            "message": "no open recommendations",
        }

    tickers = sorted({str(r["ticker"]).upper() for r in open_rows})
    min_entry = min(r["_entry_date"] for r in open_rows)
    prices = bulk_price_history(
        tickers,
        start=min_entry - timedelta(days=5),
        end=exit_day + timedelta(days=1),
    )
    analyzer = OptionsAnalyzer(fetcher_source=source)
    marks_out: list[dict[str, Any]] = []
    file_patches: dict[str, dict[str, dict[str, Any]]] = {}

    for row in open_rows:
        entry_date: date = row["_entry_date"]
        src = str(row.pop("_source_file", ""))
        row.pop("_entry_date", None)
        existing_marks = list(row.get("marks") or [])
        seen_offsets = {int(m["offset_days"]) for m in existing_marks if m.get("offset_days") is not None}

        for offset in offsets:
            if offset in seen_offsets:
                continue
            mark_date = entry_date + timedelta(days=offset)
            if mark_date > exit_day:
                continue
            replay = analyze_ticker_at_date(
                analyzer,
                row["ticker"],
                entry_date=entry_date,
                days_to_exp=int(row.get("days_to_exp") or 30),
                exit_date=mark_date,
                price_history=prices,
            )
            mark_rec = {
                "recommendation_id": row["id"],
                "ticker": row["ticker"],
                "tier": row.get("tier"),
                "entry_date": entry_date.isoformat(),
                "mark_date": mark_date.isoformat(),
                "offset_days": offset,
                "replay_status": replay.get("status"),
                "spot_return_pct": replay.get("spot_return_pct"),
                "profitable": replay.get("profitable"),
                "pnl_dollars": (replay.get("mark") or {}).get("pnl_dollars"),
                "strategy_name": replay.get("strategy_name") or row.get("strategy"),
            }
            existing_marks.append(mark_rec)
            marks_out.append(mark_rec)

        row["marks"] = existing_marks
        row["last_marked_at"] = exit_day.isoformat()
        max_offset = max(offsets) if offsets else 0
        if entry_date + timedelta(days=max_offset) <= exit_day and existing_marks:
            row["status"] = "marked"
        if src:
            file_patches.setdefault(src, {})[str(row["id"])] = row

    for path_str, by_id in file_patches.items():
        path = Path(path_str)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payload["recommendations"] = [
            by_id.get(str(rec.get("id")), rec) for rec in (payload.get("recommendations") or [])
        ]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    marks_path = _marks_path(tracker_dir(tracker_root))
    with marks_path.open("a", encoding="utf-8") as handle:
        for mark in marks_out:
            handle.write(json.dumps(mark) + "\n")

    trade_rows = [m for m in marks_out if m.get("replay_status") == "trade_candidate"]
    summary = summarize_replay_rows(
        [
            {
                "status": "trade_candidate",
                "profitable": m.get("profitable"),
                "mark": {"pnl_dollars": m.get("pnl_dollars")},
                "strategy_name": m.get("strategy_name"),
                "ticker": m.get("ticker"),
            }
            for m in trade_rows
            if m.get("pnl_dollars") is not None
        ]
    )
    by_tier: dict[str, list[dict[str, Any]]] = {}
    for mark in marks_out:
        tier = str(mark.get("tier") or "unknown")
        by_tier.setdefault(tier, []).append(mark)

    tier_summary = {}
    for tier, items in by_tier.items():
        with_pnl = [i for i in items if i.get("pnl_dollars") is not None]
        if not with_pnl:
            continue
        wins = sum(1 for i in with_pnl if i.get("profitable"))
        tier_summary[tier] = {
            "count": len(with_pnl),
            "wins": wins,
            "win_rate": wins / len(with_pnl),
            "avg_pnl_dollars": sum(float(i["pnl_dollars"]) for i in with_pnl) / len(with_pnl),
        }

    return {
        "as_of": exit_day.isoformat(),
        "marked": len(marks_out),
        "open_rows": len(open_rows),
        "summary": summary,
        "by_tier": tier_summary,
        "marks_path": str(marks_path),
    }


def render_tracker_report(summary_payload: Mapping[str, Any]) -> str:
    lines = [
        f"Options forward track — as of {summary_payload.get('as_of')}",
        f"Marks written: {summary_payload.get('marked', 0)}",
    ]
    by_tier = summary_payload.get("by_tier") or {}
    if by_tier:
        lines.append("")
        lines.append("By tier:")
        for tier, stats in sorted(by_tier.items()):
            wr = float(stats.get("win_rate") or 0) * 100
            lines.append(
                f"  {tier}: n={stats.get('count')} win_rate={wr:.0f}% "
                f"avg_pnl=${stats.get('avg_pnl_dollars', 0):.0f}"
            )
    overall = summary_payload.get("summary") or {}
    if overall.get("total"):
        lines.append("")
        lines.append(
            f"Replay-modeled trades: {overall.get('total')} "
            f"win_rate={float(overall.get('win_rate', 0)) * 100:.0f}% "
            f"avg_pnl=${overall.get('avg_pnl_dollars', 0):.0f}"
        )
    return "\n".join(lines)
