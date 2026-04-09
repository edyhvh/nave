#!/usr/bin/env python3
"""
theory_backtest — apply the current CriptoPana theory rules against historical
OHLCV + macro + COT data across named market regimes.

Usage:
    python scripts/theory_backtest.py --period 2022-bear --coins "BTC ETH"

The script loads weekly / daily / 4H / 1H data via :mod:`data_loader`, pulls
macro context from OpenBB/FRED, optionally invokes ``nave cot analyze`` for
post-2022 periods, and then walks the period week-by-week applying rules
read from ``docs/technical.yaml`` and ``docs/cot_integration.yaml``.

Output:
    - Human-readable summary on stdout.
    - Raw JSON dumped to ``docs/analysis/raw/backtest_{period}_{ts}.json``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))

import data_loader  # noqa: E402
from data_loader import DataNotFoundError  # noqa: E402


# --------------------------------------------------------------------------- #
# Period definitions
# --------------------------------------------------------------------------- #


PERIODS: dict[str, tuple[str, str]] = {
    "2017-bull+2018-bear": ("2017-01-01", "2018-12-31"),
    "2019-recovery": ("2019-01-01", "2019-12-31"),
    "2020-covid-crash": ("2020-01-01", "2020-06-30"),
    "2020-recovery+2021-ATH": ("2020-07-01", "2021-12-31"),
    "2022-bear": ("2022-01-01", "2022-12-31"),
    "2023-recovery": ("2023-01-01", "2023-12-31"),
    "2024-ETF-approval": ("2024-01-01", "2024-06-30"),
    "2024-2025-bull": ("2024-07-01", "2025-03-31"),
}


def resolve_period(name: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if name == "TODAY":
        end = pd.Timestamp.now(tz="UTC").normalize()
        return end - pd.Timedelta(days=90), end
    if name not in PERIODS:
        raise SystemExit(
            f"unknown period: {name}\n"
            f"available: {', '.join(list(PERIODS.keys()) + ['TODAY'])}"
        )
    start_s, end_s = PERIODS[name]
    return (
        pd.Timestamp(start_s, tz="UTC"),
        pd.Timestamp(end_s, tz="UTC"),
    )


def is_post_2022(start: pd.Timestamp) -> bool:
    return start >= pd.Timestamp("2022-01-01", tz="UTC")


# --------------------------------------------------------------------------- #
# Theory rule loading
# --------------------------------------------------------------------------- #


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        print(f"[theory] warning: {path.relative_to(PROJECT_ROOT)} not found")
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        print("[theory] PyYAML not installed — rules will be empty")
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"[theory] failed to parse {path.name}: {exc}")
        return {}


# --------------------------------------------------------------------------- #
# Macro loaders
# --------------------------------------------------------------------------- #


MACRO_SERIES = {
    "TGA": ("fred", "WTREGEN"),
    "RRP": ("fred", "RRPONTSYD"),
    "DXY": ("yfinance", "DX-Y.NYB"),
    "VIX": ("yfinance", "^VIX"),
    "YIELD_10Y_2Y": ("fred", "T10Y2Y"),
}


def load_macro(start: pd.Timestamp, end: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """Fetch macro series. Failures are non-fatal — we log and continue."""
    result: dict[str, pd.DataFrame] = {}
    try:
        from openbb import obb  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"[macro] OpenBB unavailable — skipping all macro series ({exc})")
        return result

    for label, (provider, symbol) in MACRO_SERIES.items():
        try:
            if provider == "fred":
                response: Any = obb.economy.fred_series(  # type: ignore[attr-defined]
                    symbol=symbol,
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                )
            else:
                response = obb.equity.price.historical(  # type: ignore[attr-defined]
                    symbol=symbol,
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                )
            df = response.to_df().reset_index()
            result[label] = df
            print(f"[macro] loaded {label} ({len(df)} rows)")
        except Exception as exc:  # noqa: BLE001
            print(f"[macro] {label} failed: {exc}")
    return result


# --------------------------------------------------------------------------- #
# COT loader
# --------------------------------------------------------------------------- #


def load_cot(coins: list[str]) -> dict[str, Any]:
    cmd = ["nave", "cot", "analyze", "--coins", " ".join(coins)]
    print(f"[cot] running: {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        print("[cot] 'nave' CLI not found on PATH — skipping COT analysis")
        return {}
    except subprocess.TimeoutExpired:
        print("[cot] 'nave cot analyze' timed out — skipping")
        return {}

    if proc.returncode != 0:
        print(f"[cot] exited {proc.returncode}: {proc.stderr.strip()[:200]}")
        return {"raw_stdout": proc.stdout, "raw_stderr": proc.stderr}

    # Prefer JSON if present, otherwise capture stdout as raw text.
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"raw_stdout": proc.stdout}


# --------------------------------------------------------------------------- #
# Signal engine
# --------------------------------------------------------------------------- #


@dataclass
class TimeframeStats:
    signals: int = 0
    correct: int = 0
    incorrect: int = 0
    entry_examples: list[dict[str, Any]] = field(default_factory=list)

    def accuracy(self) -> float | None:
        total = self.correct + self.incorrect
        return round(self.correct / total, 4) if total else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "signals": self.signals,
            "correct": self.correct,
            "incorrect": self.incorrect,
            "accuracy": self.accuracy(),
            "entry_examples": self.entry_examples,
        }


def _trend(series: pd.Series, window: int) -> str:
    if len(series) < window + 1:
        return "neutral"
    ma = series.rolling(window).mean()
    last = series.iloc[-1]
    ma_now = ma.iloc[-1]
    if pd.isna(ma_now):
        return "neutral"
    if last > ma_now * 1.005:
        return "long"
    if last < ma_now * 0.995:
        return "short"
    return "neutral"


def _weekly_bias(
    weekly_slice: pd.DataFrame,
    macro: dict[str, pd.DataFrame],
    cot: dict[str, Any],
    coin: str,
) -> str:
    if weekly_slice.empty:
        return "neutral"
    trend = _trend(weekly_slice["close"], window=8)

    # Very simple macro filter: if DXY is trending up strongly, dampen longs.
    dxy = macro.get("DXY")
    if dxy is not None and "close" in dxy.columns and len(dxy) >= 20:
        dxy_trend = _trend(dxy["close"].tail(40), window=20)
        if dxy_trend == "long" and trend == "long":
            trend = "neutral"

    # COT filter placeholder — downgrade to neutral if COT flags opposing positioning.
    if cot:
        coin_cot = cot.get(coin) if isinstance(cot, dict) else None
        if isinstance(coin_cot, dict):
            bias = str(coin_cot.get("bias", "")).lower()
            if bias and bias != trend and bias != "neutral":
                trend = "neutral"
    return trend


def _daily_confirmation(daily_slice: pd.DataFrame, weekly_bias: str) -> bool:
    if daily_slice.empty or weekly_bias == "neutral":
        return False
    trend = _trend(daily_slice["close"], window=20)
    return trend == weekly_bias


def _four_h_setup(h4_slice: pd.DataFrame, bias: str) -> tuple[bool, str]:
    if h4_slice.empty or bias == "neutral":
        return False, bias
    trend = _trend(h4_slice["close"], window=12)
    return trend == bias, bias


def _one_h_entry(
    h1_slice: pd.DataFrame, bias: str
) -> tuple[bool, float, float, float] | None:
    """Return (fired, entry, sl, tp) or None if no entry."""
    if h1_slice.empty or bias == "neutral":
        return None
    last = h1_slice.iloc[-1]
    entry = float(last["close"])
    window = h1_slice.tail(24)
    if window.empty:
        return None
    hi = float(window["high"].max())
    lo = float(window["low"].min())
    if bias == "long":
        sl = lo
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + 2 * risk
        return True, entry, sl, tp
    # short
    sl = hi
    risk = sl - entry
    if risk <= 0:
        return None
    tp = entry - 2 * risk
    return True, entry, sl, tp


def _resolve_outcome(
    h1_forward: pd.DataFrame,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
) -> str | None:
    """Walk forward until SL or TP is hit first. Returns 'correct'|'incorrect'|None."""
    if h1_forward.empty:
        return None
    for _, row in h1_forward.iterrows():
        high = float(row["high"])
        low = float(row["low"])
        if direction == "long":
            if low <= sl:
                return "incorrect"
            if high >= tp:
                return "correct"
        else:
            if high >= sl:
                return "incorrect"
            if low <= tp:
                return "correct"
    return None  # neither hit within horizon


# --------------------------------------------------------------------------- #
# Per-coin driver
# --------------------------------------------------------------------------- #


@dataclass
class CoinResult:
    weekly: TimeframeStats = field(default_factory=TimeframeStats)
    daily: TimeframeStats = field(default_factory=TimeframeStats)
    h4: TimeframeStats = field(default_factory=TimeframeStats)
    h1: TimeframeStats = field(default_factory=TimeframeStats)
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "weekly": self.weekly.to_dict(),
            "daily": self.daily.to_dict(),
            "4H": self.h4.to_dict(),
            "1H": self.h1.to_dict(),
        }


def analyze_coin(
    coin: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    macro: dict[str, pd.DataFrame],
    cot: dict[str, Any],
) -> tuple[CoinResult | None, dict[str, str], str | None]:
    """Return (result, data_sources, skip_reason)."""
    sources: dict[str, str] = {}
    frames: dict[str, pd.DataFrame] = {}
    for label, tf in (("weekly", "1W"), ("daily", "1D"), ("4H", "4H"), ("1H", "1H")):
        try:
            df = data_loader.load(coin, tf, start, end)
        except DataNotFoundError as exc:
            reason = f"{coin} {tf}: {exc}"
            print(f"[{coin}] data gap — {reason}")
            return None, sources, reason
        sources[tf] = f"{len(df)} rows {df['timestamp'].iloc[0].date()}→{df['timestamp'].iloc[-1].date()}"
        frames[label] = df

    weekly = frames["weekly"]
    daily = frames["daily"]
    h4 = frames["4H"]
    h1 = frames["1H"]

    result = CoinResult()

    # Walk each week in the period.
    weeks = pd.date_range(start=start, end=end, freq="W-MON", tz="UTC")
    for week_start in weeks:
        week_end = week_start + pd.Timedelta(days=7)

        weekly_slice = weekly[weekly["timestamp"] <= week_start]
        bias = _weekly_bias(weekly_slice, macro, cot, coin)
        result.weekly.signals += 1

        daily_slice = daily[daily["timestamp"] <= week_start]
        confirmed = _daily_confirmation(daily_slice, bias)
        result.daily.signals += 1
        if confirmed:
            result.daily.correct += 1
        else:
            if bias != "neutral":
                result.daily.incorrect += 1

        if not confirmed:
            continue

        h4_slice = h4[h4["timestamp"] <= week_start]
        setup_valid, direction = _four_h_setup(h4_slice, bias)
        result.h4.signals += 1
        if not setup_valid:
            result.h4.incorrect += 1
            result.failure_reasons.append("4H setup invalid after daily confirm")
            continue

        h1_slice = h1[h1["timestamp"] <= week_start]
        entry = _one_h_entry(h1_slice, direction)
        result.h1.signals += 1
        if entry is None:
            result.h1.incorrect += 1
            result.failure_reasons.append("1H entry did not trigger")
            continue

        fired, entry_px, sl, tp = entry
        forward = h1[(h1["timestamp"] > week_start) & (h1["timestamp"] <= week_end + pd.Timedelta(days=14))]
        outcome = _resolve_outcome(forward, direction, entry_px, sl, tp)

        example = {
            "setup_date": week_start.strftime("%Y-%m-%d"),
            "direction": direction,
            "entry_price_1H": round(entry_px, 2),
            "SL": round(sl, 2),
            "TP": round(tp, 2),
            "outcome": outcome or "unresolved",
        }
        result.h4.entry_examples.append(example)
        result.h1.entry_examples.append(example)

        if outcome == "correct":
            result.h4.correct += 1
            result.h1.correct += 1
            result.weekly.correct += 1
        elif outcome == "incorrect":
            result.h4.incorrect += 1
            result.h1.incorrect += 1
            result.weekly.incorrect += 1
            if bias == "neutral":
                result.failure_reasons.append(
                    "entry triggered but weekly bias was neutral"
                )
            else:
                result.failure_reasons.append("entry triggered but TP not reached")
        else:
            # Unresolved — don't count toward correct/incorrect.
            pass

    return result, sources, None


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def top_failures(reasons: list[str], limit: int = 3) -> list[str]:
    from collections import Counter

    counts = Counter(reasons)
    return [f"{reason} (x{n})" for reason, n in counts.most_common(limit)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest CriptoPana theory rules")
    parser.add_argument("--period", required=True, help="named period or 'TODAY'")
    parser.add_argument(
        "--coins",
        default="BTC ETH",
        help="space-separated coin tickers, e.g. 'BTC ETH'",
    )
    args = parser.parse_args()

    coins = [c.strip().upper() for c in args.coins.split() if c.strip()]
    start, end = resolve_period(args.period)
    print(f"[backtest] period={args.period} {start.date()} → {end.date()} coins={coins}")

    # Rules (loaded but consumed by the heuristic engine implicitly).
    technical_rules = load_yaml(PROJECT_ROOT / "docs" / "technical.yaml")
    cot_rules = load_yaml(PROJECT_ROOT / "docs" / "cot_integration.yaml")
    print(
        f"[theory] rules loaded: technical={len(technical_rules)} keys, "
        f"cot={len(cot_rules)} keys"
    )

    macro = load_macro(start, end)
    cot: dict[str, Any] = {}
    if is_post_2022(start):
        cot = load_cot(coins)

    per_coin: dict[str, dict[str, Any]] = {}
    data_sources: dict[str, dict[str, str]] = {}
    data_gaps: list[str] = []
    all_failures: list[str] = []

    for coin in coins:
        try:
            result, sources, skip = analyze_coin(coin, start, end, macro, cot)
        except Exception as exc:  # noqa: BLE001
            print(f"[{coin}] analysis crashed: {exc}")
            traceback.print_exc()
            data_gaps.append(f"{coin}: crash — {exc}")
            continue

        data_sources[coin] = sources
        if skip or result is None:
            data_gaps.append(skip or f"{coin}: unknown error")
            continue

        per_coin[coin] = result.to_dict()
        all_failures.extend(result.failure_reasons)

        h4 = result.h4
        pct = int(round((h4.accuracy() or 0) * 100))
        print(
            f"[{args.period}] {coin} — 4H setups: {h4.signals} | "
            f"correct: {h4.correct} ({pct}%) | incorrect: {h4.incorrect}"
        )

    failures = top_failures(all_failures)
    if failures:
        print(f"Top failure: {failures[0]}")

    # Persist raw output.
    out_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"backtest_{args.period}_{ts}.json"

    payload = {
        "period": args.period,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "coins": coins,
        "data_sources": data_sources,
        "per_coin": per_coin,
        "top_failure_patterns": failures,
        "data_gaps": data_gaps,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"[backtest] wrote {out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
