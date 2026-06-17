"""ISM contracting-industry short backtest for Ondo stock perps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from trading.stocks.ism_calendar import load_calendar
from trading.stocks.ondo_universe import ONDO_STOCK_PERP_UNIVERSE, is_ondo_stock_perp
from trading.stocks.price_provider import PriceProviderLike, YFinancePriceProvider, price_on_or_before
from trading.stocks.strategy import (
    DEFAULT_SHORT_HOLDING_WINDOW_DAYS,
    DEFAULT_SHORT_MAX_LEVERAGE,
    DEFAULT_SHORT_RISK_PCT,
    DEFAULT_SHORT_STOP_PCT,
    DEFAULT_SHORT_TARGET_PCT,
    _normalize_min_short_score,
)


@dataclass(frozen=True)
class ShortBacktestTrade:
    symbol: str
    sector: str
    kind: str
    covers_month: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    return_pct: float
    confidence: float
    score: float
    short_quality_score: float | None
    ondo_perp: bool
    entry_rule: str
    target: dict[str, Any]
    stop: dict[str, Any]
    holding_window_days: int
    risk_pct: float
    size_guidance: str
    max_leverage: float

    def to_dict(self) -> dict[str, Any]:
        out = {
            "symbol": self.symbol,
            "sector": self.sector,
            "kind": self.kind,
            "covers_month": self.covers_month,
            "entry_date": self.entry_date,
            "exit_date": self.exit_date,
            "entry_price": round(self.entry_price, 4),
            "exit_price": round(self.exit_price, 4),
            "return_pct": round(self.return_pct, 4),
            "confidence": round(self.confidence, 4),
            "score": round(self.score, 4),
            "short_quality_score": (
                round(self.short_quality_score, 4)
                if self.short_quality_score is not None
                else None
            ),
            "ondo_perp": self.ondo_perp,
            "entry_rule": self.entry_rule,
            "target": self.target,
            "stop": self.stop,
            "holding_window_days": self.holding_window_days,
            "risk_pct": round(self.risk_pct, 4),
            "size_guidance": self.size_guidance,
            "max_leverage": round(self.max_leverage, 4),
        }
        out["trade_plan"] = {
            "entry_rule": self.entry_rule,
            "entry_price": out["entry_price"],
            "target": self.target,
            "stop": self.stop,
            "holding_window_days": self.holding_window_days,
            "risk_pct": out["risk_pct"],
            "size_guidance": self.size_guidance,
            "max_leverage": out["max_leverage"],
        }
        return out


class ISMShortBacktester:
    def __init__(self, price_provider: PriceProviderLike | None = None):
        self.price_provider = price_provider or YFinancePriceProvider()

    def evaluate(
        self,
        *,
        snapshot_dir: str | Path,
        kinds: list[Literal["manufacturing", "services"]] | None = None,
        from_month: str | None = None,
        to_month: str | None = None,
        min_confidence: float = 0.3,
        min_short_score: float | None = None,
        research_mode: bool = False,
        latest_months: int | None = 6,
        ondo_only: bool = True,
    ) -> dict[str, Any]:
        effective_min_short_score = _normalize_min_short_score(
            min_short_score,
            research_mode=research_mode,
        )
        snapshot_path = Path(snapshot_dir)
        selected_kinds = kinds or ["manufacturing", "services"]
        snapshots = _load_snapshots(
            snapshot_path,
            kinds=selected_kinds,
            from_month=None if latest_months and from_month is None else from_month,
            to_month=to_month,
        )
        snapshots, effective_from_month, effective_to_month = _apply_latest_window(
            snapshots,
            from_month=from_month,
            to_month=to_month,
            latest_months=latest_months,
        )
        cycles = _build_cycles(snapshots)
        trades: list[ShortBacktestTrade] = []
        skipped: list[dict[str, Any]] = []

        for cycle in cycles:
            entry_date = cycle["entry_date"]
            exit_date = cycle["exit_date"]
            if exit_date <= entry_date:
                skipped.append(
                    {
                        "kind": cycle["kind"],
                        "covers_month": cycle["covers_month"],
                        "reason": "missing_next_release",
                    }
                )
                continue

            shorts = _short_signals(
                cycle["payload"],
                min_confidence=min_confidence,
                min_short_score=effective_min_short_score,
                research_mode=research_mode,
                ondo_only=ondo_only,
            )
            if not shorts:
                continue

            symbols = sorted({row["symbol"] for row in shorts})
            prices = self.price_provider.fetch_daily_closes(
                symbols,
                start=entry_date - timedelta(days=7),
                end=exit_date + timedelta(days=7),
            )
            for row in shorts:
                symbol = row["symbol"]
                entry_px = price_on_or_before(prices.get(symbol, pd.Series(dtype=float)), entry_date)
                exit_px = price_on_or_before(prices.get(symbol, pd.Series(dtype=float)), exit_date)
                if entry_px is None or exit_px is None or entry_px <= 0:
                    skipped.append(
                        {
                            "symbol": symbol,
                            "kind": cycle["kind"],
                            "covers_month": cycle["covers_month"],
                            "reason": "missing_price",
                        }
                    )
                    continue
                return_pct = (entry_px - exit_px) / entry_px * 100.0
                trade_plan = _priced_trade_plan(
                    row=row,
                    entry_price=entry_px,
                    holding_window_days=max((exit_date - entry_date).days, 1),
                )
                trades.append(
                    ShortBacktestTrade(
                        symbol=symbol,
                        sector=str(row.get("sector") or "?"),
                        kind=cycle["kind"],
                        covers_month=cycle["covers_month"],
                        entry_date=entry_date.isoformat(),
                        exit_date=exit_date.isoformat(),
                        entry_price=entry_px,
                        exit_price=exit_px,
                        return_pct=return_pct,
                        confidence=float(row.get("confidence") or 0.0),
                        score=float(row.get("score") or 0.0),
                        short_quality_score=_optional_float(
                            row.get("short_quality_score")
                        ),
                        ondo_perp=bool(row.get("ondo_perp")),
                        entry_rule=str(trade_plan["entry_rule"]),
                        target=trade_plan["target"],
                        stop=trade_plan["stop"],
                        holding_window_days=int(trade_plan["holding_window_days"]),
                        risk_pct=float(trade_plan["risk_pct"]),
                        size_guidance=str(trade_plan["size_guidance"]),
                        max_leverage=float(trade_plan["max_leverage"]),
                    )
                )

        return _summarize(
            trades=trades,
            skipped=skipped,
            snapshots=snapshots,
            kinds=selected_kinds,
            from_month=effective_from_month,
            to_month=effective_to_month,
            min_confidence=min_confidence,
            min_short_score=effective_min_short_score,
            research_mode=research_mode,
            latest_months=latest_months,
            ondo_only=ondo_only,
        )


def _load_snapshots(
    snapshot_dir: Path,
    *,
    kinds: list[str],
    from_month: str | None,
    to_month: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(snapshot_dir.glob("ism_*.json")):
        if path.name.startswith("ism_calendar"):
            continue
        payload = json.loads(path.read_text())
        kind = str(payload.get("kind") or "")
        if kind not in kinds:
            continue
        covers_month = _month_key(payload)
        if from_month and covers_month < from_month:
            continue
        if to_month and covers_month > to_month:
            continue
        rows.append(
            {
                "path": str(path),
                "kind": kind,
                "covers_month": covers_month,
                "payload": payload,
            }
        )
    return sorted(rows, key=lambda row: (row["kind"], row["covers_month"]))


def _apply_latest_window(
    snapshots: list[dict[str, Any]],
    *,
    from_month: str | None,
    to_month: str | None,
    latest_months: int | None,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    if not snapshots:
        return snapshots, from_month, to_month
    if from_month is not None or not latest_months:
        effective_to = to_month or max(row["covers_month"] for row in snapshots)
        return snapshots, from_month, effective_to
    if latest_months < 1:
        raise ValueError("latest_months must be >= 1")
    effective_to = to_month or max(row["covers_month"] for row in snapshots)
    effective_from = _shift_month(effective_to, -(latest_months - 1))
    filtered = [
        row
        for row in snapshots
        if effective_from <= row["covers_month"] <= effective_to
    ]
    return filtered, effective_from, effective_to


def _shift_month(month: str, offset: int) -> str:
    year = int(month[:4])
    month_num = int(month[5:7])
    zero_based = year * 12 + (month_num - 1) + offset
    shifted_year, shifted_month = divmod(zero_based, 12)
    return f"{shifted_year:04d}-{shifted_month + 1:02d}"


def _build_cycles(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for row in snapshots:
        by_kind.setdefault(row["kind"], []).append(row)

    cycles: list[dict[str, Any]] = []
    for kind, rows in by_kind.items():
        ordered = sorted(rows, key=lambda row: row["covers_month"])
        for idx, row in enumerate(ordered):
            entry_date = _release_date_for_month(kind=kind, covers_month=row["covers_month"])
            if entry_date is None:
                continue
            exit_date = None
            if idx + 1 < len(ordered):
                exit_date = _release_date_for_month(
                    kind=kind,
                    covers_month=ordered[idx + 1]["covers_month"],
                )
            if exit_date is None:
                exit_date = entry_date + timedelta(days=28)
            cycles.append(
                {
                    "kind": kind,
                    "covers_month": row["covers_month"],
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "payload": row["payload"],
                }
            )
    return cycles


def _release_date_for_month(*, kind: str, covers_month: str) -> date | None:
    year = int(covers_month[:4])
    for target_year in (year, year + 1):
        calendar = load_calendar(target_year)
        if calendar is None:
            continue
        for release in calendar.releases:
            if release.kind == kind and release.covers_month == covers_month:
                return datetime.fromisoformat(release.release_at_utc).date()
    return None


def _short_signals(
    payload: dict[str, Any],
    *,
    min_confidence: float,
    min_short_score: float,
    research_mode: bool,
    ondo_only: bool,
) -> list[dict[str, Any]]:
    candidates = payload.get("candidates") or {}
    rows = candidates.get("shorts") or candidates.get("contracting") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("side") or "short") != "short":
            continue
        confidence = float(row.get("confidence") or 0.0)
        if confidence < min_confidence:
            continue
        score = float(row.get("score") or 0.0)
        if score <= min_short_score and not research_mode:
            continue
        if score < min_short_score and research_mode:
            continue
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        ondo_perp = is_ondo_stock_perp(symbol)
        if ondo_only and not ondo_perp:
            continue
        out.append({**row, "symbol": symbol, "ondo_perp": ondo_perp})
    return out


def _priced_trade_plan(
    *,
    row: dict[str, Any],
    entry_price: float,
    holding_window_days: int,
) -> dict[str, Any]:
    plan = row.get("trade_plan")
    if not isinstance(plan, dict):
        plan = {}
    target_price = round(entry_price * (1.0 - DEFAULT_SHORT_TARGET_PCT), 4)
    stop_price = round(entry_price * (1.0 + DEFAULT_SHORT_STOP_PCT), 4)
    risk_pct = _optional_float(plan.get("risk_pct")) or DEFAULT_SHORT_RISK_PCT
    max_leverage = _optional_float(plan.get("max_leverage")) or DEFAULT_SHORT_MAX_LEVERAGE
    return {
        "entry_rule": plan.get("entry_rule")
        or "Enter short on the next Ondo stock-perp session after the ISM signal.",
        "entry_price": round(entry_price, 4),
        "target": {
            "price": target_price,
            "rule": _nested_rule(
                plan.get("target"),
                f"Cover into {DEFAULT_SHORT_TARGET_PCT:.0%} favorable move or before next ISM release.",
            ),
        },
        "stop": {
            "price": stop_price,
            "rule": _nested_rule(
                plan.get("stop"),
                f"Cover on {DEFAULT_SHORT_STOP_PCT:.0%} adverse move or thesis invalidation.",
            ),
        },
        "holding_window_days": holding_window_days or DEFAULT_SHORT_HOLDING_WINDOW_DAYS,
        "risk_pct": risk_pct,
        "size_guidance": _size_guidance_or_default(plan.get("size_guidance"), risk_pct),
        "max_leverage": max_leverage,
    }


def _size_guidance_or_default(value: Any, risk_pct: float) -> str:
    if isinstance(value, str) and value.strip() and "$0.00" not in value:
        return value
    return f"Equal-weight research short; keep account risk near {risk_pct:.1%}."


def _nested_rule(value: Any, fallback: str) -> str:
    if isinstance(value, dict) and isinstance(value.get("rule"), str):
        return value["rule"]
    return fallback


def _month_key(payload: dict[str, Any]) -> str:
    report_month = str(payload.get("report_month") or "").strip()
    if report_month:
        try:
            dt = datetime.strptime(report_month, "%B %Y")
            return dt.strftime("%Y-%m")
        except ValueError:
            pass
    generated_at = str(payload.get("generated_at") or "")
    if len(generated_at) >= 7:
        return generated_at[:7]
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summarize(
    *,
    trades: list[ShortBacktestTrade],
    skipped: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    kinds: list[str],
    from_month: str | None,
    to_month: str | None,
    min_confidence: float,
    min_short_score: float,
    research_mode: bool,
    latest_months: int | None,
    ondo_only: bool,
) -> dict[str, Any]:
    trade_dicts = [trade.to_dict() for trade in trades]
    wins = [trade for trade in trades if trade.return_pct > 0]
    losses = [trade for trade in trades if trade.return_pct <= 0]
    avg_return = (
        sum(trade.return_pct for trade in trades) / len(trades) if trades else 0.0
    )
    by_kind: dict[str, list[ShortBacktestTrade]] = {}
    for trade in trades:
        by_kind.setdefault(trade.kind, []).append(trade)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback": {
            "from_month": from_month,
            "to_month": to_month,
            "kinds": kinds,
            "latest_months": latest_months,
            "min_confidence": min_confidence,
            "min_short_score": min_short_score,
            "research_mode": research_mode,
            "ondo_only": ondo_only,
            "ondo_universe_size": len(ONDO_STOCK_PERP_UNIVERSE),
        },
        "snapshots_used": [
            {"path": row["path"], "kind": row["kind"], "covers_month": row["covers_month"]}
            for row in snapshots
        ],
        "summary": {
            "trade_count": len(trades),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
            "avg_return_pct": round(avg_return, 4),
            "total_return_pct": round(sum(trade.return_pct for trade in trades), 4),
            "skipped_count": len(skipped),
        },
        "by_kind": {
            kind: {
                "trade_count": len(kind_trades),
                "avg_return_pct": round(
                    sum(t.return_pct for t in kind_trades) / len(kind_trades), 4
                )
                if kind_trades
                else 0.0,
            }
            for kind, kind_trades in by_kind.items()
        },
        "trades": trade_dicts,
        "skipped": skipped,
    }
