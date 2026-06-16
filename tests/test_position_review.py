from __future__ import annotations

from unittest.mock import MagicMock, patch

from trading.crypto.analysis import review_positions


def test_review_positions_enter_when_momentum_tradeable_and_cot_aligned():
    momentum_payload = {
        "summary": {"tradeable_count": 1, "confirmed_count": 1},
        "results": {
            "BTCUSDT": {
                "plans": [],
                "tradeable": [
                    {
                        "side": "short",
                        "tradeable": True,
                        "confidence_score": 87,
                        "setup_status": "confirmed",
                        "entry_zone": [70000.0, 71000.0],
                        "invalidation": 72000.0,
                        "tp1": 68000.0,
                        "tp2": 66000.0,
                        "tp3": 64000.0,
                        "diagnostics": {"cot_overlay": {"aligned": True}},
                    }
                ],
            }
        },
    }
    cot_bias = MagicMock(bias="bearish", confidence=0.65, historical_percentile=97, bias_label="BEARISH")
    theory_decision = MagicMock(
        coin="BTC",
        stage="weekly",
        reason="neutral",
        signal=None,
        daily_confirmed=False,
        setup_valid=False,
    )

    empty_daily = MagicMock()
    empty_daily.empty = True
    with patch("trading.crypto.analysis.review.MomentumMarketService") as mock_svc:
        mock_svc.return_value.parse_timeframes.return_value = MagicMock()
        mock_svc.return_value.scan_live.return_value = momentum_payload
        mock_svc.return_value.load_live_frames.return_value = {
            "daily": empty_daily,
            "setup": empty_daily,
            "trigger": empty_daily,
        }
        with patch("trading.crypto.analysis.review.fetch_cot_biases", return_value={"BTC": cot_bias}):
            with patch(
                "trading.crypto.analysis.review.build_signals_for_coins",
                return_value=([], [theory_decision]),
            ):
                with patch("trading.crypto.analysis.review.assess_regime") as mock_regime:
                    mock_regime.return_value = MagicMock(
                        phase="continuation_short",
                        bias="bearish",
                        confidence=0.8,
                        playbook="test",
                        supply_zone=None,
                        continuation_trigger=None,
                        metrics={},
                        to_dict=lambda: {"phase": "continuation_short"},
                    )
                    payload = review_positions(["BTC"], include_options=False)

    rec = payload["recommendations"][0]
    assert rec["action"] == "enter"
    assert rec["direction"] == "short"
    assert rec["primary_source"] == "momentum+cot+regime"


def test_review_backfills_primary_execution_from_matching_secondary():
    momentum_payload = {
        "summary": {"tradeable_count": 0, "confirmed_count": 0},
        "results": {"BTCUSDT": {"plans": [], "tradeable": []}},
    }
    cot_bias = MagicMock(bias="bearish", confidence=0.72, historical_percentile=50, bias_label="BEARISH")
    theory_decision = MagicMock(
        coin="BTC",
        stage="daily",
        reason="daily does not confirm weekly bias",
        signal=None,
        daily_confirmed=False,
        setup_valid=False,
    )
    empty_daily = MagicMock()
    empty_daily.empty = True
    secondary = [
        {
            "kind": "relief_rally_fade",
            "direction": "short",
            "action": "watch",
            "confidence": 0.72,
            "playbook": "Fade relief rally",
            "entry_zone": [64796.0, 76610.0],
            "invalidation": 78142.0,
            "targets": [63767.0, 61795.0],
            "reasons": [],
            "blockers": [],
        },
        {
            "kind": "forming_short",
            "direction": "short",
            "action": "watch",
            "confidence": 0.72,
            "playbook": "Short forming",
            "entry_zone": [64000.0, 65000.0],
            "invalidation": 66000.0,
            "targets": [62000.0],
            "reasons": [],
            "blockers": [],
        },
    ]

    with patch("trading.crypto.analysis.review.MomentumMarketService") as mock_svc:
        mock_svc.return_value.parse_timeframes.return_value = MagicMock()
        mock_svc.return_value.scan_live.return_value = momentum_payload
        mock_svc.return_value.load_live_frames.return_value = {
            "daily": empty_daily,
            "setup": empty_daily,
            "trigger": empty_daily,
        }
        with patch("trading.crypto.analysis.review.fetch_cot_biases", return_value={"BTC": cot_bias}):
            with patch(
                "trading.crypto.analysis.review.build_signals_for_coins",
                return_value=([], [theory_decision]),
            ):
                with patch("trading.crypto.analysis.review.assess_regime") as mock_regime:
                    mock_regime.return_value = MagicMock(
                        phase="relief_rally_fade",
                        bias="bearish",
                        confidence=0.72,
                        playbook="fade relief rally",
                        supply_zone=[64796.0, 76610.0],
                        continuation_trigger="1H rejection",
                        metrics={},
                        to_dict=lambda: {"phase": "relief_rally_fade"},
                    )
                    with patch(
                        "trading.crypto.analysis.review.detect_secondary_opportunities",
                        return_value=secondary,
                    ):
                        payload = review_positions(["BTC"], include_options=False)

    rec = payload["recommendations"][0]
    assert rec["action"] == "watch"
    assert rec["invalidation"] == 78142.0
    assert rec["targets"] == [63767.0, 61795.0]
    assert rec["secondary_opportunities"] == [secondary[1]]
    assert rec["market_context"]["cot_percentile"] == 50