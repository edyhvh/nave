"""Shared BTC/ETH analysis constants — single source for phases and gating."""

from __future__ import annotations

BEARISH_REGIME_PHASES = frozenset({
    "relief_rally_fade",
    "leg_down",
    "breakdown_retest",
    "continuation_short",
    "cot_bear_bias",
    "failed_impulse_short",
})

BULLISH_REGIME_PHASES = frozenset({
    "pullback_buy",
    "leg_up",
    "breakout_retest_long",
    "continuation_long",
    "cot_bull_bias",
    "failed_impulse_long",
})

DIRECTIONAL_REGIME_PHASES = BEARISH_REGIME_PHASES | BULLISH_REGIME_PHASES

# Options scan: allow COT+regime bias without tradeable perp when macro phase is clear
REGIME_OPTIONS_WITHOUT_TRADEABLE = BEARISH_REGIME_PHASES | frozenset({
    "pullback_buy",
    "leg_up",
    "cot_bull_bias",
    "breakout_retest_long",
})

OPTIONS_BY_BIAS: dict[str, list[str]] = {
    "bearish": [
        "bear_put_debit_spread",
        "bear_call_credit_spread",
        "long_put",
    ],
    "bullish": [
        "bull_call_debit_spread",
        "bull_put_credit_spread",
        "long_call",
    ],
}

PERP_INSTRUMENT = "hyperliquid_perp"
OPTIONS_INSTRUMENT = "deribit_options"