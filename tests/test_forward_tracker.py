from __future__ import annotations

import json
from datetime import date

from options.forward_tracker import _extract_picks, record_daily_recommendations


def test_extract_picks_gems_and_scan_picks(tmp_path):
    payload = {
        "generated_at": "2026-06-04T12:00:00+00:00",
        "scan": {"days_to_exp": 30},
        "hidden_gems": {
            "gems": [
                {
                    "ticker": "BAC",
                    "strategy": "bull_put_credit_spread",
                    "gem_score": 65.0,
                    "position": {
                        "ticker": "BAC",
                        "strategy": "bull_put_credit_spread",
                        "bias": "bullish",
                        "setup_summary": "sell 1 put 50; buy 1 put 45",
                    },
                }
            ],
            "scan_picks": [
                {
                    "ticker": "V",
                    "strategy": "bull_put_credit_spread",
                    "position": {
                        "ticker": "V",
                        "strategy": "bull_put_credit_spread",
                        "bias": "bullish",
                        "setup_summary": "sell 1 put 310; buy 1 put 305",
                    },
                }
            ],
        },
    }
    rows = _extract_picks(payload, entry_day=date(2026, 6, 4), strategy_index={})
    tickers = {r["ticker"] for r in rows}
    assert tickers >= {"BAC", "V"}


def test_record_daily_recommendations_writes_file(tmp_path):
    payload = {
        "hidden_gems": {
            "gems": [
                {
                    "ticker": "JPM",
                    "strategy": "bull_put_credit_spread",
                    "position": {
                        "ticker": "JPM",
                        "strategy": "bull_put_credit_spread",
                        "bias": "neutral",
                    },
                }
            ],
            "scan_picks": [],
        }
    }
    result = record_daily_recommendations(
        payload,
        entry_day=date(2026, 6, 4),
        tracker_root=tmp_path,
    )
    path = tmp_path / "recommendations_2026-06-04.json"
    assert path.is_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["recommendation_count"] >= 1
    assert result["path"] == str(path)
