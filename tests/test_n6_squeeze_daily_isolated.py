"""Verify N6 modules import and the isolated path is wired correctly."""


def test_n6_squeeze_daily_imports():
    from trading.crypto.analysis.squeeze_daily import SqueezeDailyState, detect_squeeze_daily
    assert SqueezeDailyState is not None
    assert callable(detect_squeeze_daily)


def test_engine_has_n6_method():
    from trading.crypto.theory_v2 import TheoryV2Engine
    assert hasattr(TheoryV2Engine, "evaluate_squeeze_daily")


def test_squeeze_daily_self_contained():
    """The isolated N6 module must NOT *import* from the N5 weekly detector."""
    import sys
    import trading.crypto.analysis.squeeze_daily as sd
    # The module has exactly one runtime import (pandas); it must not import
    # trading.crypto.analysis.squeeze_detector at runtime or via the package.
    import_paths = [m for m in ("squeeze_detector", "trading.crypto.analysis.squeeze_detector")
                    if m in (sys.modules or {})]
    assert not import_paths, f"N6 must not import N5 squeeze_detector: {import_paths}"
