"""COT-driven weekly position plan generator."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Literal

from .models import TradeSetup, WeeklyAssetPlan


class COTPositionGenerator:
    """Generate weekly BTC/ETH plans from COT sections and 4H structure."""

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
        """Build a weekly plan from COT positioning and 4H market structure.

        The decision stack is:
        1. Net Commercial + weekly delta as the primary short-term bias.
        2. Non-Commercial positioning as a secondary sentiment filter.
        3. 4H structure alignment for execution timing and levels.
        """
        plans: dict[str, WeeklyAssetPlan] = {}
        for asset in sorted(cot_data.keys()):
            coin_payload = cot_data.get(asset, {}) or {}
            combined = coin_payload.get("combined") or coin_payload.get("futures_and_options") or {}
            futures_only = coin_payload.get("futures_only") or {}

            net_comm = int((combined or futures_only).get("net_commercial", 0) or 0)
            net_comm_delta = int((combined or futures_only).get("net_commercial_delta", 0) or 0)
            net_non_comm = int((combined or futures_only).get("net_non_commercial", 0) or 0)
            net_non_comm_delta = int(
                (combined or futures_only).get("net_non_commercial_delta", 0) or 0
            )

            primary_score = net_comm + net_comm_delta
            # Secondary filter is kept lower weight than commercial flow by design.
            secondary_score = -(net_non_comm + net_non_comm_delta)
            structure = market_data_4h.get(asset, {}) or {}
            trend = str(structure.get("trend", "unknown")).lower()

            bias = "neutral"
            score = primary_score * 1.0 + secondary_score * 0.35
            if score > 0:
                bias = "bullish"
            elif score < 0:
                bias = "bearish"

            if trend in {"bullish", "up"} and bias == "bearish":
                confidence = 0.56
            elif trend in {"bearish", "down"} and bias == "bullish":
                confidence = 0.56
            elif bias == "neutral":
                confidence = 0.5
            elif abs(primary_score) > 10000:
                confidence = 0.78
            else:
                confidence = 0.7

            price = float(structure.get("price", 0.0) or 0.0)
            swing_high = float(structure.get("swing_high", price * 1.01 if price else 0.0))
            swing_low = float(structure.get("swing_low", price * 0.99 if price else 0.0))
            atr = float(structure.get("atr", max(price * 0.012, 1.0) if price else 1.0))

            key_levels = {
                "swing_high": round(swing_high, 2),
                "swing_low": round(swing_low, 2),
                "equilibrium": round((swing_high + swing_low) / 2.0, 2),
            }

            setups = self._build_setups(
                asset=asset,
                bias=bias,
                price=price,
                swing_high=swing_high,
                swing_low=swing_low,
                atr=atr,
                confidence=confidence,
                capital_usd=capital_usd,
                leverage=leverage,
            )

            if bias == "neutral":
                bias_explanation = f"Commercial flow ({net_comm:+,}, delta {net_comm_delta:+,}) does not provide a clear directional edge."
            elif bias == "bullish":
                bias_explanation = (
                    f"Commercials are net supportive ({net_comm:+,}, delta {net_comm_delta:+,}); "
                    f"non-commercials are used as a sentiment filter ({net_non_comm:+,}, delta {net_non_comm_delta:+,})."
                )
            else:
                bias_explanation = (
                    f"Commercials are net defensive ({net_comm:+,}, delta {net_comm_delta:+,}); "
                    f"non-commercials are used as a sentiment filter ({net_non_comm:+,}, delta {net_non_comm_delta:+,})."
                )

            risk_notes = [
                "Risk per setup is capped to preserve capital during invalidation events.",
                "Do not run all setups simultaneously; choose the best structure confirmation.",
                "If 4H structure diverges from COT bias, reduce size or skip execution.",
            ]

            plans[asset] = WeeklyAssetPlan(
                asset=asset,
                bias=bias,
                confidence=round(confidence, 2),
                bias_explanation=bias_explanation,
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

    def _build_setups(
        self,
        *,
        asset: str,
        bias: str,
        price: float,
        swing_high: float,
        swing_low: float,
        atr: float,
        confidence: float,
        capital_usd: float,
        leverage: float,
    ) -> list[TradeSetup]:
        if price <= 0:
            return []

        if bias == "neutral":
            return []

        direction: Literal["long", "short"] = "long" if bias == "bullish" else "short"

        range_ = swing_high - swing_low
        # 75% retracement: long enters near the lower quarter; short near the upper quarter.
        retrace_entry = (
            swing_low + range_ * 0.25 if direction == "long" else swing_high - range_ * 0.25
        )
        breakout_entry = swing_high + atr * 0.15 if direction == "long" else swing_low - atr * 0.15
        continuation_entry = price

        setups = [
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
                rationale=f"{asset} retracement entry aligned with weekly COT bias.",
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
                rationale=f"{asset} structure break confirms COT direction.",
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
                rationale=f"{asset} continuation setup when momentum confirms COT bias.",
            ),
        ]
        return setups

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
        confidence_bonus = min(0.004, max(0.0, confidence - 0.6) * 0.02)
        recommended_risk_pct = round(min(0.02, base_risk_pct + confidence_bonus), 4)
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
