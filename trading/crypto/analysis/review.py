"""BTC/ETH position review — momentum + COT + regime + options (long & short)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from trading.crypto.analysis.constants import (
    BEARISH_REGIME_PHASES,
    BULLISH_REGIME_PHASES,
    OPTIONS_INSTRUMENT,
    PERP_INSTRUMENT,
    REGIME_OPTIONS_WITHOUT_TRADEABLE,
)
from trading.crypto.analysis.options_bridge import summarize_options_opportunity
from trading.crypto.analysis.regime import RegimeAssessment, assess_regime
from trading.crypto.analysis.regime_config import load_regime_config
from trading.crypto.analysis.regime_thesis import (
    RegimeThesisStore,
    apply_thesis_to_recommendation,
    reconcile_regime_thesis,
)
from trading.crypto.cot.context import cot_side_from_bias, fetch_cot_biases
from trading.crypto.momentum.service import MomentumMarketService, MomentumTimeframes
from trading.crypto.theory_v2 import build_signals_for_coins


@dataclass(frozen=True)
class PositionRecommendation:
    coin: str
    direction: str | None
    action: str
    confidence: float
    primary_source: str
    entry_zone: list[float] | None
    invalidation: float | None
    targets: list[float]
    reasons: list[str]
    blockers: list[str]
    momentum_score: int | None
    cot_bias: str | None
    theory_stage: str | None
    regime_phase: str | None = None
    playbook: str | None = None
    options_summary: dict[str, Any] | None = None
    instruments: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "coin": self.coin,
            "direction": self.direction,
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "primary_source": self.primary_source,
            "entry_zone": self.entry_zone,
            "invalidation": self.invalidation,
            "targets": self.targets,
            "reasons": self.reasons,
            "blockers": self.blockers,
            "momentum_score": self.momentum_score,
            "cot_bias": self.cot_bias,
            "theory_stage": self.theory_stage,
            "regime_phase": self.regime_phase,
            "playbook": self.playbook,
            "instruments": self.instruments or [],
        }
        if self.options_summary is not None:
            out["options"] = self.options_summary
        return out


def coin_to_symbol(coin: str) -> str:
    normalized = coin.upper()
    return normalized if normalized.endswith("USDT") else f"{normalized}USDT"


def best_momentum_plan(
    plans: list[dict[str, Any]],
    *,
    cot_side: str | None = None,
) -> dict[str, Any] | None:
    """Pick best plan; prefer side aligned with COT when scores are close."""
    tradeable = [p for p in plans if p.get("tradeable")]
    confirmed = [p for p in plans if p.get("setup_status") == "confirmed"]
    pending = [p for p in plans if p.get("setup_status") == "pending"]

    def _rank(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            pool,
            key=lambda p: (
                int(p.get("confidence_score", 0) or 0)
                + (6 if cot_side and p.get("side") == cot_side else 0),
            ),
            reverse=True,
        )

    for pool in (_rank(tradeable), _rank(confirmed), _rank(pending)):
        if pool:
            return pool[0]
    return None


def _cot_bias_to_options_bias(cot_side: str | None, direction: str | None) -> str:
    if cot_side == "long" or direction == "long":
        return "bullish"
    if cot_side == "short" or direction == "short":
        return "bearish"
    return "neutral"


def format_options_display(options: dict[str, Any] | None) -> str | None:
    if not options or options.get("status") != "ready":
        return None
    strat = options.get("strategy") or "—"
    m = options.get("metrics") or {}
    parts = [str(strat)]
    if m.get("expected_value") is not None:
        parts.append(f"EV={m['expected_value']}")
    if m.get("pop_pct") is not None:
        parts.append(f"POP={m['pop_pct']}%")
    if m.get("probability_of_touch_pct") is not None:
        parts.append(f"touch={m['probability_of_touch_pct']}%")
    if options.get("trade_decision"):
        parts.append(f"[{options['trade_decision']}]")
    return " · ".join(parts)


def _instruments_for(
    *,
    direction: str | None,
    action: str,
    has_options: bool,
) -> list[str]:
    if action == "stand_aside" or not direction:
        return []
    out = [PERP_INSTRUMENT]
    if has_options:
        out.append(OPTIONS_INSTRUMENT)
    return out


def _scan_options_for_coin(
    coin: str,
    *,
    directional_bias: str,
    momentum_context: dict[str, Any],
    require_tradeable: bool,
    days_to_exp: int,
    account_equity: float,
    risk_pct: float,
    options_source: str,
) -> dict[str, Any] | None:
    try:
        from options.analyzer import OptionsAnalyzer

        payload = OptionsAnalyzer(fetcher_source=options_source).scan_crypto_opportunities(
            coins=[coin],
            days_to_exp=days_to_exp,
            account_equity=account_equity,
            risk_pct=risk_pct,
            require_tradeable=require_tradeable,
            directional_bias_override=directional_bias,
        )
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}

    opp = (payload.get("opportunities") or {}).get(coin) or {}
    summary = summarize_options_opportunity(opp)
    if summary.get("status") != "ready":
        summary["momentum"] = momentum_context
    return summary


def _resolve_from_regime(
    regime: RegimeAssessment,
    *,
    cot_conf: float,
    best: dict[str, Any] | None,
) -> tuple[str | None, str, float, str, list[float] | None, float | None, list[float], str]:
    """Returns direction, action, confidence, source, entry, inv, targets, extra_reason."""
    score = (best or {}).get("confidence_score", 0) or 0
    conf = max(cot_conf, regime.confidence, score / 100.0)

    if regime.bias == "bearish" and regime.phase in BEARISH_REGIME_PHASES:
        direction = "short"
        entry = list(regime.supply_zone or (best or {}).get("entry_zone") or [])
        inv = (best or {}).get("invalidation")
        targets = [v for v in ((best or {}).get("tp1"), (best or {}).get("tp2")) if v is not None]
        action = "watch"
        source = "cot+regime"
        extra = regime.continuation_trigger or "Await trigger in supply zone"
        if best and best.get("tradeable") and best.get("side") == "short":
            action, source = "enter", "momentum+cot+regime"
        return direction, action, conf, source, entry or None, inv, targets, extra

    if regime.bias == "bullish" and regime.phase in BULLISH_REGIME_PHASES:
        direction = "long"
        entry = list(regime.supply_zone or (best or {}).get("entry_zone") or [])
        inv = (best or {}).get("invalidation")
        targets = [v for v in ((best or {}).get("tp1"), (best or {}).get("tp2")) if v is not None]
        action = "watch"
        source = "cot+regime"
        extra = regime.continuation_trigger or "Await trigger in demand zone"
        if best and best.get("tradeable") and best.get("side") == "long":
            action, source = "enter", "momentum+cot+regime"
        return direction, action, conf, source, entry or None, inv, targets, extra

    return None, "stand_aside", 0.0, "none", None, None, [], ""


def review_positions(
    coins: list[str],
    *,
    account_equity: float = 10_000.0,
    risk_pct: float = 0.005,
    timeframes: MomentumTimeframes | None = None,
    momentum_service: MomentumMarketService | None = None,
    include_options: bool = True,
    options_days_to_exp: int = 30,
    options_source: str = "deribit",
) -> dict[str, Any]:
    """Canonical BTC/ETH analysis: enter / watch / stand_aside per coin."""
    coin_list = [coin.upper() for coin in coins]
    symbols = [coin_to_symbol(coin) for coin in coin_list]

    service = momentum_service or MomentumMarketService()
    tf = timeframes or service.parse_timeframes("4h,1h")
    momentum_payload = service.scan_live(
        symbols=symbols,
        timeframes=tf,
        account_equity=account_equity,
        risk_pct=risk_pct,
    )

    cot_biases = fetch_cot_biases()
    _, theory_decisions = build_signals_for_coins(coin_list)
    theory_by_coin = {decision.coin: decision for decision in theory_decisions}
    regime_cfg = load_regime_config()
    thesis_store = RegimeThesisStore()

    recommendations: list[dict[str, Any]] = []

    for coin in coin_list:
        symbol = coin_to_symbol(coin)
        symbol_result = momentum_payload["results"].get(symbol, {})
        all_plans = symbol_result.get("plans", [])
        tradeable_plans = symbol_result.get("tradeable") or []
        cot_bias = cot_biases.get(coin)
        cot_side = cot_side_from_bias(cot_bias)
        cot_conf = float(cot_bias.confidence) if cot_bias else 0.0

        best = best_momentum_plan(tradeable_plans or all_plans, cot_side=cot_side)
        frames = service.load_live_frames(symbol, tf)
        regime = assess_regime(
            daily=frames["daily"],
            setup=frames["setup"],
            cot_bias=cot_bias,
            best_plan=best,
        )

        theory = theory_by_coin.get(coin)
        theory_fired = theory is not None and theory.signal is not None
        theory_stage = theory.stage if theory else "unknown"
        theory_reason = theory.reason if theory else "not evaluated"

        reasons: list[str] = [f"Regime: {regime.phase} — {regime.playbook}"]
        blockers: list[str] = []

        if best:
            overlay = (best.get("diagnostics") or {}).get("cot_overlay") or {}
            if overlay.get("aligned"):
                reasons.append(
                    f"Momentum {best['side']} (score {best['confidence_score']}) + COT aligned"
                )
            elif best.get("tradeable"):
                reasons.append(f"Momentum {best['side']} tradeable (score {best['confidence_score']})")
            else:
                blockers.append(
                    f"Momentum {best['side']} {best.get('setup_status')} "
                    f"score {best['confidence_score']} below threshold"
                )
        else:
            blockers.append("No momentum setup on 4H/1H")

        if cot_side and cot_bias:
            reasons.append(
                f"COT: {cot_bias.bias} (conf {cot_conf:.0%}, P{cot_bias.historical_percentile})"
            )
        if theory_fired and theory and theory.signal:
            reasons.append(f"Theory v2 fired {theory.signal.direction.value}")
        elif theory_stage != "fired":
            blockers.append(f"Theory v2: {theory_stage} — {theory_reason}")

        direction: str | None = None
        action = "stand_aside"
        confidence = 0.0
        primary_source = "none"
        entry_zone = None
        invalidation = None
        targets: list[float] = []

        if best and best.get("tradeable"):
            direction = str(best["side"])
            action = "enter"
            confidence = max(cot_conf, best["confidence_score"] / 100.0, regime.confidence)
            primary_source = "momentum+cot+regime"
            entry_zone = list(best.get("entry_zone") or [])
            invalidation = best.get("invalidation")
            targets = [v for v in (best.get("tp1"), best.get("tp2"), best.get("tp3")) if v is not None]
        elif theory_fired and theory and theory.signal:
            signal = theory.signal
            direction = signal.direction.value
            action = "enter"
            confidence = max(cot_conf, float(signal.confidence), regime.confidence)
            primary_source = "theory_v2+regime"
            ep = signal.metadata.get("entry_price")
            entry_zone = [ep] if ep else None
            invalidation = signal.invalidation
            targets = list(signal.targets or [])
        else:
            rd, ra, rc, rs, re, ri, rt, extra = _resolve_from_regime(
                regime, cot_conf=cot_conf, best=best
            )
            if rd:
                direction, action, confidence, primary_source = rd, ra, rc, rs
                entry_zone, invalidation, targets = re, ri, rt
                if extra:
                    reasons.append(extra)
            elif best and best.get("setup_status") == "confirmed" and cot_side == best.get("side"):
                direction = str(best["side"])
                action = "watch"
                confidence = max(cot_conf, best["confidence_score"] / 100.0, regime.confidence)
                primary_source = "momentum+cot_watch"
                entry_zone = list(best.get("entry_zone") or [])
                invalidation = best.get("invalidation")
                targets = [v for v in (best.get("tp1"), best.get("tp2")) if v is not None]
                reasons.append("Confirmed setup — awaiting tradeable score")

        options_summary = None
        if include_options and direction in {"long", "short"}:
            options_bias = _cot_bias_to_options_bias(cot_side, direction)
            allow_regime = regime.phase in REGIME_OPTIONS_WITHOUT_TRADEABLE
            options_summary = _scan_options_for_coin(
                coin,
                directional_bias=options_bias,
                momentum_context={
                    "side": direction,
                    "tradeable": bool(best and best.get("tradeable")),
                    "regime_phase": regime.phase,
                },
                require_tradeable=not allow_regime,
                days_to_exp=options_days_to_exp,
                account_equity=account_equity,
                risk_pct=risk_pct,
                options_source=options_source,
            )
            if options_summary and options_summary.get("status") == "ready":
                reasons.append(f"Options ({options_source}): {options_summary.get('strategy')}")
                confidence = max(confidence, 0.72)

        instruments = _instruments_for(
            direction=direction,
            action=action,
            has_options=bool(options_summary and options_summary.get("status") == "ready"),
        )

        trigger_frame = frames.get("trigger")
        price = None
        if trigger_frame is not None and not getattr(trigger_frame, "empty", True):
            price = float(trigger_frame["close"].iloc[-1])

        thesis_overlay = reconcile_regime_thesis(
            coin=coin,
            regime=regime,
            cot_bias_label=cot_bias.bias if cot_bias else None,
            price=price,
            invalidation=invalidation,
            store=thesis_store,
            max_age_hours=regime_cfg.thesis_max_age_hours,
        )
        rec_dict = PositionRecommendation(
            coin=coin,
            direction=direction,
            action=action,
            confidence=confidence,
            primary_source=primary_source,
            entry_zone=entry_zone,
            invalidation=invalidation,
            targets=targets,
            reasons=reasons,
            blockers=blockers,
            momentum_score=int(best["confidence_score"]) if best else None,
            cot_bias=cot_bias.bias if cot_bias else None,
            theory_stage=theory_stage,
            regime_phase=regime.phase,
            playbook=regime.playbook,
            options_summary=options_summary,
            instruments=instruments,
        ).to_dict()
        recommendations.append(apply_thesis_to_recommendation(rec_dict, thesis_overlay))

    per_coin_momentum = {
        coin: momentum_payload["results"].get(coin_to_symbol(coin), {}) for coin in coin_list
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "crypto_analysis_v4",
        "coins": coin_list,
        "summary": {
            "actionable_count": sum(1 for r in recommendations if r["action"] == "enter"),
            "watch_count": sum(1 for r in recommendations if r["action"] == "watch"),
            "stand_aside_count": sum(1 for r in recommendations if r["action"] == "stand_aside"),
        },
        "momentum_scan": {
            **momentum_payload.get("summary", {}),
            "per_coin": {
                coin: {
                    "tradeable": per_coin_momentum[coin].get("tradeable", []),
                    "top_scores": [
                        int(p.get("confidence_score", 0) or 0)
                        for p in (per_coin_momentum[coin].get("plans") or [])[:2]
                    ],
                }
                for coin in coin_list
            },
        },
        "recommendations": recommendations,
        "actionable": [r for r in recommendations if r["action"] in {"enter", "watch"}],
        "regime_thesis": {
            "state_path": str(thesis_store.path),
            "active_count": sum(
                1
                for t in (thesis_store.payload.get("theses") or {}).values()
                if isinstance(t, dict) and t.get("state") == "active"
            ),
        },
    }