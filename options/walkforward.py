"""Walk-forward validation for per-ticker setup learning."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Mapping

from options.ticker_strategy import INCOME_STRATEGIES, learn_ticker_strategy


def _parse_entry_date(row: Mapping[str, Any]) -> date | None:
    raw = row.get("entry_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _eligible_rows(replay_rows: list[Mapping[str, Any]], ticker: str) -> list[dict[str, Any]]:
    sym = ticker.upper()
    out: list[dict[str, Any]] = []
    for row in replay_rows:
        if str(row.get("ticker") or "").upper() != sym:
            continue
        if row.get("status") not in {"trade_candidate", "directional_override"}:
            continue
        if not row.get("mark"):
            continue
        if not row.get("strategy_name"):
            continue
        if _parse_entry_date(row) is None:
            continue
        out.append(dict(row))
    return out


def _chunk_entry_dates(dates: list[date], n_folds: int) -> list[list[date]]:
    if not dates or n_folds < 2:
        return [dates] if dates else []
    n_folds = min(n_folds, len(dates))
    size = max(1, len(dates) // n_folds)
    chunks: list[list[date]] = []
    for i in range(0, len(dates), size):
        chunk = dates[i : i + size]
        if chunk:
            chunks.append(chunk)
    return chunks


def walkforward_validate(
    replay_rows: list[Mapping[str, Any]],
    ticker: str,
    *,
    n_folds: int = 4,
    min_train_trades: int = 2,
    strategies: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Train on past entry windows, test on the next — per ticker."""
    sym = ticker.upper()
    rows = _eligible_rows(replay_rows, sym)
    if strategies:
        rows = [r for r in rows if str(r.get("strategy_name")) in strategies]
    if len(rows) < min_train_trades + 1:
        return {
            "status": "insufficient_data",
            "ticker": sym,
            "folds": [],
            "oos_win_rate": None,
            "oos_trades": 0,
            "primary_stable": False,
            "narrative": f"{sym}: not enough replay trades for walk-forward ({len(rows)}).",
        }

    by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ed = _parse_entry_date(row)
        if ed:
            by_date[ed].append(row)

    sorted_dates = sorted(by_date.keys())
    chunks = _chunk_entry_dates(sorted_dates, n_folds)
    if len(chunks) < 2:
        return {
            "status": "insufficient_folds",
            "ticker": sym,
            "folds": [],
            "oos_win_rate": None,
            "oos_trades": 0,
            "primary_stable": False,
            "narrative": f"{sym}: need more entry months for walk-forward splits.",
        }

    fold_results: list[dict[str, Any]] = []
    primaries: list[str] = []
    oos_wins = 0
    oos_trades = 0

    for i in range(1, len(chunks)):
        train_dates = set(sorted_dates[: sum(len(c) for c in chunks[:i])])
        test_dates = set(chunks[i])
        train_rows: list[dict[str, Any]] = []
        test_rows: list[dict[str, Any]] = []
        for ed, bucket in by_date.items():
            if ed in train_dates:
                train_rows.extend(bucket)
            elif ed in test_dates:
                test_rows.extend(bucket)

        if len(train_rows) < min_train_trades:
            continue

        last_train = max(train_rows, key=lambda r: _parse_entry_date(r) or date.min)
        bias = str(last_train.get("directional_bias") or "neutral")
        learned = learn_ticker_strategy(
            train_rows,
            sym,
            bias_20d=bias,
            strategies=strategies,
        )
        primary = (learned.get("primary") or {}).get("strategy")
        if not primary:
            continue
        primaries.append(primary)

        matched = [r for r in test_rows if str(r.get("strategy_name")) == primary]
        if not matched:
            fold_results.append(
                {
                    "fold": i,
                    "train_trades": len(train_rows),
                    "test_trades": 0,
                    "primary": primary,
                    "win_rate": None,
                    "note": "no test trades with learned primary",
                }
            )
            continue

        wins = sum(1 for r in matched if r.get("profitable"))
        wr = wins / len(matched)
        oos_wins += wins
        oos_trades += len(matched)
        fold_results.append(
            {
                "fold": i,
                "train_trades": len(train_rows),
                "test_trades": len(matched),
                "primary": primary,
                "win_rate": wr,
                "avg_pnl": sum(
                    float((r.get("mark") or {}).get("pnl_dollars") or 0) for r in matched
                )
                / len(matched),
            }
        )

    oos_wr = oos_wins / oos_trades if oos_trades else None
    stable = len(set(primaries)) <= 1 if primaries else False
    last_primary = primaries[-1] if primaries else None

    narrative_parts = []
    if oos_trades:
        narrative_parts.append(
            f"{sym} walk-forward OOS: {oos_wr:.0%} win on {oos_trades} trades "
            f"using learned primary ({last_primary})."
        )
    else:
        narrative_parts.append(f"{sym}: walk-forward folds ran but no OOS primary trades.")
    if stable and last_primary:
        narrative_parts.append(f" Primary stable across folds: {last_primary}.")
    elif len(set(primaries)) > 1:
        narrative_parts.append(f" Primary shifted across folds: {', '.join(dict.fromkeys(primaries))}.")

    return {
        "status": "ok" if fold_results else "insufficient_folds",
        "ticker": sym,
        "folds": fold_results,
        "oos_win_rate": oos_wr,
        "oos_trades": oos_trades,
        "primary_stable": stable,
        "primaries_seen": list(dict.fromkeys(primaries)),
        "last_primary": last_primary,
        "narrative": " ".join(narrative_parts),
    }


def walkforward_universe_summary(
    replay_rows: list[Mapping[str, Any]],
    tickers: list[str],
    *,
    n_folds: int = 4,
    strategies: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Run walk-forward for many tickers; leaderboard by OOS edge."""
    per_ticker: dict[str, dict[str, Any]] = {}
    for sym in tickers:
        per_ticker[sym] = walkforward_validate(
            replay_rows, sym, n_folds=n_folds, strategies=strategies
        )

    ranked = sorted(
        [
            {
                "ticker": sym,
                "oos_win_rate": block.get("oos_win_rate"),
                "oos_trades": block.get("oos_trades") or 0,
                "primary_stable": block.get("primary_stable"),
                "last_primary": block.get("last_primary"),
            }
            for sym, block in per_ticker.items()
            if (block.get("oos_trades") or 0) > 0
        ],
        key=lambda x: (x["oos_win_rate"] or 0, x["oos_trades"]),
        reverse=True,
    )

    return {
        "tickers_evaluated": len(tickers),
        "with_oos_trades": len(ranked),
        "per_ticker": per_ticker,
        "leaderboard": ranked[:20],
    }