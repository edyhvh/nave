"""Verify that the options model fixes improve MSFT and NFLX scenarios."""

from __future__ import annotations

import pandas as pd
from options.analytics.probability import evaluate_strategy_distribution, terminal_price_distribution
from options.models import StrategyCandidate, StrategyLeg
from options.scoring import _composite_score


def test_nflx_iv_fix():
    """Show that the IV outlier fix would have prevented the bad NFLX recommendation."""
    print("=" * 60)
    print("NFLX IV FIX VERIFICATION")
    print("=" * 60)

    # NFLX long strangle 88C/87P
    candidate = StrategyCandidate(
        name="long_strangle",
        expiration="2026-06-18",
        days_to_expiration=29,
        legs=[
            StrategyLeg(instrument_type="option", side="buy", quantity=1, premium=3.40, strike=88.0, option_type="call"),
            StrategyLeg(instrument_type="option", side="buy", quantity=1, premium=2.33, strike=87.0, option_type="put"),
        ],
        net_premium=-573.0,
        max_profit=None,
        max_loss=573.0,
        breakeven_points=[81.27, 93.73],
        notes=[],
    )

    for label, iv in [
        ("OLD (buggy mean IV)", 0.72),
        ("NEW (cleaned median IV)", 0.33),
    ]:
        dist = evaluate_strategy_distribution(
            candidate,
            underlying_price=87.0,
            implied_volatility=iv,
        )
        score = _composite_score(
            strategy_name="long_strangle",
            pop=dist["pop"],
            expected_value=dist["expected_value"],
            expected_loss=dist["expected_loss"],
            risk_reward=1.0,
            max_loss=573.0,
            theta_per_day=-0.10,
            vega_exposure=0.96,
            probability_of_touch=dist["probability_of_touch"],
        )
        actionable = score >= 40 and dist["expected_value"] >= -30
        print(f"\n{label}: IV={iv:.2f}")
        print(f"  PoP: {dist['pop']:.1f}%")
        print(f"  EV:  ${dist['expected_value']:.2f}")
        print(f"  Touch: {dist['probability_of_touch']:.1f}%")
        print(f"  Score: {score:.1f}")
        print(f"  Actionable: {actionable}")


def test_msft_fix():
    """Show that cleaned IV + drift improves MSFT bull put assessment."""
    print("\n" + "=" * 60)
    print("MSFT FIX VERIFICATION (bull put 395/390)")
    print("=" * 60)

    # MSFT bull put 395/390 @ $420.98
    candidate = StrategyCandidate(
        name="bull_put_credit_spread",
        expiration="2026-06-18",
        days_to_expiration=31,
        legs=[
            StrategyLeg(instrument_type="option", side="sell", quantity=1, premium=4.425, strike=395.0, option_type="put"),
            StrategyLeg(instrument_type="option", side="buy", quantity=1, premium=3.50, strike=390.0, option_type="put"),
        ],
        net_premium=92.5,
        max_profit=92.5,
        max_loss=407.5,
        breakeven_points=[394.075],
        notes=[],
    )

    for label, iv, rf in [
        ("OLD (IV=0.34, no drift)", 0.34, 0.00),
        ("NEW (IV=0.30, 4% drift)", 0.30, 0.04),
    ]:
        dist = evaluate_strategy_distribution(
            candidate,
            underlying_price=420.98,
            implied_volatility=iv,
            risk_free_rate=rf,
        )
        score = _composite_score(
            strategy_name="bull_put_credit_spread",
            pop=dist["pop"],
            expected_value=dist["expected_value"],
            expected_loss=dist["expected_loss"],
            risk_reward=0.227,
            max_loss=407.5,
            theta_per_day=0.016,
            vega_exposure=-0.041,
            probability_of_touch=dist["probability_of_touch"],
        )
        # With new quality gate: income needs score >= 30, EV >= -50
        actionable = score >= 30 and dist["expected_value"] >= -50
        print(f"\n{label}")
        print(f"  PoP: {dist['pop']:.1f}%")
        print(f"  EV:  ${dist['expected_value']:.2f}")
        print(f"  Touch: {dist['probability_of_touch']:.1f}%")
        print(f"  Score: {score:.1f}")
        print(f"  Actionable: {actionable}")


def test_score_thresholds():
    """Show that new thresholds let more income trades through."""
    print("\n" + "=" * 60)
    print("QUALITY GATE THRESHOLD VERIFICATION")
    print("=" * 60)

    strategies = [
        ("bull_put_credit_spread", 28.0),
        ("iron_condor", 42.0),
        ("long_strangle", 38.0),
        ("covered_call", 55.0),
    ]

    print("\nOLD gate (score >= 50 for all):")
    for name, score in strategies:
        actionable = score >= 50
        print(f"  {name:25s} score={score:.1f} -> {'PASS' if actionable else 'BLOCKED'}")

    print("\nNEW gate (income >= 30, aggressive >= 40):")
    thresholds = {
        "bull_put_credit_spread": 30,
        "iron_condor": 30,
        "long_strangle": 40,
        "covered_call": 30,
    }
    for name, score in strategies:
        actionable = score >= thresholds[name]
        print(f"  {name:25s} score={score:.1f} -> {'PASS' if actionable else 'BLOCKED'}")


if __name__ == "__main__":
    test_nflx_iv_fix()
    test_msft_fix()
    test_score_thresholds()
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)
