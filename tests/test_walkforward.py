"""Walk-forward per-ticker validation tests."""

from __future__ import annotations

from options.walkforward import walkforward_validate


def _mk(
    ticker: str,
    entry: str,
    strategy: str,
    *,
    profitable: bool,
    pnl: float,
) -> dict:
    return {
        "ticker": ticker,
        "status": "trade_candidate",
        "strategy_name": strategy,
        "entry_date": entry,
        "directional_bias": "neutral",
        "profitable": profitable,
        "mark": {"pnl_dollars": pnl},
        "entry_metrics": {"pop": 70.0, "probability_of_touch": 50.0},
    }


def test_walkforward_produces_oos_folds() -> None:
    rows = []
    for month, win in [
        ("2025-01-01", True),
        ("2025-02-01", True),
        ("2025-03-01", False),
        ("2025-04-01", True),
        ("2025-05-01", True),
        ("2025-06-01", True),
        ("2025-07-01", False),
        ("2025-08-01", True),
    ]:
        rows.append(
            _mk(
                "WFC",
                month,
                "bull_put_credit_spread",
                profitable=win,
                pnl=20.0 if win else -30.0,
            )
        )
    wf = walkforward_validate(rows, "WFC", n_folds=4, min_train_trades=2)
    assert wf["status"] == "ok"
    assert wf.get("oos_trades", 0) >= 0
    assert "folds" in wf