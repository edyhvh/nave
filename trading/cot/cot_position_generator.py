"""COT-driven weekly position plan generator."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from .models import TradeSetup, WeeklyAssetPlan


class COTPositionGenerator:
    """Generate weekly BTC/ETH plans from COT sections and 4H structure."""

    def __init__(self, default_risk_pct: float = 0.01):
        self.default_risk_pct = default_risk_pct

    def generate_weekly_plan(self, cot_data: dict, market_data_4h: dict) -> dict:
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
                confidence = 0.55
            elif trend in {"bearish", "down"} and bias == "bullish":
                confidence = 0.55
            elif bias == "neutral":
                confidence = 0.5
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
            )

            notes = [
                f"Primary signal (commercials): {net_comm:+,} with weekly delta {net_comm_delta:+,}.",
                f"Secondary filter (non-commercials): {net_non_comm:+,} with weekly delta {net_non_comm_delta:+,}.",
                f"4H structure trend: {trend}.",
            ]

            plans[asset] = WeeklyAssetPlan(
                asset=asset,
                bias=bias,
                confidence=round(confidence, 2),
                key_levels=key_levels,
                setups=setups,
                cot_summary={
                    "net_commercial": net_comm,
                    "net_commercial_delta": net_comm_delta,
                    "net_non_commercial": net_non_comm,
                    "net_non_commercial_delta": net_non_comm_delta,
                },
                notes=notes,
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
    ) -> list[TradeSetup]:
        if price <= 0:
            return []

        long_bias = bias == "bullish"
        direction = "long" if long_bias else "short"
        if bias == "neutral":
            direction = "long"

        eq = (swing_high + swing_low) / 2.0
        retrace_entry = eq if direction == "long" else eq
        breakout_entry = swing_high + atr * 0.15 if direction == "long" else swing_low - atr * 0.15
        continuation_entry = price

        setups = [
            self._make_setup(
                name="75_retracement",
                direction=direction,
                entry=retrace_entry,
                stop=swing_low - atr * 0.25 if direction == "long" else swing_high + atr * 0.25,
                target=swing_high + atr * 0.8 if direction == "long" else swing_low - atr * 0.8,
                rationale=f"{asset} retracement entry aligned with weekly COT bias.",
            ),
            self._make_setup(
                name="order_block_breakout",
                direction=direction,
                entry=breakout_entry,
                stop=swing_low if direction == "long" else swing_high,
                target=swing_high + atr * 1.2 if direction == "long" else swing_low - atr * 1.2,
                rationale=f"{asset} structure break confirms COT direction.",
            ),
            self._make_setup(
                name="fvg_continuation",
                direction=direction,
                entry=continuation_entry,
                stop=price - atr if direction == "long" else price + atr,
                target=price + atr * 2.0 if direction == "long" else price - atr * 2.0,
                rationale=f"{asset} continuation setup when momentum confirms COT bias.",
            ),
        ]
        return setups

    def _make_setup(
        self,
        *,
        name: str,
        direction: str,
        entry: float,
        stop: float,
        target: float,
        rationale: str,
    ) -> TradeSetup:
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk else 0.0
        return TradeSetup(
            name=name,
            direction=direction,
            entry=round(entry, 2),
            stop_loss=round(stop, 2),
            take_profit=round(target, 2),
            risk_reward=round(rr, 2),
            risk_pct=self.default_risk_pct,
            rationale=rationale,
        )
