"""Hermes Agent integration layer for Nave.

This module exposes MCP/gateway-friendly tool handlers with structured JSON
outputs so autonomous agents can consume deterministic responses.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from core.config import CliDefaults
from core.exceptions import HermesIntegrationError
from core.logger import configure_logger
from trading.client import HyperliquidClient
from trading.cot.cot_analyzer import COTAnalyzer
from trading.cot.cot_fetcher import build_cot_sections_from_datasets, fetch_latest_cot
from trading.cot.cot_position_generator import COTPositionGenerator

logger = configure_logger(__name__)


def _default_reports_dir() -> Path:
    """Project-root-relative directory for persisted daily scans."""
    return Path(__file__).resolve().parent.parent / "var" / "reports"


def _to_jsonable(value: Any) -> Any:
    """Convert dataclasses and nested objects into JSON-serializable values."""
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


class HermesNaveIntegration:
    """Dispatches Nave tools for Hermes via MCP and gateway-compatible contracts."""

    def __init__(self, defaults: CliDefaults | None = None):
        self.defaults = defaults or CliDefaults()

    def list_tools(self) -> dict[str, Any]:
        """Return MCP-compatible tool metadata for Hermes skill registration."""
        return {
            "skill": {
                "name": "nave_trading",
                "version": "1.0.0",
                "description": "Nave COT analysis and weekly planning tools",
            },
            "tools": [
                {
                    "name": "cot_report",
                    "description": "Return latest COT report with section metrics and bias.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "coins": {"type": "string", "default": self.defaults.coins},
                            "include_micro": {"type": "boolean", "default": False},
                            "report_type": {
                                "type": "string",
                                "enum": ["futures_only", "futures_and_options", "legacy_combined"],
                                "default": "futures_and_options",
                            },
                        },
                    },
                },
                {
                    "name": "cot_history",
                    "description": "Return historical COT variation report for N months.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "months": {"type": "integer", "minimum": 1, "maximum": 12},
                            "coins": {"type": "string", "default": self.defaults.coins},
                            "include_micro": {"type": "boolean", "default": False},
                            "report_type": {
                                "type": "string",
                                "enum": ["futures_only", "futures_and_options", "legacy_combined"],
                                "default": "futures_and_options",
                            },
                        },
                        "required": ["months"],
                    },
                },
                {
                    "name": "weekly_plan",
                    "description": "Generate weekly trading plan with actionable setups.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "capital": {"type": "number", "default": self.defaults.capital_usd},
                            "wallet": {"type": "string", "default": self.defaults.wallet},
                            "coins": {"type": "string", "default": self.defaults.coins},
                            "include_micro": {"type": "boolean", "default": False},
                        },
                    },
                },
                {
                    "name": "theory_v2_scan",
                    "description": (
                        "Daily top-down theory v2 scan — evaluates weekly momentum → "
                        "daily confirm → climax cooldown → chase gate → 4H → 1H for each "
                        "coin and returns the full decision trace (stage, reason, bias, "
                        "fired?). The agent uses this to decide whether to open positions."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "coins": {"type": "string", "default": self.defaults.coins},
                        },
                    },
                },
                {
                    "name": "strategy_context",
                    "description": (
                        "Return the current theory v2 configuration, pooled backtest "
                        "metrics, regime coverage, and known blind spots. Use alongside "
                        "theory_v2_scan so the agent can explain why a decision was made."
                    ),
                    "input_schema": {"type": "object", "properties": {}},
                },
                {
                    "name": "recommend_position",
                    "description": (
                        "Size a position from a theory_v2_scan fired signal. Takes the "
                        "coin's scan entry (as returned by theory_v2_scan) plus capital "
                        "and leverage, and returns notional, coin quantity, risk in USD, "
                        "reward at ZC1/ZC2, and a human-readable order summary."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "coin_scan": {
                                "type": "object",
                                "description": "One coin entry from theory_v2_scan['coins'][COIN]",
                            },
                            "capital_usd": {"type": "number", "minimum": 0},
                            "leverage": {"type": "number", "minimum": 1, "maximum": 50},
                            "risk_pct": {
                                "type": "number",
                                "minimum": 0.001,
                                "maximum": 0.1,
                                "default": 0.01,
                            },
                        },
                        "required": ["coin_scan", "capital_usd"],
                    },
                },
                {
                    "name": "scan_history",
                    "description": (
                        "Return the last N daily scan reports from var/reports/. Lets the "
                        "agent see whether today's stand-aside is new or the continuation "
                        "of a multi-day regime."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "days": {"type": "integer", "minimum": 1, "maximum": 90, "default": 7},
                        },
                    },
                },
            ],
        }

    def cot_report(
        self,
        *,
        coins: str = "BTC ETH",
        include_micro: bool = False,
        report_type: str = "futures_and_options",
    ) -> dict[str, Any]:
        """Return latest COT bias and section metrics for requested assets."""
        coin_list = [coin.strip().upper() for coin in coins.split() if coin.strip()]
        if not coin_list:
            raise HermesIntegrationError("At least one coin is required for cot_report")

        primary_report_type = (
            "futures_only" if report_type == "futures_only" else "futures_and_options"
        )

        cot_data_futures_only = fetch_latest_cot(
            report_type="futures_only",
            include_micro=include_micro,
            debug=False,
        )
        cot_data_futures_and_options = fetch_latest_cot(
            report_type="futures_and_options",
            include_micro=include_micro,
            debug=False,
        )

        analyzer = COTAnalyzer()
        biases = analyzer.analyze(
            cot_data_futures_only
            if primary_report_type == "futures_only"
            else cot_data_futures_and_options
        )
        cot_sections = build_cot_sections_from_datasets(
            futures_only_data=cot_data_futures_only,
            combined_data=cot_data_futures_and_options,
        )

        payload: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_type": primary_report_type,
            "coins": {},
        }

        for coin in coin_list:
            bias = biases.get(coin)
            if bias is None:
                continue
            metadata = bias.metadata
            payload["coins"][coin] = {
                "bias": bias.bias,
                "confidence": round(bias.confidence, 4),
                "bias_strength": metadata.get("bias_strength"),
                "fits_score": metadata.get("fits_weighted_score"),
                "net_non_commercial": bias.net_non_commercial,
                "net_commercial": bias.net_commercial,
                "open_interest": bias.open_interest,
                "weekly_change": bias.weekly_change,
                "oi_change_pct": bias.oi_change_pct,
                "historical_percentile": bias.historical_percentile,
                "report_date": metadata.get("report_date"),
                "as_of_date": metadata.get("as_of_date"),
                "release_date": metadata.get("release_date"),
                "cot_interpretation": metadata.get("cot_interpretation"),
                "futures_only": cot_sections.get(coin, {}).get("futures_only"),
                "options": cot_sections.get(coin, {}).get("options"),
                "futures_and_options": cot_sections.get(coin, {}).get("combined"),
                "options_validation": cot_sections.get(coin, {}).get("options_validation"),
            }

        return payload

    def cot_history(
        self,
        *,
        months: int,
        coins: str = "BTC ETH",
        include_micro: bool = False,
        report_type: str = "futures_and_options",
    ) -> dict[str, Any]:
        """Return historical variation payload for calendar windows."""
        if not 1 <= months <= 12:
            raise HermesIntegrationError("months must be between 1 and 12")

        history_weeks = max(16, months * 6 + 4)
        coin_list = [coin.strip().upper() for coin in coins.split() if coin.strip()]

        historical_data = fetch_latest_cot(
            report_type="futures_only" if report_type == "futures_only" else "futures_and_options",
            include_micro=include_micro,
            debug=False,
            history_weeks=history_weeks,
        )
        filtered = {coin: historical_data[coin] for coin in coin_list if coin in historical_data}

        historical = COTAnalyzer().generate_historical_variation_report(
            months=months, cot_data=filtered
        )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_type": "cot_historical_variation",
            "months": months,
            "as_of_date": historical.get("as_of_date", "N/A"),
            "coins": historical.get("assets", {}),
            "observations": historical.get("observations", []),
            "markdown": historical.get("markdown", ""),
        }

    def weekly_plan(
        self,
        *,
        capital: float = 2000.0,
        wallet: str = "hermes",
        coins: str = "BTC ETH",
        include_micro: bool = False,
    ) -> dict[str, Any]:
        """Generate structured weekly plan output from real COT + 4H structure."""
        if capital <= 0:
            raise HermesIntegrationError("capital must be positive")

        coin_list = [coin.strip().upper() for coin in coins.split() if coin.strip()]
        cot_data_futures_only = fetch_latest_cot(
            report_type="futures_only",
            include_micro=include_micro,
            debug=False,
        )
        cot_data_futures_and_options = fetch_latest_cot(
            report_type="futures_and_options",
            include_micro=include_micro,
            debug=False,
        )
        sections = build_cot_sections_from_datasets(
            futures_only_data=cot_data_futures_only,
            combined_data=cot_data_futures_and_options,
        )

        market_client = HyperliquidClient(wallet_name=wallet, testnet=True)
        market_data_4h: dict[str, dict[str, Any]] = {}

        analyzer = COTAnalyzer()
        biases = analyzer.analyze(cot_data_futures_and_options)
        for coin in coin_list:
            bias = biases.get(coin)
            if bias is None:
                continue
            as_of_raw = str(bias.metadata.get("as_of_date") or date.today().isoformat())
            market_data_4h[coin] = self._market_structure_4h(
                client=market_client,
                coin=coin,
                as_of_date=as_of_raw,
            )

        coin_sections = {coin: sections[coin] for coin in coin_list if coin in sections}
        plans = COTPositionGenerator(default_risk_pct=0.01).generate_weekly_plan(
            coin_sections,
            market_data_4h,
        )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "capital_usd": capital,
            "wallet": wallet,
            "coins": coin_list,
            "plan": _to_jsonable(plans),
        }

    def theory_v2_scan(
        self,
        *,
        coins: str = "BTC ETH",
    ) -> dict[str, Any]:
        """Run the theory v2 engine on each coin and return the full decision trace.

        Each coin receives a decision record with ``stage`` (where evaluation
        stopped), ``reason`` (human-readable explanation), ``bias``, and — when
        a signal fires — the full entry/stop/target geometry. The caller
        (Hermes / MCP client) uses this to decide whether to open positions.
        """
        coin_list = [coin.strip().upper() for coin in coins.split() if coin.strip()]
        if not coin_list:
            raise HermesIntegrationError("At least one coin is required for theory_v2_scan")

        from trading.theory_v2 import build_signals_for_coins  # local to keep import light

        signals, decisions = build_signals_for_coins(coin_list)

        coin_payload: dict[str, Any] = {}
        for decision in decisions:
            entry: dict[str, Any] = {
                "coin": decision.coin,
                "bias": decision.bias,
                "stage": decision.stage,
                "reason": decision.reason,
                "daily_confirmed": decision.daily_confirmed,
                "setup_valid": decision.setup_valid,
                "fired": decision.signal is not None,
            }
            if decision.signal is not None:
                sig = decision.signal
                meta = sig.metadata or {}
                entry["signal"] = {
                    "direction": sig.direction.value,
                    "confidence": sig.confidence,
                    "entry_price": meta.get("entry_price"),
                    "stop_loss": sig.invalidation,
                    "targets": list(sig.targets),
                    "zc1_rr": meta.get("zc1_rr"),
                    "stop_distance_pct": meta.get("stop_distance"),
                    "weekly_velocity_atr": meta.get("weekly_velocity_atr"),
                    "daily_atr_14": meta.get("daily_atr_14"),
                    "retrace_fraction": meta.get("retrace_fraction"),
                    "bias_source": meta.get("bias_source", "momentum"),
                    "range_breakout": meta.get("range_breakout"),
                    "bias_timeframe": sig.bias_timeframe.value if sig.bias_timeframe else None,
                    "setup_timeframe": sig.setup_timeframe.value if sig.setup_timeframe else None,
                    "trigger_timeframe": sig.trigger_timeframe.value if sig.trigger_timeframe else None,
                }
            coin_payload[decision.coin] = entry

        fires = [d.coin for d in decisions if d.signal is not None]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "coins": coin_payload,
            "summary": {
                "evaluated": [d.coin for d in decisions],
                "fires": fires,
                "fire_count": len(fires),
                "evaluation_errors": [c for c in coin_list if c not in {d.coin for d in decisions}],
            },
        }

    def strategy_context(self) -> dict[str, Any]:
        """Return the current theory v2 configuration and pooled backtest summary.

        Static summary of iter 14 — the converged configuration merged into
        main. Use together with ``theory_v2_scan`` so the agent can cite the
        edge, the regime coverage, and the known blind spots when explaining
        its recommendation.
        """
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "theory_v2.iter_18",
            "summary": (
                "Top-down high-momentum pipeline: weekly velocity gate (with "
                "range-breakout fallback) → daily confirmation → climax cooldown "
                "→ chase gate → 4H setup → 1H trigger. Iter 14 converged the "
                "momentum gate; iter 18 added range-breakout fallback for the "
                "iter 16 consolidation blind spot."
            ),
            "pipeline": [
                {"timeframe": "1W", "gate": "momentum_bias", "role": "direction"},
                {"timeframe": "1W", "gate": "range_breakout_bias", "role": "direction_fallback"},
                {"timeframe": "1W", "gate": "weekly_cot_filter", "role": "positioning"},
                {"timeframe": "1D", "gate": "daily_confirms", "role": "confirmation"},
                {"timeframe": "1D", "gate": "climax_cooldown", "role": "risk_gate"},
                {"timeframe": "1D", "gate": "chase_gate", "role": "entry_band"},
                {"timeframe": "4H", "gate": "four_h_setup_valid", "role": "structure"},
                {"timeframe": "1H", "gate": "one_h_entry", "role": "trigger"},
            ],
            "parameters": {
                "weekly_momentum": {
                    "min_velocity_atrs": 1.2,
                    "lookback_weeks": 4,
                    "atr_window": 8,
                },
                "range_breakout": {
                    "range_window": 8,
                    "max_range_atrs": 1.5,
                    "breakout_buffer_atrs": 0.5,
                    "atr_window": 8,
                },
                "daily_confirm": {"sma_period": 10},
                "chase_gate": {"min_retrace": 0.50, "max_retrace": 0.95},
                "climax_cooldown": {"atr_multiple": 3.0, "cooldown_bars": 5},
            },
            "backtest_metrics": {
                "window": "2017-10 → 2025-12 (9 regime periods, BTC + ETH pooled)",
                "pooled": {
                    "fires": 47,
                    "win_rate": 0.784,
                    "avg_r_per_trade": 1.19,
                    "total_r": 44.14,
                },
                "per_coin": {
                    "BTC": {"fires": 22, "win_rate": 0.778, "avg_r": 1.155, "total_r": 20.79},
                    "ETH": {"fires": 25, "win_rate": 0.789, "avg_r": 1.229, "total_r": 23.35},
                },
                "regime_coverage": {
                    "2017-2018-cycle": 9.90,
                    "2020-ATH": None,
                    "2022-bear": 5.06,
                    "2023-recovery": 9.22,
                    "2024-2025-bull": 1.70,
                },
                "iter_18_delta_vs_iter_14": {
                    "btc_fires": "+1",
                    "btc_total_r": "+1.60",
                    "eth": "unchanged",
                    "pooled_total_r": "+1.60",
                },
            },
            "known_blind_spots": [
                {
                    "name": "cot_extreme_block",
                    "description": (
                        "Weekly COT filter rejects setups when speculator "
                        "positioning is at 95th+ percentile, even if momentum "
                        "qualifies. By design — reversal-risk gate."
                    ),
                    "iter_ref": "iter_11",
                },
                {
                    "name": "range_breakout_partial",
                    "description": (
                        "Iter 18 adds a range-breakout fallback that catches "
                        "consolidation breakouts the momentum gate misses, "
                        "but it requires a flat prior range (≤ 1.5 ATRs). "
                        "Very deep, extended consolidations may still fire "
                        "late. COT filter also still applies to breakouts — "
                        "extreme positioning blocks them too."
                    ),
                    "iter_ref": "iter_18",
                },
            ],
            "iter_history_path": "docs/analysis/iterations/",
            "engine_source": "trading/theory_v2.py",
        }

    def recommend_position(
        self,
        *,
        coin_scan: dict[str, Any],
        capital_usd: float,
        leverage: float = 10.0,
        risk_pct: float = 0.01,
    ) -> dict[str, Any]:
        """Turn a fired scan entry into a concrete, sized position recommendation.

        ``coin_scan`` is one entry from ``theory_v2_scan(...)['coins'][COIN]``.
        The caller passes the user's ``capital_usd`` and desired ``leverage``;
        ``risk_pct`` is the fraction of capital to risk to stop-loss (default
        1% per the COT plan generator).
        """
        if capital_usd <= 0:
            raise HermesIntegrationError("capital_usd must be positive")
        if leverage < 1 or leverage > 50:
            raise HermesIntegrationError("leverage must be between 1 and 50")
        if not 0.001 <= risk_pct <= 0.1:
            raise HermesIntegrationError("risk_pct must be in [0.001, 0.1]")
        if not isinstance(coin_scan, dict):
            raise HermesIntegrationError("coin_scan must be a dict from theory_v2_scan output")

        if not coin_scan.get("fired"):
            return {
                "recommendation": "stand_aside",
                "reason": coin_scan.get(
                    "reason", "scan did not fire — no actionable setup"
                ),
                "stage": coin_scan.get("stage"),
                "bias": coin_scan.get("bias"),
            }

        sig = coin_scan.get("signal") or {}
        entry = sig.get("entry_price")
        stop = sig.get("stop_loss")
        targets = sig.get("targets") or []
        direction = sig.get("direction")
        if entry is None or stop is None or not targets or direction is None:
            raise HermesIntegrationError(
                "fired scan entry is missing entry_price/stop_loss/targets/direction"
            )

        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            raise HermesIntegrationError("stop_loss must differ from entry_price")

        risk_usd = capital_usd * risk_pct
        coin_qty = risk_usd / stop_distance  # size so loss at stop = risk_usd
        notional_usd = coin_qty * entry
        margin_required_usd = notional_usd / leverage

        zc1 = targets[0]
        zc2 = targets[1] if len(targets) > 1 else None
        reward_zc1_usd = abs(zc1 - entry) * coin_qty
        reward_zc2_usd = abs(zc2 - entry) * coin_qty if zc2 is not None else None
        rr_zc1 = reward_zc1_usd / risk_usd if risk_usd > 0 else None
        rr_zc2 = (reward_zc2_usd / risk_usd) if reward_zc2_usd is not None else None

        coin = coin_scan.get("coin") or "COIN"
        human = (
            f"OPEN {direction.upper()} {coin}\n"
            f"  Entry     : ${entry:,.2f}\n"
            f"  Stop-loss : ${stop:,.2f}  (risk ${risk_usd:,.2f})\n"
            f"  ZC1       : ${zc1:,.2f}  (+${reward_zc1_usd:,.2f}, RR {rr_zc1:.2f})\n"
        )
        if zc2 is not None:
            human += (
                f"  ZC2       : ${zc2:,.2f}  (+${reward_zc2_usd:,.2f}, RR {rr_zc2:.2f})\n"
            )
        human += (
            f"  Size      : {coin_qty:.6f} {coin} (${notional_usd:,.2f} notional)\n"
            f"  Leverage  : {leverage:.1f}x → margin ${margin_required_usd:,.2f}"
        )

        return {
            "recommendation": "open_position",
            "direction": direction,
            "coin": coin,
            "entry_price": entry,
            "stop_loss": stop,
            "targets": targets,
            "sizing": {
                "capital_usd": capital_usd,
                "risk_pct": risk_pct,
                "risk_usd": round(risk_usd, 2),
                "coin_qty": round(coin_qty, 8),
                "notional_usd": round(notional_usd, 2),
                "leverage": leverage,
                "margin_required_usd": round(margin_required_usd, 2),
            },
            "reward": {
                "zc1_usd": round(reward_zc1_usd, 2),
                "zc1_rr": round(rr_zc1, 3) if rr_zc1 is not None else None,
                "zc2_usd": round(reward_zc2_usd, 2) if reward_zc2_usd is not None else None,
                "zc2_rr": round(rr_zc2, 3) if rr_zc2 is not None else None,
            },
            "order_summary": human,
            "safety": {
                "default_dry_run": True,
                "suggested_mcp_call": {
                    "tool": "open_position",
                    "arguments": {
                        "coin": coin,
                        "side": direction,
                        "size_usd": round(notional_usd, 2),
                        "dry_run": True,
                    },
                },
            },
        }

    def scan_history(
        self,
        *,
        days: int = 7,
        reports_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """Return the last N daily-scan reports from ``var/reports/``.

        Reports are expected to be named ``daily_scan_YYYY-MM-DD.json`` and
        written by ``scripts/daily_scan.py``. Missing/unreadable files are
        skipped (not fatal) — the agent sees what exists.
        """
        if days < 1 or days > 90:
            raise HermesIntegrationError("days must be between 1 and 90")

        base = Path(reports_dir) if reports_dir else _default_reports_dir()
        today = date.today()
        history: list[dict[str, Any]] = []
        missing: list[str] = []
        for offset in range(days):
            day = today - timedelta(days=offset)
            path = base / f"daily_scan_{day.isoformat()}.json"
            if not path.exists():
                missing.append(day.isoformat())
                continue
            try:
                payload = json.loads(path.read_text())
            except Exception as exc:  # noqa: BLE001
                logger.warning("skipping unreadable scan %s: %s", path, exc)
                missing.append(day.isoformat())
                continue
            scan = payload.get("scan") or payload
            summary = scan.get("summary") or {}
            history.append(
                {
                    "date": day.isoformat(),
                    "path": str(path),
                    "generated_at": scan.get("generated_at"),
                    "evaluated": summary.get("evaluated", []),
                    "fires": summary.get("fires", []),
                    "stages": {
                        coin: entry.get("stage")
                        for coin, entry in (scan.get("coins") or {}).items()
                    },
                }
            )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "reports_dir": str(base),
            "days_requested": days,
            "reports": history,
            "missing": missing,
        }

    def dispatch_tool_call(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Invoke a Hermes-registered tool by name with validated arguments."""
        args = arguments or {}
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "cot_report": self.cot_report,
            "cot_history": self.cot_history,
            "weekly_plan": self.weekly_plan,
            "theory_v2_scan": self.theory_v2_scan,
            "strategy_context": self.strategy_context,
            "recommend_position": self.recommend_position,
            "scan_history": self.scan_history,
        }

        handler = handlers.get(tool_name)
        if handler is None:
            raise HermesIntegrationError(f"Unknown Hermes tool: {tool_name}")

        try:
            result = handler(**args)
        except TypeError as exc:
            raise HermesIntegrationError(f"Invalid arguments for {tool_name}: {exc}") from exc

        return {
            "tool": tool_name,
            "ok": True,
            "result": _to_jsonable(result),
        }

    def gateway_invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Gateway-compatible invocation contract.

        Expected payload shape:
            {"tool": "cot_report", "arguments": {...}}
        """
        tool_name = str(payload.get("tool", "")).strip()
        arguments = payload.get("arguments")
        if not tool_name:
            raise HermesIntegrationError("payload.tool is required")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise HermesIntegrationError("payload.arguments must be an object")
        return self.dispatch_tool_call(tool_name, arguments)

    def _market_structure_4h(
        self, *, client: HyperliquidClient, coin: str, as_of_date: str
    ) -> dict[str, Any]:
        """Build lightweight 4H structure snapshot from real candles."""
        try:
            as_of = datetime.fromisoformat(as_of_date).replace(tzinfo=timezone.utc)
        except ValueError:
            as_of = datetime.now(timezone.utc)

        end_dt = as_of + timedelta(days=1)
        start_dt = end_dt - timedelta(days=10)
        candles = client.get_historical_candles(
            coin=coin,
            interval="4h",
            start_time_ms=int(start_dt.timestamp() * 1000),
            end_time_ms=int(end_dt.timestamp() * 1000),
            max_pages=32,
            throttle_seconds=0,
        )
        if not candles:
            return {
                "trend": "unknown",
                "price": 0.0,
                "swing_high": 0.0,
                "swing_low": 0.0,
                "atr": 1.0,
            }

        closes = [float(candle["close"]) for candle in candles]
        highs = [float(candle["high"]) for candle in candles]
        lows = [float(candle["low"]) for candle in candles]

        trend = "bullish" if closes[-1] >= closes[0] else "bearish"
        atr_window = list(zip(highs[-14:], lows[-14:]))
        atr = sum((high_value - low_value) for high_value, low_value in atr_window) / max(
            1,
            len(atr_window),
        )
        return {
            "trend": trend,
            "price": closes[-1],
            "swing_high": max(highs[-18:]),
            "swing_low": min(lows[-18:]),
            "atr": atr,
        }
