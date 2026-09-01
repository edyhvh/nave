#!/usr/bin/env python3
"""Build frozen Stage-1 activity labels and a small A-vs-C sanity comparison."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import pyarrow.parquet as pq

from research.nave.stage1 import SurvivalStatus, future_trade_label


UTC = timezone.utc
DECISIONS = (60, 180, 300, 600)
HORIZONS = (900, 1800, 3600)


def parse_day(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)


def launches_from(day: str, manifest: Path | None, events: pd.DataFrame) -> pd.DataFrame:
    if manifest is not None:
        rows = json.loads(manifest.read_text())["rows"]
        result = pd.DataFrame(rows)
        # pandas 3 may retain datetime64[us]; normalize through timestamp so
        # the event tape's millisecond epoch is not shifted by 1,000x.
        result["launch_time_ms"] = pd.to_datetime(result["launch_ts"], utc=True).map(lambda value: int(value.timestamp() * 1000))
        return result[["mint", "launch_time_ms"]]
    creates = events.loc[events.event_type.eq("CREATE"), ["mint", "event_time_ms"]].dropna()
    creates = creates.sort_values(["mint", "event_time_ms"]).drop_duplicates("mint")
    creates = creates.rename(columns={"event_time_ms": "launch_time_ms"})
    creates["launch_time_ms"] = creates["launch_time_ms"].astype("int64")
    return creates[["mint", "launch_time_ms"]]


def _finite(value: object) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def build_rows(day: str, event_path: Path, manifest: Path | None) -> tuple[pd.DataFrame, dict]:
    events = pq.read_table(event_path).to_pandas()
    events["event_time_ms"] = pd.to_numeric(events["event_time_ms"], errors="coerce")
    events = events.loc[events.event_time_ms.notna()].copy()
    launches = launches_from(day, manifest, events)
    event_by_mint = {mint: group.sort_values("event_time_ms") for mint, group in events.groupby("mint", sort=False)}
    collection_end = parse_day(day) + 86_400_000
    records: list[dict] = []
    mark_bias: list[dict] = []
    for launch in launches.itertuples(index=False):
        mint = str(launch.mint)
        launch_ms = int(launch.launch_time_ms)
        group = event_by_mint.get(mint, events.iloc[0:0])
        trades = group.loc[group.event_type.isin(["BUY", "SELL"]) & (group.event_time_ms >= launch_ms)].copy()
        trade_times = trades.event_time_ms.astype("int64").tolist()
        migrations = group.loc[group.event_type.eq("MIGRATE"), "event_time_ms"].dropna().astype("int64").tolist()
        valid_prices = trades.loc[pd.to_numeric(trades.price, errors="coerce").notna()].copy()
        valid_prices["price"] = pd.to_numeric(valid_prices.price, errors="coerce")
        first_price = float(valid_prices.price.iloc[0]) if len(valid_prices) else None
        for decision_s in DECISIONS:
            decision_ms = launch_ms + decision_s * 1000
            before = trades.loc[trades.event_time_ms <= decision_ms]
            buys = before.loc[before.event_type.eq("BUY")]
            sells = before.loc[before.event_type.eq("SELL")]
            quote_buy = pd.to_numeric(buys.quote_amount, errors="coerce").dropna()
            quote_sell = pd.to_numeric(sells.quote_amount, errors="coerce").dropna()
            price_before = valid_prices.loc[valid_prices.event_time_ms <= decision_ms]
            decision_price = float(price_before.price.iloc[-1]) if len(price_before) else None
            log_return = math.log(decision_price / first_price) if decision_price and first_price and decision_price > 0 and first_price > 0 else None
            def window_stats(start_s: int, end_s: int) -> tuple[int, float, float]:
                subset = trades.loc[(trades.event_time_ms > launch_ms + start_s * 1000) & (trades.event_time_ms <= launch_ms + end_s * 1000)]
                b = pd.to_numeric(subset.loc[subset.event_type.eq("BUY"), "quote_amount"], errors="coerce").dropna()
                s = pd.to_numeric(subset.loc[subset.event_type.eq("SELL"), "quote_amount"], errors="coerce").dropna()
                return len(subset), float(b.sum()), float(s.sum())
            recent_count, recent_buy, recent_sell = window_stats(max(0, decision_s - 60), decision_s)
            prior_count, prior_buy, prior_sell = window_stats(max(0, decision_s - 120), max(0, decision_s - 60))
            buyers_recent = set(buys.loc[buys.event_time_ms > decision_ms - 60_000, "wallet"].dropna().astype(str))
            buyers_prior = set(buys.loc[(buys.event_time_ms > decision_ms - 120_000) & (buys.event_time_ms <= decision_ms - 60_000), "wallet"].dropna().astype(str))
            migration_state = int(any(time_ms <= decision_ms for time_ms in migrations))
            latest_reserve = pd.to_numeric(before.real_quote_reserves, errors="coerce").dropna()
            curve_progress = float(math.log1p(latest_reserve.iloc[-1])) if len(latest_reserve) else 0.0
            concentration_values = pd.to_numeric(before.quote_amount, errors="coerce").dropna()
            concentration = float(concentration_values.max() / concentration_values.sum()) if len(concentration_values) and concentration_values.sum() > 0 else 0.0
            for horizon_s in HORIZONS:
                label = future_trade_label(
                    decision_ms=decision_ms,
                    window_start_ms=launch_ms + horizon_s * 1000,
                    window_end_ms=launch_ms + (horizon_s + 300) * 1000,
                    collection_end_ms=collection_end,
                    trade_times_ms=trade_times,
                    migration_times_ms=migrations,
                    provider_complete=True,
                )
                records.append({
                    "day": day, "mint": mint, "decision_s": decision_s, "horizon_s": horizon_s,
                    "label_status": label.status.value, "label": 1 if label.status is SurvivalStatus.POSITIVE else (0 if label.status is SurvivalStatus.NEGATIVE else np.nan),
                    "future_trade_count": label.future_trade_count,
                    "age_seconds": decision_s, "log_return_to_decision": log_return,
                    "curve_progress": curve_progress, "buy_volume_sol_raw": float(quote_buy.sum()),
                    "sell_volume_sol_raw": float(quote_sell.sum()), "trade_count_raw": len(before),
                    "unique_buyers_raw": before.loc[before.event_type.eq("BUY"), "wallet"].dropna().astype(str).nunique(),
                    "migration_state": migration_state,
                    "new_buyer_acceleration": len(buyers_recent - buyers_prior) - len(buyers_prior),
                    "buy_volume_acceleration": recent_buy - prior_buy,
                    "sell_pressure": recent_sell / (recent_buy + 1e-9),
                    "trade_size_concentration": concentration,
                })
            exact_candidates = valid_prices.loc[(valid_prices.event_time_ms >= launch_ms + 3_300_000) & (valid_prices.event_time_ms <= launch_ms + 3_900_000)]
            mark_bias.append({
                "mint": mint, "decision_s": decision_s, "early_trades": len(trades.loc[trades.event_time_ms <= decision_ms]),
                "early_buyers": buys.wallet.dropna().astype(str).nunique(),
                "mark_resolved": bool(len(exact_candidates)),
            })
    frame = pd.DataFrame(records)
    bias = pd.DataFrame(mark_bias)
    coverage = {}
    for horizon_s in HORIZONS:
        subset = frame.loc[(frame.decision_s == 600) & (frame.horizon_s == horizon_s)]
        coverage[f"{horizon_s // 60}m"] = {
            "rows": len(subset),
            "positive": int((subset.label_status == "POSITIVE").sum()),
            "negative": int((subset.label_status == "NEGATIVE").sum()),
            "right_censored": int((subset.label_status == "RIGHT_CENSORED").sum()),
            "migration_unknown": int((subset.label_status == "MIGRATION_UNKNOWN").sum()),
            "provider_gap": int((subset.label_status == "PROVIDER_GAP").sum()),
            "binary_rate": float(subset.label.dropna().mean()) if subset.label.notna().any() else None,
        }
    resolved = bias.loc[(bias.decision_s == 600) & bias.mark_resolved]
    unresolved = bias.loc[(bias.decision_s == 600) & ~bias.mark_resolved]
    observability = {
        "resolved_count": len(resolved), "unresolved_count": len(unresolved),
        "resolved_median_early_trades": float(resolved.early_trades.median()) if len(resolved) else None,
        "unresolved_median_early_trades": float(unresolved.early_trades.median()) if len(unresolved) else None,
        "resolved_median_early_buyers": float(resolved.early_buyers.median()) if len(resolved) else None,
        "unresolved_median_early_buyers": float(unresolved.early_buyers.median()) if len(unresolved) else None,
    }
    return frame, {"day": day, "collection_end": datetime.fromtimestamp(collection_end / 1000, UTC).isoformat().replace("+00:00", "Z"), "launches": len(launches), "coverage": coverage, "observability": observability, "event_rows": len(events), "event_mints": int(events.mint.nunique())}


def _matrix(frame: pd.DataFrame, extras: list[str], train_medians: dict | None = None) -> tuple[np.ndarray, dict]:
    columns = ["age_seconds", "log_return_to_decision", "curve_progress", "buy_volume_sol_raw", "sell_volume_sol_raw", "trade_count_raw", "unique_buyers_raw", "migration_state"] + extras
    values = frame[columns].apply(pd.to_numeric, errors="coerce").astype(float)
    medians = train_medians or {column: float(values[column].median()) if values[column].notna().any() else 0.0 for column in columns}
    values = values.fillna(medians)
    means = values.mean()
    scales = values.std(ddof=0).replace(0, 1.0)
    return np.column_stack([np.ones(len(values)), ((values - means) / scales).to_numpy()]), {"columns": columns, "medians": medians, "means": means.to_dict(), "scales": scales.to_dict()}


def _fit_logistic(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        z = np.clip(x @ beta, -30, 30)
        p = 1 / (1 + np.exp(-z))
        loss = -np.sum(y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12)) + 0.1 * np.sum(beta[1:] ** 2)
        grad = x.T @ (p - y)
        grad[1:] += 0.2 * beta[1:]
        return float(loss), grad
    result = minimize(lambda beta: objective(beta), np.zeros(x.shape[1]), jac=True, method="L-BFGS-B")
    if not result.success:
        raise RuntimeError(result.message)
    return result.x


def _metrics(y: np.ndarray, p: np.ndarray) -> dict:
    order = np.argsort(-p)
    ys = y[order]
    positives = max(float(y.sum()), 1.0)
    precision = np.cumsum(ys) / np.arange(1, len(y) + 1)
    ap = float((precision * ys).sum() / positives)
    base = float(y.mean())
    top_n = max(1, len(y) // 5)
    top_rate = float(y[order[:top_n]].mean())
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {"n": len(y), "positive": int(y.sum()), "base_rate": base, "pr_auc_average_precision": ap, "precision_lift_top20pct": top_rate / base if base else None, "brier": float(np.mean((p - y) ** 2)), "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), "mean_predicted": float(p.mean())}


def _cluster_bootstrap(y: np.ndarray, p_a: np.ndarray, p_c: np.ndarray, *, seed: int = 20260901, iterations: int = 1000) -> dict:
    """Resample one primary row per mint; no decision-time pseudoreplication."""
    rng = np.random.default_rng(seed)
    deltas_ap: list[float] = []
    deltas_brier: list[float] = []
    for _ in range(iterations):
        indices = rng.integers(0, len(y), size=len(y))
        a = _metrics(y[indices], p_a[indices])
        c = _metrics(y[indices], p_c[indices])
        deltas_ap.append(c["pr_auc_average_precision"] - a["pr_auc_average_precision"])
        deltas_brier.append(c["brier"] - a["brier"])
    return {
        "iterations": iterations,
        "unit": "token; one 10m decision row per token",
        "pr_auc_delta_mean": float(np.mean(deltas_ap)),
        "pr_auc_delta_ci95": [float(np.quantile(deltas_ap, 0.025)), float(np.quantile(deltas_ap, 0.975))],
        "brier_delta_mean": float(np.mean(deltas_brier)),
        "brier_delta_ci95": [float(np.quantile(deltas_brier, 0.025)), float(np.quantile(deltas_brier, 0.975))],
    }


def model_comparison(frame: pd.DataFrame, *, evaluation_day: str = "2026-08-29") -> dict:
    primary = frame.loc[(frame.decision_s == 600) & (frame.horizon_s == 3600) & frame.label.notna()].copy()
    train = primary.loc[primary.day == "2026-08-28"]
    test = primary.loc[primary.day == evaluation_day]
    if len(train) < 100 or len(test) < 100 or train.label.nunique() < 2 or test.label.nunique() < 2:
        return {"status": "INSUFFICIENT_DATA", "train_rows": len(train), "test_rows": len(test)}
    outputs = {}
    predictions: dict[str, np.ndarray] = {}
    for name, extras in (("A_survival", []), ("C_survival", ["new_buyer_acceleration", "buy_volume_acceleration", "sell_pressure", "trade_size_concentration"])):
        x_train, spec = _matrix(train, extras)
        x_test = train[[]] if False else None
        columns = spec["columns"]
        train_values = train[columns].apply(pd.to_numeric, errors="coerce").astype(float).fillna(spec["medians"])
        test_values = test[columns].apply(pd.to_numeric, errors="coerce").astype(float).fillna(spec["medians"])
        x_test = np.column_stack([np.ones(len(test_values)), ((test_values - pd.Series(spec["means"])) / pd.Series(spec["scales"])).to_numpy()])
        beta = _fit_logistic(x_train, train.label.to_numpy(float))
        pred_train = 1 / (1 + np.exp(-np.clip(x_train @ beta, -30, 30)))
        pred_test = 1 / (1 + np.exp(-np.clip(x_test @ beta, -30, 30)))
        predictions[name] = pred_test
        outputs[name] = {"features": columns, "train": _metrics(train.label.to_numpy(float), pred_train), f"{evaluation_day}_temporal_sanity": _metrics(test.label.to_numpy(float), pred_test)}
    temporal_key = f"{evaluation_day}_temporal_sanity"
    outputs["C_minus_A_test_pr_auc"] = outputs["C_survival"][temporal_key]["pr_auc_average_precision"] - outputs["A_survival"][temporal_key]["pr_auc_average_precision"]
    outputs["C_minus_A_test_brier"] = outputs["C_survival"][temporal_key]["brier"] - outputs["A_survival"][temporal_key]["brier"]
    outputs["cluster_bootstrap"] = _cluster_bootstrap(test.label.to_numpy(float), predictions["A_survival"], predictions["C_survival"])
    outputs["status"] = "PRELIMINARY_TEMPORAL_SANITY"
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day2-events", required=True, type=Path)
    parser.add_argument("--day3-events", required=True, type=Path)
    parser.add_argument("--day3-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    day2, day2_meta = build_rows("2026-08-28", args.day2_events, None)
    day3, day3_meta = build_rows("2026-08-29", args.day3_events, args.day3_manifest)
    frame = pd.concat([day2, day3], ignore_index=True)
    payload = {
        "schema_version": "nave.stage1-audit.v1",
        "days": {"2026-08-28": day2_meta, "2026-08-29": day3_meta},
        "model_comparison": model_comparison(frame),
        "row_contract": {"tokens": int(frame.mint.nunique()), "token_time_horizon_rows": len(frame), "primary_model_rows": int(frame.loc[(frame.decision_s == 600) & (frame.horizon_s == 3600) & frame.label.notna()].shape[0])},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False, default=lambda value: value.item() if hasattr(value, "item") else value) + "\n")
    print(json.dumps({"output": str(args.output), "rows": len(frame), "model_status": payload["model_comparison"].get("status")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
