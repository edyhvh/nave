import json

from research.memecoin.pumpapi_agreement import compare_events
from research.memecoin.pumpapi_replay import iter_normalized_events, normalize_event, summarize_events


def test_normalize_current_event_preserves_event_and_provider_times():
    event = normalize_event({
        "action": "buy",
        "mint": "mint",
        "timestamp": 1_756_000_000_000,
        "localTimestamp": 1_756_000_000_100,
        "signature": "sig",
        "txSigner": "wallet",
        "quoteAmount": 1.5,
        "pool": "pump",
    })
    assert event["event_time"] != event["provider_received_at"]
    assert event["available_at"] == event["provider_received_at"]
    assert event["side"] == "buy"
    assert event["quality_flags"] == []


def test_normalize_legacy_aliases_and_missingness_are_explicit():
    event = normalize_event({"txType": "sell", "mint": "mint", "timestamp": 1_756_000_000, "solAmount": "2"})
    assert event["event_type"] == "SELL"
    assert event["quote_amount"] == 2.0
    assert "LEGACY_SCHEMA" in event["quality_flags"]
    assert "MISSING_SIGNATURE" in event["quality_flags"]


def test_jsonl_iterator_is_incremental_and_summary_is_compact():
    lines = [json.dumps({"action": "create", "mint": "m", "timestamp": 1_756_000_000_000}).encode(), b"not-json"]
    events = list(iter_normalized_events(lines[:1]))
    assert len(events) == 1
    summary = summarize_events(events)
    assert summary["rows"] == 1
    assert summary["event_types"] == {"CREATE": 1}


def test_breakdown_trader_is_used_and_ambiguous_breakdown_is_unknown():
    event = normalize_event({
        "signature": "sig",
        "action": "buy",
        "mint": "mint",
        "txSigner": "payer",
        "breakdown": [{"trader": "actor", "action": "buy"}],
        "timestamp": 1_000,
        "localTimestamp": 1_001,
        "quoteAmount": 1,
    })
    assert event["wallet"] == "actor"
    assert "AMBIGUOUS_PARTICIPANT" not in event["quality_flags"]
    ambiguous = normalize_event({**event, "breakdown": [{"trader": "a"}, {"trader": "b"}]})
    assert ambiguous["wallet"] is None
    assert "AMBIGUOUS_PARTICIPANT" in ambiguous["quality_flags"]


def test_agreement_maps_create_to_dune_buy_and_tracks_missingness():
    result = compare_events(
        [
            {
                "event_time": "2026-08-28 21:00:00.000 UTC",
                "mint": "mint",
                "transaction": "sig",
                "wallet": "actor",
                "side": "buy",
                "token_amount": 2,
                "quote_amount_sol": 1,
                "real_quote_reserves_sol": 3,
                "real_token_reserves": 4,
            },
            {"transaction": "missing", "event_time": "2026-08-28 21:00:01.000 UTC"},
        ],
        [
            {
                "event_type": "CREATE",
                "event_time_ms": 1_787_950_800_000,
                "tx_signature": "sig",
                "mint": "mint",
                "wallet": "actor",
                "token_amount": None,
                "quote_amount": 1,
                "real_quote_reserves": 3,
                "real_token_reserves": 4,
            }
        ],
    )
    assert result["counts"]["signature_matched"] == 1
    assert result["counts"]["missing_in_pumpapi"] == 1
    assert result["counts"]["known_create_as_buy"] == 1
    assert result["counts"]["wallet_exact"] == 1
