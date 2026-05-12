"""Greeks enrichment using py_vollib with scipy fallback approximations."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd
from scipy.stats import norm

from options.config import OptionsConfig

try:
    from py_vollib.black_scholes.greeks.analytical import delta as bs_delta
    from py_vollib.black_scholes.greeks.analytical import gamma as bs_gamma
    from py_vollib.black_scholes.greeks.analytical import theta as bs_theta
    from py_vollib.black_scholes.greeks.analytical import vega as bs_vega

    _HAS_PY_VOLLIB = True
except Exception:  # noqa: BLE001
    _HAS_PY_VOLLIB = False


def _year_fraction(expiration: str) -> float:
    exp = datetime.fromisoformat(expiration).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    seconds = max(1.0, (exp - now).total_seconds())
    return seconds / (365.0 * 24.0 * 3600.0)


def _fallback_greeks(flag: str, s: float, k: float, t: float, r: float, sigma: float) -> tuple[float, float, float, float]:
    if min(s, k, t, sigma) <= 0:
        return (0.0, 0.0, 0.0, 0.0)

    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / \
        (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)

    if flag == "c":
        delta = norm.cdf(d1)
        theta = (
            -(s * norm.pdf(d1) * sigma) / (2.0 * math.sqrt(t))
            - r * k * math.exp(-r * t) * norm.cdf(d2)
        ) / 365.0
    else:
        delta = norm.cdf(d1) - 1.0
        theta = (
            -(s * norm.pdf(d1) * sigma) / (2.0 * math.sqrt(t))
            + r * k * math.exp(-r * t) * norm.cdf(-d2)
        ) / 365.0

    gamma = norm.pdf(d1) / (s * sigma * math.sqrt(t))
    vega = (s * norm.pdf(d1) * math.sqrt(t)) / 100.0
    return (float(delta), float(gamma), float(theta), float(vega))


def enrich_greeks(
    option_frame: pd.DataFrame,
    *,
    underlying_price: float,
    config: OptionsConfig,
) -> pd.DataFrame:
    """Return a copy of option_frame enriched with Delta/Gamma/Theta/Vega."""
    frame = option_frame.copy()
    if frame.empty:
        frame["delta"] = []
        frame["gamma"] = []
        frame["theta"] = []
        frame["vega"] = []
        return frame

    deltas: list[float] = []
    gammas: list[float] = []
    thetas: list[float] = []
    vegas: list[float] = []

    for row in frame.itertuples(index=False):
        option_type = str(getattr(row, "option_type")).lower()
        flag = "c" if option_type == "call" else "p"
        strike = float(getattr(row, "strike"))
        iv = float(getattr(row, "implied_volatility"))
        expiration = str(getattr(row, "expiration"))
        t = _year_fraction(expiration)

        if _HAS_PY_VOLLIB:
            try:
                delta = float(bs_delta(flag, underlying_price,
                              strike, t, config.risk_free_rate, iv))
                gamma = float(bs_gamma(flag, underlying_price,
                              strike, t, config.risk_free_rate, iv))
                theta = float(bs_theta(flag, underlying_price,
                              strike, t, config.risk_free_rate, iv))
                vega = float(bs_vega(flag, underlying_price,
                             strike, t, config.risk_free_rate, iv))
            except Exception:  # noqa: BLE001
                delta, gamma, theta, vega = _fallback_greeks(
                    flag,
                    underlying_price,
                    strike,
                    t,
                    config.risk_free_rate,
                    max(iv, 1e-6),
                )
        else:
            delta, gamma, theta, vega = _fallback_greeks(
                flag,
                underlying_price,
                strike,
                t,
                config.risk_free_rate,
                max(iv, 1e-6),
            )

        deltas.append(delta)
        gammas.append(gamma)
        thetas.append(theta)
        vegas.append(vega)

    frame["delta"] = deltas
    frame["gamma"] = gammas
    frame["theta"] = thetas
    frame["vega"] = vegas
    return frame
