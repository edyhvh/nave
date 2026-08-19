import pytest

from trading.stocks.event_journal import (
    JournalCorruptError,
    list_events,
    mark_event,
    record_politician_trades,
)


def test_material_event_survives_and_can_be_marked(tmp_path) -> None:
    path = tmp_path / "events.json"
    rows = record_politician_trades(
        [
            {
                "symbol": "MRNA",
                "politician": "Trump Portfolio",
                "transaction_type": "Purchase",
                "amount_range": "$50,001 - $100,000",
                "transaction_date": "2026-03-10",
                "disclosure_date": "2026-03-20",
                "link": "https://example.test/mrna-march",
            }
        ],
        path=path,
    )
    assert rows[0]["importance"] == "high"
    assert rows[0]["status"] == "new"
    event_id = rows[0]["event_id"]

    listed = list_events(path=path)
    assert listed[0]["ticker"] == "MRNA"
    assert listed[0]["event_date"] == "2026-03-10"

    marked = mark_event(event_id, status="watching", note="Revisar performance y tesis", path=path)
    assert marked["status"] == "watching"
    assert marked["review_count"] == 1
    assert list_events(status="watching", path=path)[0]["event_id"] == event_id


def test_duplicate_event_is_idempotent(tmp_path) -> None:
    path = tmp_path / "events.json"
    trade = {
        "symbol": "MSFT",
        "transaction_type": "Purchase",
        "amount_range": "$1,001 - $15,000",
        "transaction_date": "2026-03-10",
        "link": "https://example.test/msft",
    }
    record_politician_trades([trade], path=path)
    record_politician_trades([trade], path=path)
    assert len(list_events(path=path)) == 1


def test_corrupt_event_journal_fails_closed(tmp_path) -> None:
    path = tmp_path / "events.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(JournalCorruptError):
        record_politician_trades(
            [
                {
                    "symbol": "MSFT",
                    "transaction_type": "Purchase",
                    "amount_range": "$1,001 - $15,000",
                    "transaction_date": "2026-03-10",
                    "link": "https://example.test/msft",
                }
            ],
            path=path,
        )


def test_reviewed_event_status_is_preserved_on_upsert(tmp_path) -> None:
    path = tmp_path / "events.json"
    trade = {
        "symbol": "MSFT",
        "transaction_type": "Purchase",
        "amount_range": "$1,001 - $15,000",
        "transaction_date": "2026-03-10",
        "link": "https://example.test/msft",
    }
    row = record_politician_trades([trade], path=path)[0]
    mark_event(row["event_id"], status="closed", path=path)
    updated = record_politician_trades([trade], path=path)[0]
    assert updated["status"] == "closed"


def test_distinct_trades_in_one_filing_are_preserved(tmp_path) -> None:
    path = tmp_path / "events.json"
    trades = [
        {
            "symbol": "MSFT",
            "politician": "P",
            "transaction_type": "Purchase",
            "amount_range": "$1,001 - $15,000",
            "transaction_date": "2026-03-10",
            "disclosure_date": "2026-03-20",
            "link": "https://example.test/filing",
        },
        {
            "symbol": "MSFT",
            "politician": "P",
            "transaction_type": "Sale",
            "amount_range": "$15,001 - $50,000",
            "transaction_date": "2026-03-10",
            "disclosure_date": "2026-03-20",
            "link": "https://example.test/filing",
        },
    ]

    record_politician_trades(trades, path=path)

    events = list_events(path=path)
    assert len(events) == 2
    assert {event["event_type"] for event in events} == {"purchase", "sale"}
