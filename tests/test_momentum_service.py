from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import Mock

from trading.crypto.momentum import load_momentum_config
from trading.crypto.momentum.service import MomentumMarketService, MomentumTimeframes, build_cadence_policy


@dataclass(frozen=True)
class _FakePlan:
    setup_status: str
    tradeable: bool
    confidence_score: int

    def to_dict(self) -> dict[str, object]:
        return {
            "setup_status": self.setup_status,
            "tradeable": self.tradeable,
            "confidence_score": self.confidence_score,
        }


@dataclass(frozen=True)
class _FakeResponse:
    payload: object

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def test_build_cadence_policy_flags_quiet_market() -> None:
    cadence = load_momentum_config().cadence
    results = {
        "BTCUSDT": {
            "plans": [
                {
                    "setup_status": "pending",
                    "tradeable": False,
                    "confidence_score": 84,
                }
            ]
        }
    }

    policy = build_cadence_policy(results, base_threshold=90, cadence=cadence)

    assert policy["state"] == "quiet"
    assert policy["recommended_threshold"] == 93
    assert policy["target_trade_count_range"] == [0, 3]


def test_build_cadence_policy_flags_expansion_market() -> None:
    cadence = load_momentum_config().cadence
    results = {
        "BTCUSDT": {
            "plans": [
                {
                    "setup_status": "confirmed",
                    "tradeable": True,
                    "confidence_score": 93,
                },
                {
                    "setup_status": "confirmed",
                    "tradeable": True,
                    "confidence_score": 91,
                },
            ]
        },
        "ETHUSDT": {
            "plans": [
                {
                    "setup_status": "confirmed",
                    "tradeable": True,
                    "confidence_score": 92,
                }
            ]
        },
    }

    policy = build_cadence_policy(results, base_threshold=90, cadence=cadence)

    assert policy["state"] == "expansion"
    assert policy["recommended_threshold"] == 88
    assert policy["target_trade_count_range"] == [3, 6]
    assert policy["breadth"]["symbols_with_tradeable"] == 2


def test_scan_live_can_apply_cadence_recommended_threshold(monkeypatch) -> None:
    service = MomentumMarketService(market_client=cast(Any, object()))
    monkeypatch.setattr(service, "load_live_frames", lambda symbol, timeframes: {"daily": None, "setup": None, "trigger": None})

    def fake_evaluate_symbol(**kwargs):
        if kwargs["symbol"] == "BTCUSDT":
            return [
                _FakePlan(setup_status="confirmed", tradeable=True, confidence_score=93),
                _FakePlan(setup_status="confirmed", tradeable=True, confidence_score=91),
            ]
        return [
            _FakePlan(setup_status="confirmed", tradeable=True, confidence_score=90),
            _FakePlan(setup_status="confirmed", tradeable=True, confidence_score=89),
        ]

    monkeypatch.setattr(service.engine, "evaluate_symbol", fake_evaluate_symbol)
    timeframes = MomentumTimeframes(bias="1d", setup="4h", trigger="1h")

    base_payload = service.scan_live(symbols=["BTCUSDT", "ETHUSDT"], timeframes=timeframes, score_threshold=90)
    adaptive_payload = service.scan_live(
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframes=timeframes,
        score_threshold=90,
        apply_cadence_policy=True,
    )

    assert base_payload["summary"]["tradeable_count"] == 3
    assert base_payload["summary"]["effective_score_threshold"] == 90
    assert adaptive_payload["summary"]["tradeable_count"] == 4
    assert adaptive_payload["summary"]["effective_score_threshold"] == 88
    assert adaptive_payload["cadence"]["applied"] is True


def test_fetch_funding_rate_returns_none_for_malformed_numeric_value() -> None:
    session = Mock()
    session.get.return_value = _FakeResponse({"lastFundingRate": "bad-value"})
    service = MomentumMarketService(market_client=cast(Any, object()), session=cast(Any, session))

    assert service.fetch_funding_rate("BTCUSDT") is None


def test_fetch_open_interest_history_returns_none_for_malformed_payload_entry() -> None:
    session = Mock()
    session.get.return_value = _FakeResponse([
        {"timestamp": "bad-timestamp", "sumOpenInterest": "oops"},
    ])
    service = MomentumMarketService(market_client=cast(Any, object()), session=cast(Any, session))

    assert service.fetch_open_interest_history("BTCUSDT", "4h") is None