"""COT Analyzer — Parses COT data into trading bias per Nave philosophy.

Focuses on non-commercial (speculators) vs commercials positioning.
Commercials (institutions/makers) move the market per technical.yaml.

Bias Calculation (F.I.T.S. Contrarian Logic):
─────────────────────────────────────────────
The bias is *contrarian* to speculator positioning. When speculators (non-
commercials) pile into one side, the market is likely to reverse:

  pct_oi > 5%   → specs heavily long (rare, P95+) → BEARISH reversal  (conf 75%)
  pct_oi < -15% → specs heavily short (P30-)       → BULLISH reversal  (conf 80%)
  0 < pct_oi ≤5 → specs mildly long               → lean BEARISH      (conf 60%)
  -15 ≤ pct_oi < -8 → specs moderately short       → lean BULLISH      (conf 65%)
  -8 ≤ pct_oi ≤ 0   → no clear edge               → NEUTRAL           (conf 50%)

FITS Weighted Score (0-100):
  40% Sentiment  — abs(pct_oi) / 20, capped at 1.0
  30% Fundamental — abs(weekly_change) / 2000, capped at 1.0
  30% Technical  — stub at 0.7 (manual chart confluence)

Bias Strength → Leverage mapping:
  score > 70 → STRONG  (1.0 multiplier, up to 10x leverage)
  40-70      → MEDIUM  (0.6 multiplier, 5-8x leverage)
  < 40       → WEAK    (0.25 multiplier, 1-5x or skip)

Historical Percentile:
  Net Non-Commercial ranked within all available history (0=extreme short, 100=extreme long).
  Used for context: "Specs at P85 → historically crowded long → watch for reversal".
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from trading.crypto.config import DEFAULT_SETUPS, COT_PRIMARY_WEIGHT
from trading.crypto.cot.cot_historical_analyzer import COTHistoricalAnalyzer
from trading.crypto.cot.cot_report_generator import COTReportGenerator
from trading.crypto.signals import Signal, Direction

logger = logging.getLogger(__name__)

MIN_PERCENTILE_HISTORY_WEEKS = 52
TARGET_PERCENTILE_HISTORY_WEEKS = 104


@dataclass
class COTBias:
    """Structured COT bias for an asset.

    Attributes:
        asset: "BTC" or "ETH".
        net_non_commercial: Speculator net position (long - short).
        pct_oi_non_com: Absolute net as % of open interest.
        weekly_change: Week-over-week change in net non-commercial.
        bias: "bullish", "bearish", or "neutral" (contrarian to specs).
        confidence: Conviction score in [0, 1].
        net_commercial: Commercial (hedger) net position (long - short).
        open_interest: Total open interest.
        oi_change_pct: Week-over-week OI change in percent.
        historical_percentile: Current net non-comm ranked 0-100 in available history.
        metadata: Additional diagnostic context.
    """

    asset: str
    net_non_commercial: int
    pct_oi_non_com: float
    weekly_change: int
    bias: str
    confidence: float
    bias_label: str = "NEUTRAL"
    net_commercial: int = 0
    open_interest: int = 0
    oi_change_pct: float = 0.0
    historical_percentile: int = 50
    metadata: Dict[str, Any] = field(default_factory=dict)


class COTAnalyzer:
    """Analyzes COT reports for BTC and ETH, generates Signals."""

    def __init__(
        self,
        setups: Optional[List[str]] = None,
        regime: Optional[str] = None,
    ):
        candidate_setups = setups or list(DEFAULT_SETUPS)
        self.regime = regime
        self.setups = candidate_setups

    def analyze(self, cot_data: Dict[str, Any]) -> Dict[str, COTBias]:
        """Analyze COT for all assets and return biases."""
        results = {}
        for asset, raw in cot_data.items():
            bias = self._analyze_single(asset, raw)
            results[asset] = bias
        return results

    def generate_historical_variation_report(
        self,
        months: int,
        cot_data: Dict[str, Any],
        as_of_date: str | None = None,
    ) -> dict[str, Any]:
        """Generate a historical COT variation report with precise date ranges.

        Periods include:
        - Last Week (previous report date -> latest report date)
        - Last 1..N Months (calendar-month anchor to latest report date)
        """
        historical = COTHistoricalAnalyzer().generate_historical_variation(
            months=months,
            cot_data=cot_data,
            as_of_date=as_of_date,
        )
        markdown = COTReportGenerator().render_historical_markdown(
            months=months,
            as_of=historical.get("as_of_date", "N/A"),
            per_asset=historical.get("assets", {}),
            observations=historical.get("observations", []),
        )
        return {
            **historical,
            "markdown": markdown,
        }

    def _analyze_single(self, asset: str, raw: Dict) -> COTBias:
        """Parse single asset COT into bias (aligned to F.I.T.S. sentiment).

        Handles two data shapes:
          1. Pre-computed dict with 'net_non_commercial' (mock/simplified data).
          2. Dict with 'raw' key containing list of record dicts (real CFTC data).

        Extracts: net non-commercial, net commercial, OI, weekly changes,
        historical percentile.
        """
        df = pd.DataFrame(raw.get("raw", []))
        history_points = len(df)

        if not df.empty:
            (
                net,
                pct_signed,
                change,
                net_comm,
                oi,
                oi_change_pct,
                percentile,
                history_points,
            ) = self._extract_from_dataframe(df)
        elif isinstance(raw, dict) and ("net_non_commercial" in raw or "noncomm_net" in raw):
            (
                net,
                pct_signed,
                change,
                net_comm,
                oi,
                oi_change_pct,
                percentile,
                history_points,
            ) = self._extract_from_precomputed(raw)
        else:
            logger.warning("No COT data available for %s", asset)
            net, pct_signed, change, net_comm, oi, oi_change_pct, percentile, history_points = (
                0,
                0.0,
                0,
                0,
                0,
                0.0,
                50,
                0,
            )

        pct_abs = abs(pct_signed)

        # ── F.I.T.S. Weighted Score (0-100) ──
        # 40% Sentiment: how extreme is speculator positioning?
        pct_extreme = pct_abs / 20.0  # 20% OI = maximum signal
        # 30% Fundamental: how fast is positioning changing?
        # 2000 contracts/week = strong momentum
        change_signal = abs(change) / 2000
        # 30% Technical: stub — manual chart confluence (OBs, FVGs, etc.)
        technical_stub = 0.7

        score = min(
            100,
            int(40 * min(pct_extreme, 1.0) + 30 * min(change_signal, 1.0) + 30 * technical_stub),
        )

        # ── Contrarian Bias Logic ──
        # Specs heavily positioned one way → expect reversal the other way
        if pct_signed <= -15.0:
            bias = "bullish"
            bias_label = "BULLISH"
        elif pct_signed < -8.0:
            bias = "bullish"
            bias_label = "LEAN BULLISH"
        elif pct_signed >= 5.0:
            bias = "bearish"
            bias_label = "BEARISH"
        elif pct_signed > 0.0:
            bias = "bearish"
            bias_label = "LEAN BEARISH"
        else:
            bias = "neutral"
            bias_label = "NEUTRAL"

        # Confidence and FITS consistency rule:
        # 1) FITS score is the main continuous confidence driver.
        # 2) Extreme crowding gets a small premium.
        # 3) Neutral bias stays centered at 50% confidence.
        if bias == "neutral":
            conf = 0.50
        else:
            crowding_premium = 0.03 if pct_abs >= 15.0 else 0.0
            conf = min(0.90, max(0.50, 0.45 + 0.45 * (score / 100.0) + crowding_premium))

        side = "net long" if pct_signed >= 0 else "net short"
        intensity = self._position_intensity(pct_abs)
        if bias == "bullish":
            cot_interpretation = f"Specs {intensity} {side} -> contrarian bullish"
            contrarian_label = "contrarian bullish"
        elif bias == "bearish":
            cot_interpretation = f"Specs {intensity} {side} -> contrarian bearish"
            contrarian_label = "contrarian bearish"
        else:
            cot_interpretation = "Specs near neutral -> no clear contrarian edge"
            contrarian_label = "no strong contrarian edge"

        percentile_band = self._percentile_band(percentile)
        pct_interp = f"Net Non-Comm percentile {percentile} (0-100) -> {percentile_band} -> {contrarian_label}"
        percentile_warning = ""
        if history_points < MIN_PERCENTILE_HISTORY_WEEKS:
            percentile_warning = (
                f"Insufficient history for percentile ({history_points} weekly snapshots; "
                f"target >= {MIN_PERCENTILE_HISTORY_WEEKS})."
            )

        market_regime = self.regime or self._infer_market_regime(
            change=int(change), pct_oi=float(pct_signed)
        )

        bias_strength = "strong" if score > 70 else "medium" if score > 40 else "weak"

        metadata = {
            "net_non_commercial": int(net),
            "pct_oi": round(pct_abs, 1),
            "pct_oi_signed": round(pct_signed, 1),
            "pct_oi_position_side": "net long" if pct_signed >= 0 else "net short",
            "weekly_change": int(change),
            "net_commercial": int(net_comm),
            "open_interest": int(oi),
            "oi_change_pct": round(oi_change_pct, 2),
            "historical_percentile": percentile,
            "history_points": history_points,
            "percentile_interpretation": pct_interp,
            "percentile_warning": percentile_warning,
            "cot_interpretation": cot_interpretation,
            "bias_label": bias_label,
            "report_date": raw.get("latest_date", "N/A"),
            "as_of_date": raw.get("as_of_date", raw.get("latest_date", "N/A")),
            "release_date": raw.get("release_date", "N/A"),
            "cached": raw.get("cached", False),
            "source": "cftc_cot",
            "philosophy_ref": "F.I.T.S. sentiment — commercials as makers",
            "setups": self.setups,
            "cot_weight": COT_PRIMARY_WEIGHT,
            "fits_weighted_score": score,
            "confidence_rule": "confidence = clamp(0.50, 0.90, 0.45 + 0.45*(fits/100) + crowding_premium)",
            "bias_strength": bias_strength,
            "cot_bias_strength": 1.0 if score > 70 else 0.6 if score > 40 else 0.25,
            "market_regime": market_regime,
            "momentum": float(change),
            "oi_level": float(pct_abs),
            "volatility": 0.02 + (min(abs(change), 2000) / 2000) * 0.03,
        }

        return COTBias(
            asset=asset,
            net_non_commercial=int(net),
            pct_oi_non_com=round(pct_abs, 2),
            weekly_change=int(change),
            bias=bias,
            bias_label=bias_label,
            confidence=round(conf, 2),
            net_commercial=int(net_comm),
            open_interest=int(oi),
            oi_change_pct=round(oi_change_pct, 2),
            historical_percentile=percentile,
            metadata=metadata,
        )

    # ── Data extraction helpers ──────────────────────────────────────────

    def _extract_from_dataframe(self, df: pd.DataFrame):
        """Extract all metrics from a DataFrame of COT records."""
        long_col = self._first_existing(
            df, ["noncomm_positions_long_all", "Noncommercial_Positions_Long"]
        )
        short_col = self._first_existing(
            df, ["noncomm_positions_short_all", "Noncommercial_Positions_Short"]
        )
        oi_col = self._first_existing(df, ["open_interest_all", "Open_Interest_All"])
        comm_long_col = self._first_existing(
            df, ["comm_positions_long_all", "Commercial_Positions_Long"]
        )
        comm_short_col = self._first_existing(
            df, ["comm_positions_short_all", "Commercial_Positions_Short"]
        )

        fin_spec_long_cols = [
            c
            for c in [
                "asset_mgr_positions_long",
                "lev_money_positions_long",
                "other_rept_positions_long",
            ]
            if c in df.columns
        ]
        fin_spec_short_cols = [
            c
            for c in [
                "asset_mgr_positions_short",
                "lev_money_positions_short",
                "other_rept_positions_short",
            ]
            if c in df.columns
        ]

        # Net Non-Commercial
        if long_col:
            latest_long = self._safe_float(df[long_col].iloc[-1])
            latest_short = self._safe_float(df[short_col].iloc[-1]) if short_col else 0.0
            net = latest_long - latest_short
        elif fin_spec_long_cols and fin_spec_short_cols:
            latest_long = sum(self._safe_float(df[c].iloc[-1]) for c in fin_spec_long_cols)
            latest_short = sum(self._safe_float(df[c].iloc[-1]) for c in fin_spec_short_cols)
            net = latest_long - latest_short
        else:
            net = 0.0

        # Open Interest
        oi = self._safe_float(df[oi_col].iloc[-1]) if oi_col else 0.0

        # % of OI (signed: positive = net long, negative = net short)
        pct = round(net / oi * 100, 2) if oi else 0.0

        # Weekly Change
        if len(df) >= 2 and (long_col or (fin_spec_long_cols and fin_spec_short_cols)):
            if long_col:
                prev_long = self._safe_float(df[long_col].iloc[-2])
                prev_short = self._safe_float(df[short_col].iloc[-2]) if short_col else 0.0
                prev_net = prev_long - prev_short
            else:
                prev_long = sum(self._safe_float(df[c].iloc[-2]) for c in fin_spec_long_cols)
                prev_short = sum(self._safe_float(df[c].iloc[-2]) for c in fin_spec_short_cols)
                prev_net = prev_long - prev_short
            change = int(net - prev_net)
        elif (
            "change_in_asset_mgr_long" in df.columns
            and "change_in_asset_mgr_short" in df.columns
            and "change_in_lev_money_long" in df.columns
            and "change_in_lev_money_short" in df.columns
            and "change_in_other_rept_long" in df.columns
            and "change_in_other_rept_short" in df.columns
        ):
            d_long = (
                self._safe_float(df["change_in_asset_mgr_long"].iloc[-1])
                + self._safe_float(df["change_in_lev_money_long"].iloc[-1])
                + self._safe_float(df["change_in_other_rept_long"].iloc[-1])
            )
            d_short = (
                self._safe_float(df["change_in_asset_mgr_short"].iloc[-1])
                + self._safe_float(df["change_in_lev_money_short"].iloc[-1])
                + self._safe_float(df["change_in_other_rept_short"].iloc[-1])
            )
            change = int(d_long - d_short)
        elif (
            "change_in_noncomm_long_all" in df.columns
            and "change_in_noncomm_short_all" in df.columns
        ):
            d_long = self._safe_float(df["change_in_noncomm_long_all"].iloc[-1])
            d_short = self._safe_float(df["change_in_noncomm_short_all"].iloc[-1])
            change = int(d_long - d_short)
        else:
            change = 0

        # Net Commercial
        if comm_long_col:
            comm_long = self._safe_float(df[comm_long_col].iloc[-1])
            comm_short = self._safe_float(df[comm_short_col].iloc[-1]) if comm_short_col else 0.0
            net_comm = comm_long - comm_short
        elif (
            "dealer_positions_long_all" in df.columns and "dealer_positions_short_all" in df.columns
        ):
            comm_long = self._safe_float(df["dealer_positions_long_all"].iloc[-1])
            comm_short = self._safe_float(df["dealer_positions_short_all"].iloc[-1])
            net_comm = comm_long - comm_short
        else:
            net_comm = 0.0

        # OI weekly change %
        if len(df) >= 2 and oi_col:
            prev_oi = self._safe_float(df[oi_col].iloc[-2])
            oi_change_pct = ((oi - prev_oi) / prev_oi * 100) if prev_oi else 0.0
        elif "change_in_open_interest_all" in df.columns:
            d_oi = self._safe_float(df["change_in_open_interest_all"].iloc[-1])
            prev_oi = oi - d_oi
            oi_change_pct = ((oi - prev_oi) / prev_oi * 100) if prev_oi else 0.0
        else:
            oi_change_pct = 0.0

        # Historical percentile window:
        # Use up to 104 trailing weekly snapshots to stabilize percentile context while
        # preserving recent regime relevance. A warning is emitted if fewer than 52 are available.
        history_points = 0
        if (long_col or (fin_spec_long_cols and fin_spec_short_cols)) and len(df) >= 2:
            if long_col:
                all_longs = df[long_col].apply(self._safe_float)
                all_shorts = (
                    df[short_col].apply(self._safe_float)
                    if short_col
                    else pd.Series(0.0, index=df.index)
                )
            else:
                all_longs = (
                    df[fin_spec_long_cols].apply(lambda col: col.map(self._safe_float)).sum(axis=1)
                )
                all_shorts = (
                    df[fin_spec_short_cols].apply(lambda col: col.map(self._safe_float)).sum(axis=1)
                )
            all_nets = all_longs - all_shorts
            all_nets = all_nets.tail(TARGET_PERCENTILE_HISTORY_WEEKS)
            history_points = len(all_nets)
            rank = (all_nets < net).sum()
            percentile = int(round(rank / len(all_nets) * 100))
        else:
            percentile = 50
            history_points = 0

        return net, pct, change, net_comm, oi, oi_change_pct, percentile, history_points

    def _extract_from_precomputed(self, raw: Dict):
        """Extract metrics from pre-computed mock/simplified data dict."""
        net = raw.get("net_non_commercial", raw.get("noncomm_net", 0))
        pct = raw.get("pct_oi_non_com", raw.get("noncomm_pct_oi", 20.0))
        change = raw.get("change", raw.get("change_noncomm_net", 0))
        net_comm = raw.get("net_commercial", 0)
        oi = raw.get("open_interest", 0)
        oi_change_pct = raw.get("oi_change_pct", 0.0)
        percentile = raw.get("historical_percentile", 50)
        history_points = self._safe_int(raw.get("history_points", 1), 1)

        # Sanitise NaN/None
        net = self._safe_int(net)
        pct = self._safe_float(pct, 0.0)
        change = self._safe_int(change)
        net_comm = self._safe_int(net_comm)
        oi = self._safe_int(oi)
        oi_change_pct = self._safe_float(oi_change_pct, 0.0)

        return net, pct, change, net_comm, oi, oi_change_pct, percentile, history_points

    # ── Signal generation ────────────────────────────────────────────────

    def to_signals(self, biases: Dict[str, COTBias]) -> List[Signal]:
        """Convert COT biases to trading Signals for aggregator."""
        signals = []
        for bias in biases.values():
            direction = (
                Direction.LONG
                if bias.bias == "bullish"
                else (Direction.SHORT if bias.bias == "bearish" else Direction.NEUTRAL)
            )
            if direction != Direction.NEUTRAL:
                signals.append(
                    Signal(
                        coin=bias.asset,
                        direction=direction,
                        confidence=bias.confidence,
                        source="macro/cot",
                        metadata=bias.metadata,
                    )
                )
        return signals

    def generate_cot_signal(
        self, asset: str, cot_bias: COTBias, technical_context: dict | None = None
    ) -> Signal:
        """Precise signal generation with setup confluence + IPDA (from PR #7).
        Stubs technical confluence for 4H/1H setups per philosophy.
        """
        technical_context = technical_context or {}
        retracement_conf = technical_context.get("has_75_retracement", True)
        ipda_phase = technical_context.get("ipda_phase", "retracement")
        overall_conf = min(
            cot_bias.confidence * (cot_bias.metadata.get("fits_weighted_score", 50) / 100), 0.95
        )

        direction = Direction.LONG if cot_bias.bias == "bullish" else Direction.SHORT
        metadata = {
            **cot_bias.metadata,
            "75_retracement": retracement_conf,
            "ipda_phase": ipda_phase,
            "confluence": " + ".join(self.setups),
            "bias_score_100": cot_bias.metadata.get("fits_weighted_score", 50),
        }
        return Signal(
            coin=asset,
            direction=direction,
            confidence=overall_conf,
            source="macro/cot_75_retrace",
            metadata=metadata,
        )

    # ── Internal helpers ─────────────────────────────────────────────────

    def _infer_market_regime(self, change: int, pct_oi: float) -> str:
        if abs(change) > 2500 or abs(pct_oi) > 22:
            return "high_vol"
        if change >= 0:
            return "bull"
        return "bear"

    @staticmethod
    def _position_intensity(pct_abs: float) -> str:
        if pct_abs >= 15.0:
            return "heavily"
        if pct_abs >= 5.0:
            return "moderately"
        if pct_abs > 0.0:
            return "slightly"
        return "near-neutral"

    @staticmethod
    def _percentile_band(percentile: int) -> str:
        if percentile >= 85:
            return "very extreme long"
        if percentile >= 70:
            return "moderately extreme long"
        if percentile <= 15:
            return "very extreme short"
        if percentile <= 30:
            return "moderately extreme short"
        return "balanced positioning"

    def _first_existing(self, df: pd.DataFrame, names: list[str]) -> str | None:
        for name in names:
            if name in df.columns:
                return name
        return None

    @staticmethod
    def _safe_float(val: Any, default: float = 0.0) -> float:
        if val is None:
            return default
        try:
            f = float(val)
            return default if math.isnan(f) else f
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_int(val: Any, default: int = 0) -> int:
        if val is None:
            return default
        try:
            f = float(val)
            return default if math.isnan(f) else int(f)
        except (ValueError, TypeError):
            return default


if __name__ == "__main__":
    import logging as _logging

    _logging.basicConfig(level=_logging.DEBUG, format="%(levelname)s: %(message)s")
    from trading.crypto.cot.cot_fetcher import fetch_latest_cot

    data = fetch_latest_cot(debug=True)
    analyzer = COTAnalyzer()
    biases = analyzer.analyze(data)
    signals = analyzer.to_signals(biases)
    for k, b in biases.items():
        print(f"\n{k}: {b.bias.upper()} (conf={b.confidence:.0%})")
        print(f"  Net Non-Comm: {b.net_non_commercial:+,}")
        print(f"  Net Commercial: {b.net_commercial:+,}")
        print(f"  OI: {b.open_interest:,} (Δ {b.oi_change_pct:+.1f}%)")
        print(f"  Percentile: {b.historical_percentile}")
    print(f"\nGenerated Signals: {len(signals)}")
