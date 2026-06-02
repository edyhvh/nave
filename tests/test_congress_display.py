from __future__ import annotations

from trading.stocks.politicians.display import render_congress_scan


def test_render_congress_scan_no_crash(capsys):
    payload = {
        "generated_at": "2026-06-02T12:00:00+00:00",
        "previous_scan_at": "2026-06-01T08:00:00+00:00",
        "fetched_total": 100,
        "new_total": 1,
        "seen_total_after": 101,
        "new_trades": [
            {
                "chamber": "house",
                "politician": "Jane Doe",
                "symbol": "NVDA",
                "transaction_type": "Purchase",
                "amount_range": "$1,001 - $15,000",
                "transaction_date": "2026-05-28",
                "disclosure_date": "2026-06-01",
            }
        ],
        "summary": {"top_symbols": [{"symbol": "NVDA", "count": 1}]},
    }
    render_congress_scan(payload)
    out = capsys.readouterr().out
    assert "Jane Doe" in out
    assert "NVDA" in out