from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import Mock

import pandas as pd

from trading.crypto.momentum import load_momentum_config
from trading.crypto.momentum.service import MomentumMarketService, MomentumTimeframes, build_cadence_policy
from trading.crypto.momentum.thesis import MomentumThesisStore


@dataclass(frozen=True)
class _FakePlan:
    setup_status: str
    tradeable: bool
    confidence_score: int
    side: str = "long"
    entry_zone: tuple[float, float] = (100.0, 101.0)
    invalidation: float = 95.0
    tp1: float = 104.0
    tp2: float = 108.0
    tp3: float = 112.0
    rr_estimated: float = 2.0

    def to_dict(self) -> dict[str, object]:
        return {
            "setup_status": self.setup_status,
            "tradeable": self.tradeable,
            "confidence_score": self.confidence_score,
            "side": self.side,
            "entry_zone": list(self.entry_zone),
            "invalidation": self.invalidation,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "rr_estimated": self.rr_estimated,
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


def test_scan_live_can_apply_cadence_recommended_threshold(monkeypatch, tmp_path) -> None:
    service = MomentumMarketService(
        market_client=cast(Any, object()),
        thesis_store=MomentumThesisStore(path=tmp_path / "theses.json"),
    )
    monkeypatch.setattr(service, "load_live_frames", lambda symbol, timeframes: {"daily": None, "setup": None, "trigger": None})

    def fake_evaluate_symbol(**kwargs):
        if kwargs["symbol"] == "BTCUSDT":
            return [
                _FakePlan(setup_status="confirmed", tradeable=True, confidence_score=93),
                _FakePlan(setup_status="confirmed", tradeable=True, confidence_score=91, side="short", entry_zone=(98.0, 99.0), invalidation=104.0, tp2=90.0),
            ]
        return [
            _FakePlan(setup_status="confirmed", tradeable=True, confidence_score=90),
            _FakePlan(setup_status="confirmed", tradeable=True, confidence_score=89, side="short", entry_zone=(98.0, 99.0), invalidation=104.0, tp2=90.0),
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


def test_scan_live_freezes_active_thesis_when_fresh_scan_drifts(monkeypatch, tmp_path) -> None:
    service = MomentumMarketService(
        market_client=cast(Any, object()),
        thesis_store=MomentumThesisStore(path=tmp_path / "theses.json"),
    )
    timeframes = MomentumTimeframes(bias="1d", setup="4h", trigger="1h")
    trigger = pd.DataFrame({"close": [102.0]})
    monkeypatch.setattr(
        service,
        "load_live_frames",
        lambda symbol, timeframes: {"daily": None, "setup": None, "trigger": trigger},
    )
    calls = {"count": 0}

    def fake_evaluate_symbol(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return [
                _FakePlan(
                    setup_status="confirmed",
                    tradeable=True,
                    confidence_score=91,
                    entry_zone=(100.0, 101.0),
                    invalidation=95.0,
                    tp2=108.0,
                )
            ]
        return [
            _FakePlan(
                setup_status="confirmed",
                tradeable=True,
                confidence_score=92,
                entry_zone=(110.0, 111.0),
                invalidation=106.0,
                tp2=118.0,
            )
        ]

    monkeypatch.setattr(service.engine, "evaluate_symbol", fake_evaluate_symbol)

    first = service.scan_live(symbols=["BTCUSDT"], timeframes=timeframes, score_threshold=90)
    second = service.scan_live(symbols=["BTCUSDT"], timeframes=timeframes, score_threshold=90)

    first_plan = first["results"]["BTCUSDT"]["tradeable"][0]
    second_plan = second["results"]["BTCUSDT"]["tradeable"][0]
    assert first_plan["entry_zone"] == [100.0, 101.0]
    assert second_plan["entry_zone"] == [100.0, 101.0]
    assert second_plan["invalidation"] == 95.0
    assert second_plan["tp2"] == 108.0
    assert second_plan["scan_plan"]["entry_zone"] == [110.0, 111.0]
    assert second_plan["thesis_status"] == "holding_previous"


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
