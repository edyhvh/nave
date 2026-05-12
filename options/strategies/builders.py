"""Generate options strategy candidates from a normalized option chain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from options.config import OptionsConfig, load_options_config
from options.models import StrategyCandidate, StrategyLeg


@dataclass(frozen=True)
class _ChainSlice:
    expiration: str
    dte: int
    calls: pd.DataFrame
    puts: pd.DataFrame


def _days_to_expiration(expiration: str) -> int:
    exp_date = datetime.fromisoformat(expiration).date()
    now_date = datetime.now(timezone.utc).date()
    return max(1, (exp_date - now_date).days)


def _nearest_expiration(frame: pd.DataFrame, target_dte: int) -> _ChainSlice | None:
    if frame.empty:
        return None

    expirations = sorted(frame["expiration"].dropna().unique().tolist())
    if not expirations:
        return None

    pairs: list[tuple[str, int]] = [
        (exp, _days_to_expiration(exp)) for exp in expirations]
    selected, dte = min(pairs, key=lambda item: abs(item[1] - target_dte))
    expiry_frame = frame[frame["expiration"] == selected]
    calls = expiry_frame[expiry_frame["option_type"]
                         == "call"].sort_values("strike")
    puts = expiry_frame[expiry_frame["option_type"]
                        == "put"].sort_values("strike")
    if calls.empty or puts.empty:
        return None
    return _ChainSlice(expiration=selected, dte=dte, calls=calls, puts=puts)


def _nearest_strike_row(side: pd.DataFrame, *, underlying_price: float) -> pd.Series | None:
    if side.empty:
        return None
    ordered = side.reset_index(drop=True)
    idx = int((ordered["strike"] - underlying_price).abs().idxmin())
    if idx < 0 or idx >= len(ordered):
        return None
    return ordered.iloc[idx]


def _row_by_offset(side: pd.DataFrame, *, strike: float, offset: int) -> pd.Series | None:
    if side.empty:
        return None
    ordered = side.sort_values("strike").reset_index(drop=True)
    matches = ordered.index[ordered["strike"] == strike].tolist()
    if not matches:
        idx = int((ordered["strike"] - strike).abs().idxmin())
    else:
        idx = matches[0]
    target = idx + offset
    if target < 0 or target >= len(ordered):
        return None
    return ordered.iloc[target]


def _row_nearest_to_strike(
    side: pd.DataFrame,
    *,
    target_strike: float,
    strike_min: float | None = None,
    strike_max: float | None = None,
) -> pd.Series | None:
    if side.empty:
        return None

    filtered = side
    if strike_min is not None:
        filtered = filtered[filtered["strike"] >= strike_min]
    if strike_max is not None:
        filtered = filtered[filtered["strike"] <= strike_max]
    if filtered.empty:
        return None

    ordered = filtered.reset_index(drop=True)
    idx = int((ordered["strike"] - target_strike).abs().idxmin())
    if idx < 0 or idx >= len(ordered):
        return None
    return ordered.iloc[idx]


def _option_leg(row: pd.Series, *, side: str, quantity: int) -> StrategyLeg:
    return StrategyLeg(
        instrument_type="option",
        side=side,
        quantity=quantity,
        premium=float(row["mid_price"]),
        strike=float(row["strike"]),
        option_type=str(row["option_type"]),
    )


def _stock_leg(*, side: str, quantity: int, price: float) -> StrategyLeg:
    return StrategyLeg(
        instrument_type="stock",
        side=side,
        quantity=quantity,
        premium=price,
    )


def _build_covered_call(chain: _ChainSlice, *, underlying_price: float) -> StrategyCandidate | None:
    atm_call = _nearest_strike_row(
        chain.calls, underlying_price=underlying_price)
    if atm_call is None:
        return None
    premium = float(atm_call["mid_price"])
    strike = float(atm_call["strike"])
    legs = [
        _stock_leg(side="buy", quantity=100, price=underlying_price),
        _option_leg(atm_call, side="sell", quantity=1),
    ]
    max_profit = (strike - underlying_price) * 100.0 + premium * 100.0
    max_loss = max(0.0, (underlying_price - premium) * 100.0)
    return StrategyCandidate(
        name="covered_call",
        expiration=chain.expiration,
        days_to_expiration=chain.dte,
        legs=legs,
        net_premium=premium * 100.0,
        max_profit=max_profit,
        max_loss=max_loss,
        breakeven_points=[underlying_price - premium],
        notes=["Long 100 shares, short 1 call near ATM."],
    )


def _build_cash_secured_put(chain: _ChainSlice, *, underlying_price: float) -> StrategyCandidate | None:
    atm_put = _nearest_strike_row(
        chain.puts, underlying_price=underlying_price)
    if atm_put is None:
        return None
    premium = float(atm_put["mid_price"])
    strike = float(atm_put["strike"])
    max_profit = premium * 100.0
    max_loss = max(0.0, (strike - premium) * 100.0)
    return StrategyCandidate(
        name="cash_secured_put",
        expiration=chain.expiration,
        days_to_expiration=chain.dte,
        legs=[_option_leg(atm_put, side="sell", quantity=1)],
        net_premium=premium * 100.0,
        max_profit=max_profit,
        max_loss=max_loss,
        breakeven_points=[strike - premium],
        notes=["Sell put while reserving strike * 100 cash."],
    )


def _build_iron_condor(chain: _ChainSlice, *, underlying_price: float) -> StrategyCandidate | None:
    short_call = _nearest_strike_row(
        chain.calls, underlying_price=underlying_price)
    short_put = _nearest_strike_row(
        chain.puts, underlying_price=underlying_price)
    if short_call is None or short_put is None:
        return None

    long_call = _row_by_offset(
        chain.calls, strike=float(short_call["strike"]), offset=2)
    long_put = _row_by_offset(
        chain.puts, strike=float(short_put["strike"]), offset=-2)
    if long_call is None or long_put is None:
        return None

    net_credit = (
        float(short_call["mid_price"])
        + float(short_put["mid_price"])
        - float(long_call["mid_price"])
        - float(long_put["mid_price"])
    )
    width_call = float(long_call["strike"] - short_call["strike"])
    width_put = float(short_put["strike"] - long_put["strike"])
    wing = max(width_call, width_put)
    max_loss = max(0.0, (wing - net_credit) * 100.0)
    max_profit = max(0.0, net_credit * 100.0)

    legs = [
        _option_leg(short_put, side="sell", quantity=1),
        _option_leg(long_put, side="buy", quantity=1),
        _option_leg(short_call, side="sell", quantity=1),
        _option_leg(long_call, side="buy", quantity=1),
    ]
    return StrategyCandidate(
        name="iron_condor",
        expiration=chain.expiration,
        days_to_expiration=chain.dte,
        legs=legs,
        net_premium=net_credit * 100.0,
        max_profit=max_profit,
        max_loss=max_loss,
        breakeven_points=[float(short_put["strike"]) - net_credit,
                          float(short_call["strike"]) + net_credit],
        notes=["Neutral credit spread on both wings."],
    )


def _build_butterfly(chain: _ChainSlice, *, underlying_price: float) -> StrategyCandidate | None:
    atm_call = _nearest_strike_row(
        chain.calls, underlying_price=underlying_price)
    if atm_call is None:
        return None

    lower = _row_by_offset(chain.calls, strike=float(
        atm_call["strike"]), offset=-1)
    upper = _row_by_offset(chain.calls, strike=float(
        atm_call["strike"]), offset=1)
    if lower is None or upper is None:
        return None

    debit = float(lower["mid_price"]) + float(upper["mid_price"]
                                              ) - 2.0 * float(atm_call["mid_price"])
    width = float(atm_call["strike"] - lower["strike"])
    max_profit = max(0.0, (width - debit) * 100.0)
    max_loss = max(0.0, debit * 100.0)
    return StrategyCandidate(
        name="call_butterfly",
        expiration=chain.expiration,
        days_to_expiration=chain.dte,
        legs=[
            _option_leg(lower, side="buy", quantity=1),
            _option_leg(atm_call, side="sell", quantity=2),
            _option_leg(upper, side="buy", quantity=1),
        ],
        net_premium=-debit * 100.0,
        max_profit=max_profit,
        max_loss=max_loss,
        breakeven_points=[float(lower["strike"]) + debit,
                          float(upper["strike"]) - debit],
        notes=["Low-cost directional-neutral structure."],
    )


def _build_straddle(chain: _ChainSlice, *, underlying_price: float) -> StrategyCandidate | None:
    atm_call = _nearest_strike_row(
        chain.calls, underlying_price=underlying_price)
    atm_put = _nearest_strike_row(
        chain.puts, underlying_price=underlying_price)
    if atm_call is None or atm_put is None:
        return None

    debit = float(atm_call["mid_price"]) + float(atm_put["mid_price"])
    strike = float(atm_call["strike"])
    return StrategyCandidate(
        name="long_straddle",
        expiration=chain.expiration,
        days_to_expiration=chain.dte,
        legs=[
            _option_leg(atm_call, side="buy", quantity=1),
            _option_leg(atm_put, side="buy", quantity=1),
        ],
        net_premium=-debit * 100.0,
        max_profit=None,
        max_loss=max(0.0, debit * 100.0),
        breakeven_points=[strike - debit, strike + debit],
        notes=["Long volatility at the money."],
    )


def _build_strangle(chain: _ChainSlice, *, underlying_price: float) -> StrategyCandidate | None:
    otm_call = chain.calls[chain.calls["strike"] > underlying_price].head(1)
    otm_put = chain.puts[chain.puts["strike"] < underlying_price].tail(1)
    if otm_call.empty or otm_put.empty:
        return None

    call_row = otm_call.iloc[0]
    put_row = otm_put.iloc[0]
    debit = float(call_row["mid_price"]) + float(put_row["mid_price"])
    return StrategyCandidate(
        name="long_strangle",
        expiration=chain.expiration,
        days_to_expiration=chain.dte,
        legs=[
            _option_leg(call_row, side="buy", quantity=1),
            _option_leg(put_row, side="buy", quantity=1),
        ],
        net_premium=-debit * 100.0,
        max_profit=None,
        max_loss=max(0.0, debit * 100.0),
        breakeven_points=[float(put_row["strike"]) -
                          debit, float(call_row["strike"]) + debit],
        notes=["Long volatility with cheaper OTM strikes."],
    )


def _build_vertical_spreads(
    chain: _ChainSlice,
    *,
    underlying_price: float,
    config: OptionsConfig,
) -> tuple[list[StrategyCandidate], list[dict[str, Any]]]:
    candidates: list[StrategyCandidate] = []
    audit_entries: list[dict[str, Any]] = []

    atm_call = _nearest_strike_row(
        chain.calls, underlying_price=underlying_price)
    if atm_call is not None:
        higher_call = _row_by_offset(
            chain.calls, strike=float(atm_call["strike"]), offset=1)
        if higher_call is not None:
            debit = float(atm_call["mid_price"]) - \
                float(higher_call["mid_price"])
            width = float(higher_call["strike"] - atm_call["strike"])
            candidates.append(
                StrategyCandidate(
                    name="bull_call_debit_spread",
                    expiration=chain.expiration,
                    days_to_expiration=chain.dte,
                    legs=[
                        _option_leg(atm_call, side="buy", quantity=1),
                        _option_leg(higher_call, side="sell", quantity=1),
                    ],
                    net_premium=-debit * 100.0,
                    max_profit=max(0.0, (width - debit) * 100.0),
                    max_loss=max(0.0, debit * 100.0),
                    breakeven_points=[float(atm_call["strike"]) + debit],
                    notes=["Directional bullish debit spread."],
                )
            )
            audit_entries.append(
                {
                    "strategy_family": "bull_call_debit_spread",
                    "status": "built",
                    "selection": "atm_plus_one_width",
                }
            )
        else:
            audit_entries.append(
                {
                    "strategy_family": "bull_call_debit_spread",
                    "status": "dropped",
                    "reason": "missing_higher_call_for_vertical",
                }
            )
    else:
        audit_entries.append(
            {
                "strategy_family": "bull_call_debit_spread",
                "status": "dropped",
                "reason": "missing_atm_call",
            }
        )

    target_short_center = underlying_price * \
        (1.0 - ((config.bull_put_otm_min_pct + config.bull_put_otm_max_pct) / 2.0))
    short_strike_min = underlying_price * (1.0 - config.bull_put_otm_max_pct)
    short_strike_max = underlying_price * (1.0 - config.bull_put_otm_min_pct)
    template_short_put = _row_nearest_to_strike(
        chain.puts[chain.puts["strike"] < underlying_price],
        target_strike=target_short_center,
        strike_min=short_strike_min,
        strike_max=short_strike_max,
    )

    short_put = template_short_put
    short_selection = "template_3_6pct_otm"
    if short_put is None:
        short_put = _nearest_strike_row(
            chain.puts[chain.puts["strike"] < underlying_price], underlying_price=underlying_price)
        short_selection = "fallback_nearest_put_below_spot"

    if short_put is not None:
        short_strike = float(short_put["strike"])
        target_long_center = short_strike - \
            ((config.spread_width_min_points + config.spread_width_max_points) / 2.0)
        long_put = _row_nearest_to_strike(
            chain.puts,
            target_strike=target_long_center,
            strike_min=short_strike - config.spread_width_max_points,
            strike_max=short_strike - config.spread_width_min_points,
        )

        width_selection = "template_8_15_points"
        if long_put is None:
            long_put = _row_by_offset(
                chain.puts,
                strike=short_strike,
                offset=-1,
            )
            width_selection = "fallback_nearest_lower_put"

        if long_put is not None:
            credit = float(short_put["mid_price"]) - \
                float(long_put["mid_price"])
            width = float(short_put["strike"] - long_put["strike"])
            candidates.append(
                StrategyCandidate(
                    name="bull_put_credit_spread",
                    expiration=chain.expiration,
                    days_to_expiration=chain.dte,
                    legs=[
                        _option_leg(short_put, side="sell", quantity=1),
                        _option_leg(long_put, side="buy", quantity=1),
                    ],
                    net_premium=credit * 100.0,
                    max_profit=max(0.0, credit * 100.0),
                    max_loss=max(0.0, (width - credit) * 100.0),
                    breakeven_points=[float(short_put["strike"]) - credit],
                    notes=[
                        "Directional bullish credit spread.",
                        f"Short leg selection: {short_selection}.",
                        f"Width selection: {width_selection}.",
                    ],
                )
            )

            short_otm_pct = ((underlying_price - short_strike) /
                             underlying_price) if underlying_price > 0 else 0.0
            audit_entries.append(
                {
                    "strategy_family": "bull_put_credit_spread",
                    "status": "built",
                    "short_selection": short_selection,
                    "width_selection": width_selection,
                    "short_strike": short_strike,
                    "long_strike": float(long_put["strike"]),
                    "short_otm_pct": short_otm_pct,
                    "width_points": width,
                    "target_short_otm_pct_range": [
                        config.bull_put_otm_min_pct,
                        config.bull_put_otm_max_pct,
                    ],
                    "target_width_points_range": [
                        config.spread_width_min_points,
                        config.spread_width_max_points,
                    ],
                }
            )
        else:
            audit_entries.append(
                {
                    "strategy_family": "bull_put_credit_spread",
                    "status": "dropped",
                    "reason": "missing_long_put_for_width",
                    "short_selection": short_selection,
                    "short_strike": short_strike,
                }
            )
    else:
        audit_entries.append(
            {
                "strategy_family": "bull_put_credit_spread",
                "status": "dropped",
                "reason": "missing_otm_or_fallback_short_put",
            }
        )

    return candidates, audit_entries


def build_strategy_candidates_with_audit(
    option_frame: pd.DataFrame,
    *,
    underlying_price: float,
    target_dte: int,
    config: OptionsConfig | None = None,
) -> tuple[list[StrategyCandidate], dict[str, Any]]:
    """Build strategy candidates and provide transparent generation diagnostics."""
    active_config = config or load_options_config()
    chain = _nearest_expiration(option_frame, target_dte)
    if chain is None:
        return [], {
            "status": "no_chain",
            "reason": "missing_calls_or_puts_for_selected_expiration",
        }

    candidates: list[StrategyCandidate] = []
    generation_steps: list[dict[str, Any]] = []

    maybe = [
        ("covered_call", _build_covered_call(
            chain, underlying_price=underlying_price)),
        ("cash_secured_put", _build_cash_secured_put(
            chain, underlying_price=underlying_price)),
        ("iron_condor", _build_iron_condor(chain, underlying_price=underlying_price)),
        ("call_butterfly", _build_butterfly(
            chain, underlying_price=underlying_price)),
        ("long_straddle", _build_straddle(chain, underlying_price=underlying_price)),
        ("long_strangle", _build_strangle(chain, underlying_price=underlying_price)),
    ]
    for strategy_name, item in maybe:
        if item is not None:
            candidates.append(item)
            generation_steps.append(
                {
                    "strategy_family": strategy_name,
                    "status": "built",
                }
            )
        else:
            generation_steps.append(
                {
                    "strategy_family": strategy_name,
                    "status": "dropped",
                    "reason": "required_legs_not_found",
                }
            )

    verticals, vertical_audit = _build_vertical_spreads(
        chain,
        underlying_price=underlying_price,
        config=active_config,
    )
    candidates.extend(verticals)
    generation_steps.extend(vertical_audit)

    audit = {
        "status": "ok",
        "selected_expiration": chain.expiration,
        "selected_dte": chain.dte,
        "target_dte": target_dte,
        "candidate_count": len(candidates),
        "template_config": {
            "bull_put_otm_pct_range": [
                active_config.bull_put_otm_min_pct,
                active_config.bull_put_otm_max_pct,
            ],
            "spread_width_points_range": [
                active_config.spread_width_min_points,
                active_config.spread_width_max_points,
            ],
        },
        "strategy_generation": generation_steps,
    }
    return candidates, audit


def build_strategy_candidates(
    option_frame: pd.DataFrame,
    *,
    underlying_price: float,
    target_dte: int,
    config: OptionsConfig | None = None,
) -> list[StrategyCandidate]:
    """Build all supported strategy candidates from one chain slice."""
    candidates, _ = build_strategy_candidates_with_audit(
        option_frame,
        underlying_price=underlying_price,
        target_dte=target_dte,
        config=config,
    )
    return candidates
