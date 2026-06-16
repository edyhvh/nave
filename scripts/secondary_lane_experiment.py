#!/usr/bin/env python3
"""Backtest secondary crypto opportunity lanes.

The production review surfaces secondary lanes as WATCH-only ideas. This
experiment asks whether those documented lanes would have had positive edge if
entered on a simple touch of the emitted 4H zone, then managed with the lane's
own invalidation and targets.

This intentionally does not change production execution logic. It is a research
tool for validating relief-rally fades, forming shorts, and notrend scalps.
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

from trading.crypto.analysis.opportunities import detect_secondary_opportunities  # noqa: E402
from trading.crypto.analysis.regime import assess_regime  # noqa: E402
from trading.crypto.cot.cot_analyzer import COTBias  # noqa: E402
from trading.crypto.cot.cot_gate import compute_cot_state, load_cached_cot_history  # noqa: E402
from trading.crypto.cot.context import cot_side_from_bias  # noqa: E402
from trading.crypto.momentum import MomentumSetupEngine, load_momentum_config  # noqa: E402
from trading.crypto.momentum.filters import normalize_frame  # noqa: E402
from trading.crypto.momentum.workflow import (  # noqa: E402
    MOMENTUM_PERIOD_ORDER,
    load_symbol_frames,
    resolve_period,
)

HISTORICAL_PERIODS = [p for p in MOMENTUM_PERIOD_ORDER if p != "TODAY"]
DEFAULT_PERIODS = ["2022-bear", "2023-recovery", "2024-ETF-approval", "2024-2025-bull"]


@dataclass(frozen=True)
class SecondaryTrade:
    period: str
    symbol: str
    kind: str
    side: str
    setup_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    r_multiple: float
    sized_r: float
    size_fraction: float
    confidence: float
    daily_trend: str
    setup_trend: str
    trend_alignment: str
    entry_mode: str
    target_policy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "symbol": self.symbol,
            "kind": self.kind,
            "side": self.side,
            "setup_time": self.setup_time.isoformat(),
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "entry_price": round(self.entry_price, 6),
            "exit_price": round(self.exit_price, 6),
            "stop_price": round(self.stop_price, 6),
            "target_price": round(self.target_price, 6),
            "r_multiple": round(self.r_multiple, 4),
            "sized_r": round(self.sized_r, 4),
            "size_fraction": self.size_fraction,
            "confidence": round(self.confidence, 4),
            "daily_trend": self.daily_trend,
            "setup_trend": self.setup_trend,
            "trend_alignment": self.trend_alignment,
            "entry_mode": self.entry_mode,
            "target_policy": self.target_policy,
        }


def historical_cot_bias(symbol: str, as_of: pd.Timestamp) -> COTBias | None:
    """Build a lightweight COTBias from cached historical net positioning."""
    coin = symbol.upper().replace("USDT", "")
    history = load_cached_cot_history("BTC" if coin == "BTC" else coin)
    state = compute_cot_state(history, as_of)
    if state is None:
        return None

    spec_side, net, pct = state
    if spec_side == "long":
        bias = "bearish"
    elif spec_side == "short":
        bias = "bullish"
    else:
        bias = "neutral"

    confidence = 0.5 if bias == "neutral" else max(0.65, min(0.85, pct))
    return COTBias(
        asset=coin,
        net_non_commercial=int(net),
        pct_oi_non_com=0.0,
        weekly_change=0,
        bias=bias,
        confidence=confidence,
        bias_label=bias.upper(),
        historical_percentile=int(round(pct * 100)),
        metadata={"source": "cached_history_proxy", "spec_side": spec_side},
    )


def primary_action(plans: list[dict[str, Any]], cot_bias: COTBias | None) -> str:
    if any(bool(plan.get("tradeable")) for plan in plans):
        return "enter"
    cot_side = cot_side_from_bias(cot_bias)
    if cot_side and any(str(plan.get("side")) == cot_side for plan in plans):
        return "watch"
    return "stand_aside"


def _zone_entry(side: str, zone: list[float]) -> float:
    if side == "long":
        return float(max(zone))
    return float(min(zone))


def _ema_trend(frame: pd.DataFrame) -> str:
    if len(frame) < 50:
        return "unknown"
    close = float(frame["close"].iloc[-1])
    fast = float(frame["close"].ewm(span=20, adjust=False).mean().iloc[-1])
    slow = float(frame["close"].ewm(span=50, adjust=False).mean().iloc[-1])
    if close > fast > slow:
        return "long"
    if close < fast < slow:
        return "short"
    return "neutral"


def _trend_alignment(side: str, daily_trend: str, setup_trend: str) -> str:
    trends = {daily_trend, setup_trend} - {"unknown", "neutral"}
    if not trends:
        return "neutral"
    if trends == {side}:
        return "aligned"
    if side not in trends:
        return "counter_trend"
    return "mixed"


def _rejection_confirmed(side: str, row: pd.Series, entry: float) -> bool:
    open_ = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    bar_range = max(high - low, 1e-12)
    body = abs(close - open_)
    if side == "short":
        upper_wick = high - max(open_, close)
        return close < entry and close < open_ and upper_wick >= body * 0.5 and upper_wick / bar_range >= 0.25
    lower_wick = min(open_, close) - low
    return close > entry and close > open_ and lower_wick >= body * 0.5 and lower_wick / bar_range >= 0.25


def _target_price(kind: str, targets: list[float], target_policy: str) -> float:
    if target_policy == "tp1":
        return float(targets[0])
    if target_policy == "tp2":
        return float(targets[1] if len(targets) > 1 else targets[0])
    if target_policy == "playbook":
        if kind == "notrend_range_long":
            return float(targets[0])
        return float(targets[1] if len(targets) > 1 else targets[0])
    raise ValueError(f"unknown target_policy: {target_policy}")


def simulate_secondary_trade(
    *,
    period: str,
    symbol: str,
    kind: str,
    side: str,
    setup_time: pd.Timestamp,
    entry_zone: list[float],
    invalidation: float,
    targets: list[float],
    future_trigger: pd.DataFrame,
    max_bars: int,
    size_fraction: float,
    confidence: float,
    daily_trend: str = "unknown",
    setup_trend: str = "unknown",
    entry_mode: str = "touch",
    target_policy: str = "tp2",
) -> SecondaryTrade | None:
    if future_trigger.empty or not entry_zone or invalidation <= 0 or not targets:
        return None

    entry = _zone_entry(side, entry_zone)
    target = _target_price(kind, targets, target_policy)

    touch_idx: pd.Timestamp | None = None
    entry_idx: pd.Timestamp | None = None
    entry_price = entry
    for timestamp, row in future_trigger.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        touched = low <= entry if side == "long" else high >= entry
        if touched:
            touch_idx = pd.Timestamp(timestamp)
            if entry_mode == "touch":
                entry_idx = touch_idx
                break
        if touch_idx is not None and entry_mode == "rejection" and _rejection_confirmed(side, row, entry):
            entry_idx = pd.Timestamp(timestamp)
            entry_price = float(row["close"])
            break
    if touch_idx is None or entry_idx is None:
        return None

    risk = abs(entry_price - invalidation)
    if risk <= 0:
        return None

    if entry_mode == "rejection":
        horizon = future_trigger.loc[future_trigger.index > entry_idx].head(max_bars)
    else:
        horizon = future_trigger.loc[future_trigger.index >= entry_idx].head(max_bars)
    if horizon.empty:
        return None

    exit_price = float(horizon["close"].iloc[-1])
    exit_time = pd.Timestamp(horizon.index[-1])

    for timestamp, row in horizon.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        if side == "long":
            if low <= invalidation:
                exit_price = invalidation
                exit_time = pd.Timestamp(timestamp)
                break
            if high >= target:
                exit_price = target
                exit_time = pd.Timestamp(timestamp)
                break
        else:
            if high >= invalidation:
                exit_price = invalidation
                exit_time = pd.Timestamp(timestamp)
                break
            if low <= target:
                exit_price = target
                exit_time = pd.Timestamp(timestamp)
                break

    if side == "long":
        r_multiple = (exit_price - entry_price) / risk
    else:
        r_multiple = (entry_price - exit_price) / risk

    return SecondaryTrade(
        period=period,
        symbol=symbol,
        kind=kind,
        side=side,
        setup_time=setup_time,
        entry_time=entry_idx,
        exit_time=exit_time,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_price=float(invalidation),
        target_price=target,
        r_multiple=r_multiple,
        sized_r=r_multiple * size_fraction,
        size_fraction=size_fraction,
        confidence=confidence,
        daily_trend=daily_trend,
        setup_trend=setup_trend,
        trend_alignment=_trend_alignment(side, daily_trend, setup_trend),
        entry_mode=entry_mode,
        target_policy=target_policy,
    )


def _metrics(trades: list[SecondaryTrade]) -> dict[str, float]:
    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "sized_expectancy": 0.0,
            "total_r": 0.0,
            "sized_total_r": 0.0,
            "max_dd": 0.0,
        }
    wins = sum(1 for trade in trades if trade.r_multiple > 0)
    cum = peak = mdd = 0.0
    for trade in trades:
        cum += trade.sized_r
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return {
        "trades": len(trades),
        "win_rate": round(wins / len(trades), 4),
        "expectancy": round(sum(t.r_multiple for t in trades) / len(trades), 4),
        "sized_expectancy": round(sum(t.sized_r for t in trades) / len(trades), 4),
        "total_r": round(sum(t.r_multiple for t in trades), 4),
        "sized_total_r": round(sum(t.sized_r for t in trades), 4),
        "max_dd": round(abs(mdd), 4),
    }


def _group_metrics(trades: list[SecondaryTrade], field: str) -> dict[str, dict[str, float]]:
    values = sorted({str(getattr(trade, field)) for trade in trades})
    return {
        value: _metrics([trade for trade in trades if str(getattr(trade, field)) == value])
        for value in values
    }


def run_experiment(
    periods: list[str],
    symbols: list[str],
    *,
    step_bars: int = 6,
    entry_mode: str = "touch",
    target_policy: str = "tp2",
    kinds: set[str] | None = None,
) -> dict[str, Any]:
    if step_bars <= 0:
        raise ValueError("step_bars must be positive")
    if entry_mode not in {"touch", "rejection"}:
        raise ValueError("entry_mode must be touch or rejection")
    if target_policy not in {"tp1", "tp2", "playbook"}:
        raise ValueError("target_policy must be tp1, tp2, or playbook")

    config = load_momentum_config()
    engine = MomentumSetupEngine(config)
    max_bars = config.execution.max_holding_bars
    all_trades: list[SecondaryTrade] = []
    skipped: list[str] = []
    cot_coverage: dict[str, dict[str, Any]] = {}

    for coin in symbols:
        normalized = coin.upper().replace("USDT", "")
        history = load_cached_cot_history("BTC" if normalized == "BTC" else normalized)
        cot_coverage[normalized] = {
            "rows": len(history),
            "start": history["report_date"].min().isoformat() if not history.empty else None,
            "end": history["report_date"].max().isoformat() if not history.empty else None,
            "minimum_rows_for_state": 12,
        }

    for period in periods:
        start, end = resolve_period(period)
        for coin in symbols:
            symbol = f"{coin.upper().replace('USDT', '')}USDT"
            try:
                frames = load_symbol_frames(coin, start, end)
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"{period} {coin}: {exc}")
                continue

            daily = normalize_frame(frames["daily"])
            setup = normalize_frame(frames["setup"])
            trigger = normalize_frame(frames["trigger"])
            active_until: dict[str, pd.Timestamp] = {}
            warmup = max(60, config.breakout.lookback_bars + 10)

            for stop in range(warmup, len(setup), step_bars):
                setup_slice = setup.iloc[: stop + 1]
                end_time = pd.Timestamp(setup_slice.index[-1])
                if any(end_time < ts for ts in active_until.values()):
                    continue
                trigger_slice = trigger.loc[trigger.index <= end_time]
                if len(trigger_slice) < warmup:
                    continue
                as_of = end_time.tz_localize("UTC") if end_time.tzinfo is None else end_time.tz_convert("UTC")
                daily_slice = daily.loc[daily.index <= end_time]
                cot_bias = historical_cot_bias(symbol, as_of)
                if cot_bias is None:
                    continue
                plans = [
                    plan.to_dict()
                    for plan in engine.evaluate_symbol(
                        symbol=symbol,
                        daily_frame=daily_slice,
                        setup_frame=setup_slice,
                        trigger_frame=trigger_slice,
                        as_of=as_of,
                        cot_overlay_mode="historical",
                    )
                ]
                best_plan = max(plans, key=lambda p: int(p.get("confidence_score", 0) or 0), default=None)
                regime = assess_regime(
                    daily=daily_slice,
                    setup=setup_slice,
                    cot_bias=cot_bias,
                    best_plan=best_plan,
                )
                opps = detect_secondary_opportunities(
                    daily=daily_slice,
                    setup=setup_slice,
                    cot_bias=cot_bias,
                    regime=regime,
                    plans=plans,
                    primary_action=primary_action(plans, cot_bias),
                )
                future = trigger.loc[trigger.index > end_time]
                daily_trend = _ema_trend(daily_slice)
                setup_trend = _ema_trend(setup_slice)
                for opp in opps:
                    kind = str(opp["kind"])
                    if kinds is not None and kind not in kinds:
                        continue
                    if end_time < active_until.get(kind, pd.Timestamp.min.tz_localize("UTC")):
                        continue
                    trade = simulate_secondary_trade(
                        period=period,
                        symbol=symbol,
                        kind=kind,
                        side=str(opp["direction"]),
                        setup_time=end_time,
                        entry_zone=list(opp.get("entry_zone") or []),
                        invalidation=float(opp.get("invalidation") or 0.0),
                        targets=list(opp.get("targets") or []),
                        future_trigger=future,
                        max_bars=max_bars,
                        size_fraction=float(opp.get("size_fraction") or 1.0),
                        confidence=float(opp.get("confidence") or 0.0),
                        daily_trend=daily_trend,
                        setup_trend=setup_trend,
                        entry_mode=entry_mode,
                        target_policy=target_policy,
                    )
                    if trade is None:
                        continue
                    all_trades.append(trade)
                    active_until[kind] = trade.exit_time

    return {
        "assumptions": [
            "COT bias is reconstructed from cached net non-commercial history.",
            "WATCH entries are filled on first 1H touch of the emitted 4H zone.",
            "Rejection mode enters at the rejection candle close after zone touch.",
            "Rejection-mode exits begin on the next 1H candle, excluding pre-entry range.",
            "R is reported both raw and multiplied by each lane's size_fraction.",
            f"Setup scan uses every {step_bars} 4H bars.",
            f"Entry mode is {entry_mode}.",
            f"Target policy is {target_policy}.",
        ],
        "periods": periods,
        "symbols": symbols,
        "step_bars": step_bars,
        "entry_mode": entry_mode,
        "target_policy": target_policy,
        "kinds": sorted(kinds) if kinds is not None else "all",
        "cot_coverage": cot_coverage,
        "metrics": _metrics(all_trades),
        "by_kind": _group_metrics(all_trades, "kind"),
        "by_trend_alignment": _group_metrics(all_trades, "trend_alignment"),
        "by_period": _group_metrics(all_trades, "period"),
        "by_symbol": _group_metrics(all_trades, "symbol"),
        "skipped": skipped,
        "trades": [trade.to_dict() for trade in all_trades],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--periods", nargs="+", default=DEFAULT_PERIODS)
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH"])
    parser.add_argument(
        "--step-bars",
        type=int,
        default=6,
        help="Evaluate every N setup bars; 6 equals roughly one daily sample on 4H data.",
    )
    parser.add_argument("--entry-mode", choices=["touch", "rejection"], default="touch")
    parser.add_argument("--target-policy", choices=["tp1", "tp2", "playbook"], default="tp2")
    parser.add_argument("--kinds", nargs="+", default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = run_experiment(
        args.periods,
        args.symbols,
        step_bars=args.step_bars,
        entry_mode=args.entry_mode,
        target_policy=args.target_policy,
        kinds=set(args.kinds) if args.kinds else None,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0

    print("\n=== Secondary lane experiment ===")
    print(json.dumps(payload["metrics"], indent=2))
    print("\nBy kind:")
    for kind, metrics in payload["by_kind"].items():
        print(f"  {kind}: {metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
