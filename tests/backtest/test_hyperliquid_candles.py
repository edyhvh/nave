from __future__ import annotations

from trading.client import HyperliquidClient


class FakeCandleClient(HyperliquidClient):
    def __init__(self):
        super().__init__(wallet_name=None, testnet=True)
        self.payloads: list[dict] = []

    def _info(self, payload: dict):
        self.payloads.append(payload)
        req = payload.get("req", {})
        end_time = int(req.get("endTime", 0))

        def row(ts: int) -> dict:
            return {
                "t": ts,
                "T": ts + 3599999,
                "s": "BTC",
                "i": "1h",
                "o": "100.0",
                "h": "110.0",
                "l": "90.0",
                "c": "105.0",
                "v": "12.5",
                "n": 10,
            }

        if end_time > 3000:
            return [row(2000), row(3000)]
        if end_time > 1000:
            return [row(0), row(1000)]
        return []


def test_candle_snapshot_payload_shape():
    client = FakeCandleClient()
    rows = client.get_candle_snapshot("BTC", "1h", 0, 4000)

    assert len(rows) == 2
    assert client.payloads
    payload = client.payloads[0]
    assert payload["type"] == "candleSnapshot"
    assert payload["req"]["coin"] == "BTC"
    assert payload["req"]["interval"] == "1h"


def test_historical_pagination_and_dedup():
    client = FakeCandleClient()
    candles = client.get_historical_candles(
        coin="BTC",
        interval="1h",
        start_time_ms=0,
        end_time_ms=4000,
        max_pages=10,
        throttle_seconds=0,
    )

    timestamps = [c["timestamp_ms"] for c in candles]
    assert timestamps == [0, 1000, 2000, 3000]
    assert len(candles) == 4


def test_invalid_interval_raises_value_error():
    client = FakeCandleClient()
    try:
        client.get_candle_snapshot("BTC", "10h", 0, 1000)
    except ValueError as exc:
        assert "Unsupported interval" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported interval")
