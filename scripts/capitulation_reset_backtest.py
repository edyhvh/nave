#!/usr/bin/env python3
"""Replay capitulation-reset lane on 4H bars and report signal counts + PnL.

Offline usage (synthetic fixtures, no network):

    python scripts/capitulation_reset_backtest.py --fixture

Historical replay (requires cached OHLC like momentum backtest):

    python scripts/capitulation_reset_backtest.py --period 2022-bear --symbols BTC ETH
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.crypto.analysis.capitulation_reset import (  # noqa: E402
    assess_cot_early_trend_entry,
    assess_crowded_long_failed_reset_short,
    assess_crowded_long_reset,
)
from trading.crypto.cot.cot_analyzer import COTBias  # noqa: E402


@dataclass(frozen=True)
class CapitulationSignal:
    symbol: str
    setup_time: pd.Timestamp
    action: str
    size_fraction: float
    entry_price: float
    invalidation: float
    target: float
    exit_price: float
    exit_time: pd.Timestamp
    exit_reason: str
    r_multiple: float
    sized_r: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "setup_time": self.setup_time.isoformat(),
            "action": self.action,
            "size_fraction": self.size_fraction,
            "entry_price": round(self.entry_price, 6),
            "invalidation": round(self.invalidation, 6),
            "target": round(self.target, 6),
            "exit_price": round(self.exit_price, 6),
            "exit_time": self.exit_time.isoformat(),
            "exit_reason": self.exit_reason,
            "r_multiple": round(self.r_multiple, 4),
            "sized_r": round(self.sized_r, 4),
        }


def _frame(closes: list[float], *, freq: str = "4h") -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(closes), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=idx,
    )


def build_fixture_frames() -> dict[str, dict[str, pd.DataFrame]]:
    """Synthetic BTC/ETH liquidation-reset replay frames (offline)."""
    daily_closes = [100.0] * 20 + [95, 90, 84, 80, 78, 76, 74, 72, 70, 68, 70, 72, 75, 78, 82]
    setup_closes = [
        100,
        95,
        90,
        84,
        80,
        76,
        74,
        73,
        72,
        70,
        69,
        71,
        70.5,
        71,
        71.2,
        71.4,
        72,
        72.5,
        73,
        73.5,
        74,
        74.5,
        75,
        75.5,
        76,
    ]
    trigger_closes = [68.5, 69.0, 68.7, 69.5, 70.2, 70.8, 71.0, 71.5, 72.0, 72.5, 73.0, 73.5] * 6
    daily_idx = pd.date_range("2025-12-01", periods=len(daily_closes), freq="D", tz="UTC")
    setup_idx = pd.date_range("2026-01-01", periods=len(setup_closes), freq="4h", tz="UTC")
    trigger_idx = pd.date_range("2026-01-01", periods=len(trigger_closes), freq="1h", tz="UTC")

    def _ohlc(closes: list[float], index: pd.DatetimeIndex) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "open": closes,
                "high": [c * 1.01 for c in closes],
                "low": [c * 0.99 for c in closes],
                "close": closes,
                "volume": [1000.0] * len(closes),
            },
            index=index,
        )

    daily = _ohlc(daily_closes, daily_idx)
    setup = _ohlc(setup_closes, setup_idx)
    trigger = _ohlc(trigger_closes, trigger_idx)
    return {
        "BTC": {"daily": daily, "setup": setup, "trigger": trigger},
        "ETH": {"daily": daily.copy(), "setup": setup.copy(), "trigger": trigger.copy()},
    }


def fixture_cot_bias(symbol: str) -> COTBias:
    return COTBias(
        asset=symbol,
        net_non_commercial=10_000,
        pct_oi_non_com=18.0,
        weekly_change=500,
        bias="bearish",
        confidence=0.86,
        historical_percentile=96,
    )


def _simulate_long_trade(
    *,
    symbol: str,
    setup_time: pd.Timestamp,
    action: str,
    size_fraction: float,
    entry_price: float,
    invalidation: float,
    target: float,
    future_setup: pd.DataFrame,
    max_bars: int = 12,
) -> CapitulationSignal | None:
    risk = entry_price - invalidation
    if risk <= 0 or future_setup.empty:
        return None

    exit_price = float(future_setup["close"].iloc[-1])
    exit_time = pd.Timestamp(future_setup.index[-1])
    exit_reason = "mark_to_market"
    for timestamp, row in future_setup.head(max_bars).iterrows():
        low = float(row["low"])
        high = float(row["high"])
        if low <= invalidation:
            exit_price = invalidation
            exit_time = pd.Timestamp(timestamp)
            exit_reason = "stop"
            break
        if high >= target:
            exit_price = target
            exit_time = pd.Timestamp(timestamp)
            exit_reason = "target"
            break
    else:
        if len(future_setup) >= max_bars:
            exit_price = float(future_setup["close"].head(max_bars).iloc[-1])
            exit_time = pd.Timestamp(future_setup.head(max_bars).index[-1])
            exit_reason = "time_stop"

    r_multiple = (exit_price - entry_price) / risk
    return CapitulationSignal(
        symbol=symbol,
        setup_time=setup_time,
        action=action,
        size_fraction=size_fraction,
        entry_price=entry_price,
        invalidation=invalidation,
        target=target,
        exit_price=exit_price,
        exit_time=exit_time,
        exit_reason=exit_reason,
        r_multiple=r_multiple,
        sized_r=r_multiple * size_fraction,
    )


def _simulate_short_trade(
    *,
    symbol: str,
    setup_time: pd.Timestamp,
    action: str,
    size_fraction: float,
    entry_price: float,
    invalidation: float,
    target: float,
    future_setup: pd.DataFrame,
    max_bars: int = 12,
) -> CapitulationSignal | None:
    risk = invalidation - entry_price
    if risk <= 0 or future_setup.empty:
        return None

    exit_price = float(future_setup["close"].iloc[-1])
    exit_time = pd.Timestamp(future_setup.index[-1])
    exit_reason = "mark_to_market"
    for timestamp, row in future_setup.head(max_bars).iterrows():
        low = float(row["low"])
        high = float(row["high"])
        if high >= invalidation:
            exit_price = invalidation
            exit_time = pd.Timestamp(timestamp)
            exit_reason = "stop"
            break
        if low <= target:
            exit_price = target
            exit_time = pd.Timestamp(timestamp)
            exit_reason = "target"
            break
    else:
        if len(future_setup) >= max_bars:
            exit_price = float(future_setup["close"].head(max_bars).iloc[-1])
            exit_time = pd.Timestamp(future_setup.head(max_bars).index[-1])
            exit_reason = "time_stop"

    r_multiple = (entry_price - exit_price) / risk
    return CapitulationSignal(
        symbol=symbol,
        setup_time=setup_time,
        action=action,
        size_fraction=size_fraction,
        entry_price=entry_price,
        invalidation=invalidation,
        target=target,
        exit_price=exit_price,
        exit_time=exit_time,
        exit_reason=exit_reason,
        r_multiple=r_multiple,
        sized_r=r_multiple * size_fraction,
    )


def _trade_metrics(trades: list[CapitulationSignal]) -> dict[str, Any]:
    if not trades:
        return {
            "win_rate": 0.0,
            "avg_r": 0.0,
            "avg_sized_r": 0.0,
            "profit_factor": None,
            "max_drawdown_sized_r": 0.0,
            "exit_reasons": {},
        }

    r_values = [trade.r_multiple for trade in trades]
    sized_r = [trade.sized_r for trade in trades]
    wins = [value for value in sized_r if value > 0]
    losses = [value for value in sized_r if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    exit_reasons: dict[str, int] = {}
    for trade in trades:
        equity += trade.sized_r
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        exit_reasons[trade.exit_reason] = exit_reasons.get(trade.exit_reason, 0) + 1

    return {
        "win_rate": round(len(wins) / len(trades), 4),
        "avg_r": round(sum(r_values) / len(r_values), 4),
        "avg_sized_r": round(sum(sized_r) / len(sized_r), 4),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "max_drawdown_sized_r": round(max_drawdown, 4),
        "exit_reasons": exit_reasons,
    }


def _open_interest_as_of(open_interest: pd.Series | pd.DataFrame | None, as_of: pd.Timestamp) -> pd.Series | pd.DataFrame | None:
    if open_interest is None:
        return None
    if not isinstance(open_interest.index, pd.DatetimeIndex):
        return open_interest
    return open_interest.loc[open_interest.index <= as_of]


def _count_assessment(
    counts: dict[str, int],
    by_kind: dict[str, dict[str, int]],
    *,
    kind: str,
    action: str,
) -> None:
    counts[action] = counts.get(action, 0) + 1
    kind_counts = by_kind.setdefault(kind, {})
    kind_counts[action] = kind_counts.get(action, 0) + 1


def _simulate_assessment_trade(
    *,
    symbol: str,
    end_time: pd.Timestamp,
    assessment,
    setup_slice: pd.DataFrame,
    future: pd.DataFrame,
    max_holding_bars: int,
) -> CapitulationSignal | None:
    if assessment.invalidation is None or not assessment.targets:
        return None
    action = str(assessment.action)
    if action not in {
        "starter_long",
        "confirmed_long",
        "starter_trend_long",
        "confirmed_trend_long",
        "starter_trend_short",
        "confirmed_trend_short",
    }:
        return None
    entry_price = float(setup_slice["close"].iloc[-1])
    if assessment.direction == "short":
        return _simulate_short_trade(
            symbol=symbol,
            setup_time=end_time,
            action=action,
            size_fraction=assessment.size_fraction,
            entry_price=entry_price,
            invalidation=float(assessment.invalidation),
            target=float(assessment.targets[0]),
            future_setup=future,
            max_bars=max_holding_bars,
        )
    return _simulate_long_trade(
        symbol=symbol,
        setup_time=end_time,
        action=action,
        size_fraction=assessment.size_fraction,
        entry_price=entry_price,
        invalidation=float(assessment.invalidation),
        target=float(assessment.targets[0]),
        future_setup=future,
        max_bars=max_holding_bars,
    )


def run_backtest(
    frames_by_symbol: dict[str, dict[str, pd.DataFrame]],
    *,
    cot_bias_fn,
    funding_rate: float | None = -0.0001,
    open_interest: pd.Series | None = None,
    step_bars: int = 1,
    warmup: int = 15,
    max_holding_bars: int = 12,
    oi_contracting: bool = True,
) -> dict[str, Any]:
    if oi_contracting:
        oi = pd.Series([100.0] * 20 + [85.0])
    else:
        oi = open_interest

    counts = {"watch": 0, "starter_long": 0, "confirmed_long": 0}
    by_kind: dict[str, dict[str, int]] = {}
    trades: list[CapitulationSignal] = []
    active_until_by_symbol: dict[str, pd.Timestamp] = {}

    for symbol, frames in frames_by_symbol.items():
        daily = frames["daily"]
        setup = frames["setup"]
        trigger = frames["trigger"]
        cot_bias = cot_bias_fn(symbol)

        for stop in range(warmup, len(setup), step_bars):
            setup_slice = setup.iloc[: stop + 1]
            end_time = pd.Timestamp(setup_slice.index[-1])
            if end_time <= active_until_by_symbol.get(symbol, pd.Timestamp.min.tz_localize("UTC")):
                continue
            trigger_slice = trigger.loc[trigger.index <= end_time]
            daily_slice = daily.loc[daily.index <= end_time]
            if daily_slice.empty:
                continue

            assessments = []
            reset = assess_crowded_long_reset(
                daily=daily_slice,
                setup=setup_slice,
                trigger=trigger_slice if not trigger_slice.empty else None,
                cot_bias=cot_bias,
                funding_rate=funding_rate,
                open_interest=_open_interest_as_of(oi, end_time),
            )
            if reset is not None:
                assessments.append(reset)
            failed_short = assess_crowded_long_failed_reset_short(
                daily=daily_slice,
                setup=setup_slice,
                trigger=trigger_slice if not trigger_slice.empty else None,
                cot_bias=cot_bias,
                funding_rate=funding_rate,
                open_interest=_open_interest_as_of(oi, end_time),
            )
            if failed_short is not None:
                assessments.append(failed_short)
            assessments.extend(
                assess_cot_early_trend_entry(
                    daily=daily_slice,
                    setup=setup_slice,
                    trigger=trigger_slice if not trigger_slice.empty else None,
                    cot_bias=cot_bias,
                    funding_rate=funding_rate,
                    open_interest=_open_interest_as_of(oi, end_time),
                )
            )
            if not assessments:
                continue

            future = setup.loc[setup.index > end_time]
            for assessment in assessments:
                _count_assessment(
                    counts,
                    by_kind,
                    kind=assessment.kind,
                    action=assessment.action,
                )
                trade = _simulate_assessment_trade(
                    symbol=symbol,
                    end_time=end_time,
                    assessment=assessment,
                    setup_slice=setup_slice,
                    future=future,
                    max_holding_bars=max_holding_bars,
                )
                if trade is not None:
                    trades.append(trade)
                    active_until_by_symbol[symbol] = trade.exit_time
                    break

    sized_r = [t.sized_r for t in trades]
    metrics = _trade_metrics(trades)
    return {
        "counts": counts,
        "by_kind": by_kind,
        "trade_count": len(trades),
        "total_sized_r": round(sum(sized_r), 4) if sized_r else 0.0,
        "avg_sized_r": metrics["avg_sized_r"],
        "metrics": metrics,
        "trades": [t.to_dict() for t in trades],
    }


def _load_period_frames(symbols: list[str], period: str) -> dict[str, dict[str, pd.DataFrame]]:
    from trading.crypto.momentum.filters import normalize_frame  # noqa: WPS433
    from trading.crypto.momentum.workflow import load_symbol_frames, resolve_period  # noqa: WPS433

    start, end = resolve_period(period)
    out: dict[str, dict[str, pd.DataFrame]] = {}
    for coin in symbols:
        normalized = coin.upper().replace("USDT", "")
        frames = load_symbol_frames(coin, start, end)
        out[normalized] = {
            "daily": normalize_frame(frames["daily"]),
            "setup": normalize_frame(frames["setup"]),
            "trigger": normalize_frame(frames["trigger"]),
        }
    return out


def _historical_cot_bias(symbol: str, as_of: pd.Timestamp) -> COTBias | None:
    from scripts.secondary_lane_experiment import historical_cot_bias  # noqa: WPS433

    return historical_cot_bias(f"{symbol}USDT", as_of)


def run_period_backtest(
    period: str,
    symbols: list[str],
    *,
    step_bars: int = 6,
    warmup: int = 60,
    assume_reset_derivatives: bool = False,
) -> dict[str, Any]:
    frames_by_symbol = _load_period_frames(symbols, period)
    counts = {"watch": 0, "starter_long": 0, "confirmed_long": 0}
    by_kind: dict[str, dict[str, int]] = {}
    trades: list[CapitulationSignal] = []
    data_gaps: list[str] = []
    active_until_by_symbol: dict[str, pd.Timestamp] = {}

    for symbol, frames in frames_by_symbol.items():
        daily = frames["daily"]
        setup = frames["setup"]
        trigger = frames["trigger"]

        for stop in range(warmup, len(setup), step_bars):
            setup_slice = setup.iloc[: stop + 1]
            end_time = pd.Timestamp(setup_slice.index[-1])
            if end_time <= active_until_by_symbol.get(symbol, pd.Timestamp.min.tz_localize("UTC")):
                continue
            as_of = end_time.tz_localize("UTC") if end_time.tzinfo is None else end_time.tz_convert("UTC")
            cot_bias = _historical_cot_bias(symbol, as_of)
            if cot_bias is None:
                continue
            funding_rate = -0.0001 if assume_reset_derivatives else None
            open_interest = pd.Series([100.0] * 20 + [85.0]) if assume_reset_derivatives else None
            if not assume_reset_derivatives:
                gap = f"{symbol} {as_of.date()}: funding/OI replay unavailable; starter/confirmed reset blocked"
                if not data_gaps or data_gaps[-1] != gap:
                    data_gaps.append(gap)

            trigger_slice = trigger.loc[trigger.index <= end_time]
            daily_slice = daily.loc[daily.index <= end_time]
            assessments = []
            reset = assess_crowded_long_reset(
                daily=daily_slice,
                setup=setup_slice,
                trigger=trigger_slice if not trigger_slice.empty else None,
                cot_bias=cot_bias,
                funding_rate=funding_rate,
                open_interest=open_interest,
            )
            if reset is not None:
                assessments.append(reset)
            failed_short = assess_crowded_long_failed_reset_short(
                daily=daily_slice,
                setup=setup_slice,
                trigger=trigger_slice if not trigger_slice.empty else None,
                cot_bias=cot_bias,
                funding_rate=funding_rate,
                open_interest=open_interest,
            )
            if failed_short is not None:
                assessments.append(failed_short)
            assessments.extend(
                assess_cot_early_trend_entry(
                    daily=daily_slice,
                    setup=setup_slice,
                    trigger=trigger_slice if not trigger_slice.empty else None,
                    cot_bias=cot_bias,
                    funding_rate=funding_rate,
                    open_interest=open_interest,
                )
            )
            if not assessments:
                continue

            future = setup.loc[setup.index > end_time]
            for assessment in assessments:
                _count_assessment(
                    counts,
                    by_kind,
                    kind=assessment.kind,
                    action=assessment.action,
                )
                trade = _simulate_assessment_trade(
                    symbol=symbol,
                    end_time=end_time,
                    assessment=assessment,
                    setup_slice=setup_slice,
                    future=future,
                    max_holding_bars=12,
                )
                if trade is not None:
                    trades.append(trade)
                    active_until_by_symbol[symbol] = trade.exit_time
                    break

    sized_r = [t.sized_r for t in trades]
    metrics = _trade_metrics(trades)
    return {
        "mode": "period",
        "period": period,
        "symbols": symbols,
        "counts": counts,
        "by_kind": by_kind,
        "trade_count": len(trades),
        "total_sized_r": round(sum(sized_r), 4) if sized_r else 0.0,
        "avg_sized_r": metrics["avg_sized_r"],
        "metrics": metrics,
        "data_gaps": data_gaps,
        "trades": [t.to_dict() for t in trades],
    }


def render_summary(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "Capitulation reset backtest",
        f"  watch: {counts.get('watch', 0)}",
        f"  starter_long: {counts.get('starter_long', 0)}",
        f"  confirmed_long: {counts.get('confirmed_long', 0)}",
        f"  traded signals: {payload.get('trade_count', 0)}",
        f"  total sized R: {payload.get('total_sized_r', 0.0)}",
        f"  avg sized R: {payload.get('avg_sized_r', 0.0)}",
    ]
    metrics = payload.get("metrics") or {}
    if metrics:
        lines.extend(
            [
                f"  win rate: {metrics.get('win_rate', 0.0)}",
                f"  profit factor: {metrics.get('profit_factor')}",
                f"  max DD sized R: {metrics.get('max_drawdown_sized_r', 0.0)}",
            ]
        )
    if payload.get("data_gaps"):
        lines.append(f"  data gaps: {len(payload['data_gaps'])}")
    if payload.get("by_kind"):
        lines.append("  by kind:")
        for kind, values in sorted(payload["by_kind"].items()):
            detail = ", ".join(f"{action}={count}" for action, count in sorted(values.items()))
            lines.append(f"    {kind}: {detail}")
    if "period" in payload:
        lines.insert(1, f"  period: {payload['period']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest capitulation reset lane on 4H bars")
    parser.add_argument("--fixture", action="store_true", help="use offline synthetic frames")
    parser.add_argument("--period", help="historical period label (requires cached OHLC)")
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--step-bars", type=int, default=1)
    parser.add_argument(
        "--assume-reset-derivatives",
        action="store_true",
        help="historical experiment only: assume negative funding and material OI contraction",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON payload")
    args = parser.parse_args(argv)

    if args.fixture or not args.period:
        payload = run_backtest(
            build_fixture_frames(),
            cot_bias_fn=fixture_cot_bias,
            step_bars=args.step_bars,
        )
        payload["mode"] = "fixture"
    else:
        payload = run_period_backtest(
            args.period,
            args.symbols,
            step_bars=args.step_bars,
            assume_reset_derivatives=args.assume_reset_derivatives,
        )

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(render_summary(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
