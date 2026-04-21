from trading.execution import build_execution_plan
from trading.signals import Direction, Signal, Timeframe


def test_signal_keeps_timeframe_metadata():
    signal = Signal(
        coin="ETH",
        direction=Direction.LONG,
        confidence=0.7,
        source="theory/live",
        bias_timeframe=Timeframe.WEEKLY,
        setup_timeframe=Timeframe.H4,
        trigger_timeframe=Timeframe.H1,
        invalidation=2021.0,
        targets=[2321.0],
        metadata={"entry_price": 2121.0},
    )

    assert signal.is_timeframe_aware is True
    assert signal.setup_timeframe == Timeframe.H4
    assert signal.trigger_timeframe == Timeframe.H1
    assert signal.targets == [2321.0]


def test_build_execution_plan_requires_4h_and_1h_contract():
    signal = Signal(
        coin="ETH",
        direction=Direction.LONG,
        confidence=0.7,
        source="theory/live",
        bias_timeframe=Timeframe.WEEKLY,
        setup_timeframe=Timeframe.H4,
        trigger_timeframe=Timeframe.H1,
        invalidation=2021.0,
        targets=[2321.0],
        metadata={"entry_price": 2121.0, "notes": ["await 1H confirmation close"]},
    )

    plan = build_execution_plan(signal)

    assert plan is not None
    assert plan.coin == "ETH"
    assert plan.direction == Direction.LONG
    assert plan.risk_distance == 100.0
    assert plan.targets == [2321.0]
