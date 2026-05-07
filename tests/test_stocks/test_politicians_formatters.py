from __future__ import annotations

from trading.stocks.politicians.formatters import (
    escape_markdown_v2,
    render_politicians_scan_markdown_v2,
)


def _sample_payload() -> dict:
    return {
        "generated_at": "2026-05-06T20:01:00+00:00",
        "new_total": 4,
        "summary": {
            "by_chamber": {"house": 3, "senate": 1},
            "by_type": {"Purchase": 4, "Sale": 0},
            "top_symbols": [
                {"symbol": "NVDA", "count": 2},
                {"symbol": "MSFT", "count": 1},
            ],
            "unique_politicians": 2,
        },
        "new_trades": [
            {
                "chamber": "senate",
                "symbol": "MSFT",
                "politician": "John [Q]",
                "state": "PA",
                "asset_description": "Microsoft Corp.",
                "amount_range": "$50,001 - $100,000",
                "transaction_date": "2026-04-30",
                "disclosure_date": "2026-05-02",
                "link": "https://example.com/filing(1)",
            },
            {
                "chamber": "house",
                "symbol": "NVDA",
                "politician": "Ana_Test",
                "state": "FL",
                "asset_description": "NVIDIA Corp.",
                "amount_range": "$1,001 - $15,000",
                "transaction_date": "2026-04-28",
                "disclosure_date": "2026-05-01",
                "link": "https://example.com/filing2",
            },
            {
                "chamber": "house",
                "symbol": "NVDA",
                "politician": "Ana_Test",
                "state": "FL",
                "asset_description": "NVIDIA Corp.",
                "amount_range": "$1,001 - $15,000",
                "transaction_date": "2026-04-28",
                "disclosure_date": "2026-05-01",
                "link": "https://example.com/filing2",
            },
            {
                "chamber": "house",
                "symbol": "AAPL",
                "politician": "Ana_Test",
                "state": "FL",
                "asset_description": "Apple Inc.",
                "amount_range": "$15,001 - $50,000",
                "transaction_date": "2026-04-27",
                "disclosure_date": "2026-04-30",
                "link": "https://example.com/filing2",
            },
        ],
    }


def test_escape_markdown_v2_escapes_reserved_characters() -> None:
    raw = "A_[b](c)! # + - = | { } ."
    escaped = escape_markdown_v2(raw)
    assert escaped == "A\\_\\[b\\]\\(c\\)\\! \\# \\+ \\- \\= \\| \\{ \\} \\."


def test_render_markdown_groups_and_orders_by_amount() -> None:
    messages = render_politicians_scan_markdown_v2(_sample_payload())
    full = "\n".join(messages)

    assert messages
    assert "*NAVE STOCK Act*" in messages[0]
    assert "John \\[Q\\]" in full
    assert "Ana\\_Test" in full
    assert "x2" in full
    assert "[Fuente](https://example.com/filing\\(1\\))" in full

    # John group carries the highest amount bucket, so it should come first.
    assert full.find("John \\[Q\\]") < full.find("Ana\\_Test")


def test_render_markdown_splits_large_payload_into_parts() -> None:
    payload = _sample_payload()
    extra = []
    for idx in range(70):
        extra.append(
            {
                "chamber": "house",
                "symbol": f"SYM{idx}",
                "politician": f"Member {idx}",
                "state": "TX",
                "asset_description": "Very long synthetic company description for telegram chunk sizing.",
                "amount_range": "$1,001 - $15,000",
                "transaction_date": "2026-04-20",
                "disclosure_date": "2026-05-01",
                "link": f"https://example.com/extra/{idx}",
            }
        )
    payload["new_trades"] = payload["new_trades"] + extra
    payload["new_total"] = len(payload["new_trades"])

    messages = render_politicians_scan_markdown_v2(payload, max_message_chars=500)

    assert len(messages) > 1
    assert all(len(message) <= 500 for message in messages)
    assert messages[0].startswith("*Parte 1/")


def test_render_markdown_empty_payload_behavior() -> None:
    payload = {
        "generated_at": "2026-05-06T20:01:00+00:00",
        "new_total": 0,
        "summary": {},
        "new_trades": [],
    }

    assert render_politicians_scan_markdown_v2(payload) == []
    with_empty = render_politicians_scan_markdown_v2(payload, include_empty=True)
    assert len(with_empty) == 1
    assert "No hay disclosures nuevas" in with_empty[0]
