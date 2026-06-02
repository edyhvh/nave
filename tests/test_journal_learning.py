"""Journal → replay row conversion tests."""

from __future__ import annotations

from options.journal_learning import manual_trade_to_replay_row


def test_manual_trade_to_replay_row() -> None:
    row = manual_trade_to_replay_row(
        {
            "market_type": "options",
            "asset": "WFC",
            "setup": "bull_put",
            "entry_price": 100.0,
            "take_profit_final_price": 110.0,
            "side": "long",
            "status": "closed",
            "date_created": "2026-01-15T12:00:00",
        }
    )
    assert row is not None
    assert row["ticker"] == "WFC"
    assert row["strategy_name"] == "bull_put_credit_spread"
    assert row["profitable"] is True