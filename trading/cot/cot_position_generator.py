"""COT-informed weekly directional context generator.

Philosophy (per CriptoPana):
─────────────────────────────
The Commitment of Traders report is ONLY a record of past positioning.
It is NOT a predictive tool and must never be treated as a direct signal.

    • Commercials are primarily hedgers — their net position reflects
      defensive institutional activity, not directional conviction.
    • Non-Commercials are speculators — their positioning is a sentiment
      gauge, useful as a secondary filter but never as a primary driver.
    • The COT should never be used in isolation.  Every setup must require
      strong confluence with 4H price structure (order blocks, FVGs,
      mitigation blocks, 75% retracement zones, etc.).
    • Outputs should be humble, realistic, and never promise direction
      with high certainty.  The maximum confidence for any COT-derived
      context is 0.65.

Decision Stack:
    1. Net Commercial position + weekly delta → primary directional context
       (institutional hedging pressure).
    2. Non-Commercial positioning → secondary sentiment filter that can
       weaken confidence but never override the commercial-derived direction.
    3. 4H structure confluence assessment → determines whether setups are
       emitted at all.

Structure Confluence Levels:
    • "strong"  — 4H trend aligns with COT context AND price is near a key
      IPDA level (within 1 ATR of swing high/low).
    • "partial" — 4H trend aligns but price is mid-range (no clear level).
    • "none"    — 4H trend opposes COT context, or trend is "unknown".
      No setups are generated in this case.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Literal

from .models import Confluence, TradeSetup, WeeklyAssetPlan

# Hard confidence cap — COT is lagging context; high conviction is dishonest.
MAX_CONFIDENCE = 0.65


class COTPositionGenerator:
    """Generate weekly directional context from COT positioning + 4H structure.

    The output is a *conditional* plan: setups are only emitted when 4H price
    structure confirms the directional context derived from commercial hedging
    activity.  When structure opposes or is unknown, the plan reports the
    context but explicitly states "no actionable setups."
    """

    def __init__(self, default_risk_pct: float = 0.01):
        self.default_risk_pct = default_risk_pct

    def generate_weekly_plan(
        self,
        cot_data: dict,
        market_data_4h: dict,
        *,
        capital_usd: float = 2000.0,
        leverage: float = 10.0,
    ) -> dict:
        """Build a weekly directional context plan from COT + 4H structure.

        COT data provides *context* (not a signal).  Setups are only generated
        when 4H price structure provides clear confluence.
        """
        plans: dict[str, WeeklyAssetPlan] = {}
        for asset in sorted(cot_data.keys()):
            coin_payload = cot_data.get(asset, {}) or {}
            combined = coin_payload.get("combined") or coin_payload.get("futures_and_options") or {}
            futures_only = coin_payload.get("futures_only") or {}

            # ── Step 1: Commercial hedging context (PRIMARY) ─────────────
            source = combined or futures_only
            net_comm = int(source.get("net_commercial", 0) or 0)
            net_comm_delta = int(source.get("net_commercial_delta", 0) or 0)

            # ── Step 2: Speculative sentiment filter (SECONDARY) ─────────
            net_non_comm = int(source.get("net_non_commercial", 0) or 0)
            net_non_comm_delta = int(source.get("net_non_commercial_delta", 0) or 0)

            # ── Derive directional context from commercials ALONE ────────
            bias = self._derive_commercial_bias(net_comm, net_comm_delta)

            # ── Step 3: 4H structure confluence assessment ───────────────
            structure = market_data_4h.get(asset, {}) or {}
            trend = str(structure.get("trend", "unknown")).lower()
            price = float(structure.get("price", 0.0) or 0.0)
            swing_high = float(structure.get("swing_high", price * 1.01 if price else 0.0))
            swing_low = float(structure.get("swing_low", price * 0.99 if price else 0.0))
            atr = float(structure.get("atr", max(price * 0.012, 1.0) if price else 1.0))

            confluence = self._assess_confluence(
                bias=bias,
                trend=trend,
                price=price,
                swing_high=swing_high,
                swing_low=swing_low,
                atr=atr,
            )

            # ── Confidence: capped and adjusted by confluence + sentiment ─
            confidence = self._compute_confidence(
                bias=bias,
                confluence=confluence,
                net_non_comm=net_non_comm,
                net_non_comm_delta=net_non_comm_delta,
            )

            key_levels = {
                "swing_high": round(swing_high, 2),
                "swing_low": round(swing_low, 2),
                "equilibrium": round((swing_high + swing_low) / 2.0, 2),
            }

            # ── Setup generation: gated by confluence ────────────────────
            setups = self._build_setups(
                asset=asset,
                bias=bias,
                confluence=confluence,
                price=price,
                swing_high=swing_high,
                swing_low=swing_low,
                atr=atr,
                confidence=confidence,
                capital_usd=capital_usd,
                leverage=leverage,
            )

            bias_explanation = self._build_bias_explanation(
                bias=bias,
                confluence=confluence,
                net_comm=net_comm,
                net_comm_delta=net_comm_delta,
                net_non_comm=net_non_comm,
                net_non_comm_delta=net_non_comm_delta,
                trend=trend,
            )

            risk_notes = [
                "COT data is released with a 3-day lag and reflects past positioning, not current intent.",
                "Never trade COT context in isolation — require 4H structure confirmation on every entry.",
                "If price invalidates the key level, the setup is void regardless of COT context.",
                "Risk per setup is capped to preserve capital during invalidation events.",
                "Do not run all setups simultaneously; choose the single best structure confirmation.",
            ]

            plans[asset] = WeeklyAssetPlan(
                asset=asset,
                bias=bias,
                confidence=round(confidence, 2),
                bias_explanation=bias_explanation,
                structure_confluence=confluence,
                key_levels=key_levels,
                setups=setups,
                cot_summary={
                    "net_commercial": net_comm,
                    "net_commercial_delta": net_comm_delta,
                    "net_non_commercial": net_non_comm,
                    "net_non_commercial_delta": net_non_comm_delta,
                },
                risk_management_notes=risk_notes,
            )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "assets": {asset: asdict(plan) for asset, plan in plans.items()},
        }

    # ── Bias derivation ──────────────────────────────────────────────────

    @staticmethod
    def _derive_commercial_bias(net_comm: int, net_comm_delta: int) -> str:
        """Derive directional context from commercial hedging activity alone.

        Positive net commercial + positive delta → commercials are
        accumulating long hedges → *suggests* bullish institutional context.

        Negative net commercial + negative delta → commercials are
        accumulating short hedges → *suggests* bearish institutional context.

        When the signal is mixed or near zero, context is neutral.
        """
        comm_score = net_comm + net_comm_delta
        if comm_score > 500:
            return "bullish"
        elif comm_score < -500:
            return "bearish"
        return "neutral"

    # ── Confluence assessment ────────────────────────────────────────────

    @staticmethod
    def _assess_confluence(
        *,
        bias: str,
        trend: str,
        price: float,
        swing_high: float,
        swing_low: float,
        atr: float,
    ) -> Confluence:
        """Assess 4H structure confluence with COT-derived context.

        Returns:
            "strong"  — trend aligns AND price is near a key IPDA level.
            "partial" — trend aligns but price is mid-range.
            "none"    — trend opposes or is unknown.
        """
        if bias == "neutral":
            return "none"

        trend_aligns = (bias == "bullish" and trend in {"bullish", "up"}) or (
            bias == "bearish" and trend in {"bearish", "down"}
        )

        if not trend_aligns:
            return "none"

        # Price proximity to key IPDA levels (swing extremes).
        near_support = abs(price - swing_low) <= atr
        near_resistance = abs(price - swing_high) <= atr
        near_key_level = (bias == "bullish" and near_support) or (
            bias == "bearish" and near_resistance
        )

        return "strong" if near_key_level else "partial"

    # ── Confidence computation ───────────────────────────────────────────

    @staticmethod
    def _compute_confidence(
        *,
        bias: str,
        confluence: Confluence,
        net_non_comm: int,
        net_non_comm_delta: int,
    ) -> float:
        """Compute confidence, hard-capped at MAX_CONFIDENCE.

        Base confidence is set by confluence level.  Non-commercial sentiment
        can weaken confidence (opposing speculative crowding) but never
        strengthens it beyond the cap.
        """
        if bias == "neutral" or confluence == "none":
            return 0.45

        if confluence == "strong":
            base = 0.60
        else:  # partial
            base = 0.52

        # Non-commercial sentiment adjustment (secondary filter only).
        # If speculators are crowding in the same direction as our bias,
        # that's contrarian-negative → slightly weaken confidence.
        spec_aligned = (bias == "bullish" and (net_non_comm + net_non_comm_delta) > 2000) or (
            bias == "bearish" and (net_non_comm + net_non_comm_delta) < -2000
        )
        if spec_aligned:
            base -= 0.03  # Speculative crowding weakens edge.

        return min(base, MAX_CONFIDENCE)

    # ── Bias explanation ─────────────────────────────────────────────────

    @staticmethod
    def _build_bias_explanation(
        *,
        bias: str,
        confluence: Confluence,
        net_comm: int,
        net_comm_delta: int,
        net_non_comm: int,
        net_non_comm_delta: int,
        trend: str,
    ) -> str:
        """Build a humble, educational bias explanation."""
        parts: list[str] = []

        if bias == "neutral":
            parts.append(
                f"Commercial hedging activity ({net_comm:+,}, delta {net_comm_delta:+,}) "
                f"does not suggest a clear directional context this week."
            )
        elif bias == "bullish":
            parts.append(
                f"Commercial hedging suggests bullish institutional context "
                f"({net_comm:+,}, delta {net_comm_delta:+,}). "
                f"This reflects past positioning, not a prediction."
            )
        else:
            parts.append(
                f"Commercial hedging suggests bearish institutional context "
                f"({net_comm:+,}, delta {net_comm_delta:+,}). "
                f"This reflects past positioning, not a prediction."
            )

        parts.append(
            f"Speculative sentiment filter: non-commercials at "
            f"{net_non_comm:+,} (delta {net_non_comm_delta:+,})."
        )

        if confluence == "strong":
            parts.append(
                f"4H structure ({trend}) aligns with COT context and price is near a key level — "
                f"conditional setups are generated."
            )
        elif confluence == "partial":
            parts.append(
                f"4H structure ({trend}) aligns with COT context but price is mid-range — "
                f"one conservative setup is generated."
            )
        else:
            parts.append(
                f"4H structure ({trend}) does not confirm COT context — "
                f"no setups are generated. Wait for alignment."
            )

        return " ".join(parts)

    # ── Setup generation ─────────────────────────────────────────────────

    def _build_setups(
        self,
        *,
        asset: str,
        bias: str,
        confluence: Confluence,
        price: float,
        swing_high: float,
        swing_low: float,
        atr: float,
        confidence: float,
        capital_usd: float,
        leverage: float,
    ) -> list[TradeSetup]:
        """Generate setups ONLY when structure confluence exists."""
        if price <= 0 or bias == "neutral" or confluence == "none":
            return []

        direction: Literal["long", "short"] = "long" if bias == "bullish" else "short"

        range_ = swing_high - swing_low
        retrace_entry = (
            swing_low + range_ * 0.25 if direction == "long" else swing_high - range_ * 0.25
        )
        breakout_entry = swing_high + atr * 0.15 if direction == "long" else swing_low - atr * 0.15
        continuation_entry = price

        all_setups = [
            self._make_setup(
                name="75_retracement",
                direction=direction,
                entry_reference=retrace_entry,
                entry_zone=self._entry_zone(retrace_entry, atr),
                stop=swing_low - atr * 0.25 if direction == "long" else swing_high + atr * 0.25,
                tp_rr=[1.8, 2.4, 3.2],
                confidence=confidence,
                capital_usd=capital_usd,
                leverage=leverage,
                rationale=(
                    f"{asset} 75% retracement entry — only valid if 4H confirms with "
                    f"an order block or FVG at this level. "
                    f"Invalidation: {'break below swing low' if direction == 'long' else 'break above swing high'} + ATR buffer."
                ),
            ),
            self._make_setup(
                name="order_block_breakout",
                direction=direction,
                entry_reference=breakout_entry,
                entry_zone=self._entry_zone(breakout_entry, atr),
                stop=swing_low if direction == "long" else swing_high,
                tp_rr=[1.5, 2.1, 2.8],
                confidence=confidence,
                capital_usd=capital_usd,
                leverage=leverage,
                rationale=(
                    f"{asset} structure break entry — requires confirmed break of "
                    f"{'swing high' if direction == 'long' else 'swing low'} on 4H close. "
                    f"Invalidation: full reclaim of the broken level."
                ),
            ),
            self._make_setup(
                name="fvg_continuation",
                direction=direction,
                entry_reference=continuation_entry,
                entry_zone=self._entry_zone(continuation_entry, atr),
                stop=price - atr if direction == "long" else price + atr,
                tp_rr=[1.3, 2.0, 2.6],
                confidence=confidence,
                capital_usd=capital_usd,
                leverage=leverage,
                rationale=(
                    f"{asset} FVG continuation — enter only if a 4H fair value gap "
                    f"is present and unfilled. "
                    f"Invalidation: full fill of the FVG against the bias direction."
                ),
            ),
        ]

        # Confluence gating: strong → 3 setups, partial → 1 conservative.
        if confluence == "partial":
            return all_setups[:1]
        return all_setups

    @staticmethod
    def _entry_zone(entry_reference: float, atr: float) -> dict[str, float]:
        width = max(atr * 0.2, entry_reference * 0.002)
        return {
            "low": round(entry_reference - width, 2),
            "high": round(entry_reference + width, 2),
        }

    def _make_setup(
        self,
        *,
        name: str,
        direction: Literal["long", "short"],
        entry_reference: float,
        entry_zone: dict[str, float],
        stop: float,
        tp_rr: list[float],
        confidence: float,
        capital_usd: float,
        leverage: float,
        rationale: str,
    ) -> TradeSetup:
        risk = abs(entry_reference - stop)
        if risk <= 0:
            risk = max(entry_reference * 0.003, 1.0)

        base_risk_pct = self.default_risk_pct
        confidence_bonus = min(0.004, max(0.0, confidence - 0.5) * 0.015)
        recommended_risk_pct = round(min(0.015, base_risk_pct + confidence_bonus), 4)
        risk_budget_usd = capital_usd * recommended_risk_pct

        quantity = risk_budget_usd / risk
        max_notional = capital_usd * leverage
        notional = quantity * entry_reference
        if notional > max_notional and entry_reference > 0:
            quantity = max_notional / entry_reference
            notional = max_notional

        take_profit_levels: list[dict[str, float | str]] = []
        for idx, rr in enumerate(tp_rr, start=1):
            if direction == "long":
                tp_price = entry_reference + risk * rr
            else:
                tp_price = entry_reference - risk * rr
            take_profit_levels.append(
                {
                    "label": f"TP{idx}",
                    "price": round(tp_price, 2),
                    "rr": round(rr, 2),
                }
            )

        return TradeSetup(
            name=name,
            direction=direction,
            entry_zone=entry_zone,
            entry_reference=round(entry_reference, 2),
            stop_loss=round(stop, 2),
            take_profit_levels=take_profit_levels,
            recommended_risk_pct=recommended_risk_pct,
            position_size_usd=round(risk_budget_usd, 2),
            position_size_coin=round(quantity, 6),
            notional_usd_10x=round(notional, 2),
            rationale=rationale,
        )
