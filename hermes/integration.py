"""Hermes Agent integration layer for Nave.

This module exposes MCP/gateway-friendly tool handlers with structured JSON
outputs so autonomous agents can consume deterministic responses.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, cast

from core.config import CliDefaults
from core.exceptions import HermesIntegrationError
from core.logger import configure_logger
from options.factory import build_options_analyzer
from trading.crypto.client import HyperliquidClient
from trading.crypto.cot.cot_analyzer import COTAnalyzer
from trading.crypto.cot.cot_fetcher import build_cot_sections_from_datasets, fetch_latest_cot
from trading.crypto.cot.cot_position_generator import COTPositionGenerator

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
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    return value


def _extract_suggested_risk(coin_scan: dict[str, Any]) -> dict[str, Any] | None:
    """Return a normalized advisory risk hint from review/scan payloads."""
    raw = coin_scan.get("suggested_risk")
    if raw is None:
        recommendation = coin_scan.get("recommendation")
        if isinstance(recommendation, dict):
            raw = recommendation.get("suggested_risk")
    if not isinstance(raw, dict):
        return None

    suggested = raw.get("suggested_risk_pct")
    current = raw.get("current_risk_pct")
    if suggested is None and raw.get("risk_pct") is not None:
        suggested = raw.get("risk_pct")
    try:
        suggested_pct = float(suggested)
    except (TypeError, ValueError):
        return None
    try:
        current_pct = float(current) if current is not None else None
    except (TypeError, ValueError):
        current_pct = None

    return {
        "mode": raw.get("mode", "advisory"),
        "applies_to": raw.get("applies_to"),
        "current_risk_pct": current_pct,
        "suggested_risk_pct": suggested_pct,
        "blocked": bool(raw.get("blocked", False)),
        "blockers": list(raw.get("blockers") or []),
        "rationale": raw.get("rationale"),
        "source": "coin_scan.suggested_risk",
    }


def _operational_hints(
    *,
    preferred_execution: str,
    agent_reminder_min_interval_minutes: int,
    native_scheduler_min_interval_minutes: int | None = None,
    fallback_when_provider_429: str,
    send_preformatted_digest_first: bool = True,
) -> dict[str, Any]:
    """Attach schedule/fallback guidance for chat agents and cron jobs."""
    hints: dict[str, Any] = {
        "preferred_execution": preferred_execution,
        "agent_reminder_min_interval_minutes": agent_reminder_min_interval_minutes,
        "fallback_when_provider_429": fallback_when_provider_429,
        "send_preformatted_digest_first": send_preformatted_digest_first,
    }
    if native_scheduler_min_interval_minutes is not None:
        hints["native_scheduler_min_interval_minutes"] = native_scheduler_min_interval_minutes
    return hints


def _with_operational_hints(
    payload: dict[str, Any],
    *,
    preferred_execution: str,
    agent_reminder_min_interval_minutes: int,
    native_scheduler_min_interval_minutes: int | None = None,
    fallback_when_provider_429: str,
    send_preformatted_digest_first: bool = True,
) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["operational_hints"] = _operational_hints(
        preferred_execution=preferred_execution,
        agent_reminder_min_interval_minutes=agent_reminder_min_interval_minutes,
        native_scheduler_min_interval_minutes=native_scheduler_min_interval_minutes,
        fallback_when_provider_429=fallback_when_provider_429,
        send_preformatted_digest_first=send_preformatted_digest_first,
    )
    return enriched


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
                "description": "Nave momentum, COT analysis, and weekly planning tools",
            },
            "tools": [
                {
                    "name": "momentum_scan",
                    "description": (
                        "Primary derivatives market-read tool and default scan path. Scans BTC/ETH perpetuals "
                        "for high-probability momentum breakouts with retest, volatility, "
                        "participation, funding, and risk-efficiency filters."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "symbols": {"type": "string", "default": "BTCUSDT,ETHUSDT"},
                            "tf": {"type": "string", "default": "4h,1h"},
                            "account_equity": {"type": "number", "default": 10000.0},
                            "risk_pct": {"type": "number", "default": 0.005},
                            "score_threshold": {"type": "integer", "default": 75},
                        },
                    },
                },
                {
                    "name": "market_scan",
                    "description": (
                        "Default generic market scan alias. Internally routes to momentum_scan so Hermes "
                        "uses momentum by default when looking at BTC/ETH derivatives."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "symbols": {"type": "string", "default": "BTCUSDT,ETHUSDT"},
                            "tf": {"type": "string", "default": "4h,1h"},
                            "account_equity": {"type": "number", "default": 10000.0},
                            "risk_pct": {"type": "number", "default": 0.005},
                            "score_threshold": {"type": "integer", "default": 75},
                        },
                    },
                },
                {
                    "name": "momentum_zone_watch",
                    "description": (
                        "Monitor momentum entry zones and emit alerts when live price first "
                        "touches a watched zone. Returns Telegram MarkdownV2 chunks for direct delivery. "
                        "For chat/reminder jobs, do not schedule faster than hourly; for 5-minute monitoring "
                        "use scripts/monitor_entry_zones.py via cron/launchd."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "symbols": {"type": "string", "default": "BTCUSDT,ETHUSDT"},
                            "tf": {"type": "string", "default": "4h,1h"},
                            "score_threshold": {"type": "integer", "default": 75},
                            "account_equity": {"type": "number", "default": 10000.0},
                            "risk_pct": {"type": "number", "default": 0.005},
                        },
                    },
                },
                {
                    "name": "momentum_playbook",
                    "description": (
                        "Build one concrete BTC/ETH derivatives trade plan with entry zone, "
                        "invalidation, targets, sizing, and leverage constraints."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "default": "BTCUSDT"},
                            "side": {"type": "string", "enum": ["long", "short"]},
                            "tf": {"type": "string", "default": "4h,1h"},
                            "account_equity": {"type": "number", "default": 10000.0},
                            "risk_pct": {"type": "number", "default": 0.005},
                            "score_threshold": {"type": "integer", "default": 75},
                        },
                        "required": ["symbol", "side"],
                    },
                },
                {
                    "name": "market_playbook",
                    "description": (
                        "Default generic trade-plan alias. Internally routes to momentum_playbook so BTC/ETH "
                        "market planning defaults to momentum execution rules."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "default": "BTCUSDT"},
                            "side": {"type": "string", "enum": ["long", "short"]},
                            "tf": {"type": "string", "default": "4h,1h"},
                            "account_equity": {"type": "number", "default": 10000.0},
                            "risk_pct": {"type": "number", "default": 0.005},
                            "score_threshold": {"type": "integer", "default": 75},
                        },
                        "required": ["symbol", "side"],
                    },
                },
                {
                    "name": "options_scan",
                    "description": (
                        "Analyze equity options chains (MSFT default), rank strategies, "
                        "and return top recommendations with risk metrics and chart paths."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "default": "MSFT"},
                            "days_to_exp": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30},
                            "source": {
                                "type": "string",
                                "enum": ["yfinance", "deribit"],
                                "default": "yfinance",
                            },
                        },
                    },
                },
                {
                    "name": "options_registry_build",
                    "description": (
                        "Build or refresh the S&P top-40 ticker playbook registry: "
                        "price behavior, replay setup stats, X cache, congressional trades."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "include_live_options": {"type": "boolean", "default": False},
                            "replay_json": {"type": "string"},
                        },
                    },
                },
                {
                    "name": "options_registry_show",
                    "description": "Return the full playbook card for one ticker from the registry.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                        },
                        "required": ["ticker"],
                    },
                },
                {
                    "name": "options_hidden_gems",
                    "description": (
                        "Scan S&P liquid names for hidden-gem income setups: high PoP bull puts "
                        "(bias-aligned), under-the-radar names, optional X crowd interest from cache."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "minimum": 10, "maximum": 200, "default": 80},
                            "top": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
                            "days_to_exp": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30},
                            "workers": {"type": "integer", "minimum": 1, "maximum": 8, "default": 4},
                            "fetch_x_for_top": {"type": "integer", "minimum": 0, "maximum": 12, "default": 0},
                            "source": {"type": "string", "enum": ["yfinance", "deribit"], "default": "yfinance"},
                        },
                    },
                },
                {
                    "name": "options_sp500_weekly",
                    "description": (
                        "Run the weekly S&P 500 options universe scan and return a Discord-ready "
                        "Spanish report with scan-quality safeguards."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 40},
                            "top": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
                            "days_to_exp": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30},
                            "workers": {"type": "integer", "minimum": 1, "maximum": 8, "default": 6},
                            "source": {"type": "string", "enum": ["yfinance", "deribit"], "default": "yfinance"},
                        },
                    },
                },
                {
                    "name": "options_opportunities",
                    "description": (
                        "Scan BTC/ETH options opportunities by first applying the momentum "
                        "filter, then running options analysis for momentum-qualified setups."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "coins": {
                                "type": "string",
                                "default": "BTC,ETH",
                            },
                            "days_to_exp": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 365,
                                "default": 30,
                            },
                            "tf": {
                                "type": "string",
                                "default": "4h,1h",
                            },
                            "account_equity": {
                                "type": "number",
                                "default": 10000.0,
                            },
                            "risk_pct": {
                                "type": "number",
                                "default": 0.005,
                            },
                            "score_threshold": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 75,
                            },
                            "require_tradeable": {
                                "type": "boolean",
                                "default": True,
                            },
                            "source": {
                                "type": "string",
                                "enum": ["yfinance", "deribit"],
                                "default": "yfinance",
                            },
                        },
                    },
                },
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
                    "name": "position_review",
                    "description": (
                        "Primary BTC/ETH position recommendation. Merges COT contrarian bias, "
                        "momentum 4H/1H setups, and theory_v2 gate trace into enter / watch / "
                        "stand_aside with entry zone, stop, and targets."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "coins": {"type": "string", "default": "BTC ETH"},
                            "account_equity": {"type": "number", "default": 10000.0},
                            "risk_pct": {"type": "number", "default": 0.005},
                            "apply_cadence_policy": {"type": "boolean", "default": True},
                            "include_options": {"type": "boolean", "default": True},
                            "options_source": {"type": "string", "default": "deribit"},
                        },
                    },
                },
                {
                    "name": "theory_v2_scan",
                    "description": (
                        "Legacy secondary scan. Daily top-down theory v2 scan — evaluates weekly momentum → "
                        "daily confirm → climax cooldown → chase gate → 4H → 1H for each "
                        "coin and returns the full decision trace (stage, reason, bias, "
                        "fired?). Use when you explicitly want the theory-v2 path rather than the default momentum scan."
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
                        "reward at ZC1/ZC2, and a human-readable order summary. If the "
                        "scan includes suggested_risk, Hermes returns it as advisory "
                        "context without changing caller-requested sizing."
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
                {
                    "name": "stocks_ism_report",
                    "description": (
                        "Return ISM hottest/worst industries and Massive-filtered stock "
                        "candidates based on PE and next-year EPS growth criteria. Also includes "
                        "Telegram MarkdownV2 digest chunks so reminder jobs can send a preformatted "
                        "summary directly when an LLM provider is rate-limited. For chat/reminder jobs, "
                        "cap cadence at hourly."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": ["manufacturing", "services"],
                                "default": "manufacturing",
                            },
                            "top_n": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                            "min_eps_growth_next_year": {"type": "number"},
                            "min_confidence": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.3},
                            "min_short_score": {"type": "number"},
                            "research_mode": {"type": "boolean", "default": False},
                        },
                    },
                },
                {
                    "name": "stocks_ism_calendar",
                    "description": (
                        "Return the internal ISM release calendar (sourced from FMP). "
                        "Use this to answer 'when is the next ISM Manufacturing/Services "
                        "PMI release?' or to fetch the full year's release dates. For recurring "
                        "jobs prefer next_only/recent_days with refresh=false so reminder runs "
                        "reuse stored data instead of re-fetching on every trigger."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "year": {
                                "type": "integer",
                                "minimum": 2000,
                                "maximum": 2100,
                                "description": "Calendar year. Defaults to the current year.",
                            },
                            "kind": {
                                "type": "string",
                                "enum": ["manufacturing", "services"],
                                "description": "Optional filter. Omit to return both.",
                            },
                            "next_only": {
                                "type": "boolean",
                                "default": False,
                                "description": "Return only the next upcoming release.",
                            },
                            "recent_days": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 30,
                                "default": 0,
                                "description": (
                                    "When > 0, return the most recent release within "
                                    "the given day lookback window."
                                ),
                            },
                            "refresh": {
                                "type": "boolean",
                                "default": False,
                                "description": "Re-fetch from FMP and overwrite the stored file.",
                            },
                        },
                    },
                },
                {
                    "name": "stocks_politicians_scan",
                    "description": (
                        "Daily-cadence scan of Congressional STOCK Act disclosures. "
                        "Call this once per day as part of the daily routine: fetches "
                        "the latest House and Senate periodic transaction reports from "
                        "FMP and returns only disclosures not previously surfaced "
                        "(diffed against an internal seen-cache). "
                        "When 'new_total' > 0, notify the user with the trades; "
                        "when 'new_total' == 0, stay silent. "
                        "Includes Telegram MarkdownV2 digest chunks so no extra LLM formatting step is required. "
                        "Note the STOCK Act allows up to 45 days between trade and "
                        "disclosure — this is informational, not a real-time edge."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "lookback_days": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 30,
                                "description": (
                                    "Reserved for future use. The provider returns the "
                                    "FMP 'latest' window regardless; novelty is gated "
                                    "by the local seen-cache, not by this parameter."
                                ),
                            },
                            "persist": {
                                "type": "boolean",
                                "default": True,
                                "description": (
                                    "Update the seen-cache with this scan's results. "
                                    "Set false for a dry-run preview."
                                ),
                            },
                        },
                    },
                },
                {
                    "name": "stocks_x_analyze",
                    "description": (
                        "Fetch recent X (Twitter) posts about one or more stock tickers "
                        "and return them packaged with the LLM analysis prompt baked in, plus a "
                        "deterministic Telegram MarkdownV2 summary digest for provider-429 fallback. "
                        "The caller (Telegram-side LLM, manual paste into another model) "
                        "uses payload.analysis_prompt.system + .user to produce the final "
                        "markdown sentiment report. For chat/reminder jobs, cap cadence at hourly."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "tickers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of tickers, e.g. ['NVDA', 'AAPL'].",
                            },
                            "days": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 30,
                                "default": 7,
                            },
                            "limit_per_ticker": {
                                "type": "integer",
                                "minimum": 5,
                                "maximum": 200,
                                "default": 50,
                            },
                            "persist": {"type": "boolean", "default": True},
                        },
                        "required": ["tickers"],
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
        coin_list = [coin.strip().upper()
                     for coin in coins.split() if coin.strip()]
        if not coin_list:
            raise HermesIntegrationError(
                "At least one coin is required for cot_report")

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

    def momentum_scan(
        self,
        *,
        symbols: str = "BTCUSDT,ETHUSDT",
        tf: str = "4h,1h",
        account_equity: float = 10000.0,
        risk_pct: float = 0.005,
        score_threshold: int = 75,
    ) -> dict[str, Any]:
        if account_equity <= 0:
            raise HermesIntegrationError("account_equity must be positive")
        if not 0.001 <= risk_pct <= 0.02:
            raise HermesIntegrationError(
                "risk_pct must be between 0.001 and 0.02")
        if not 1 <= score_threshold <= 100:
            raise HermesIntegrationError(
                "score_threshold must be between 1 and 100")

        from trading.crypto.momentum.service import MomentumMarketService
        from trading.crypto.momentum.formatters import (
            render_momentum_scan_markdown_v2,
        )

        service = MomentumMarketService()
        try:
            payload = service.scan_live(
                symbols=service.parse_symbols(symbols),
                timeframes=service.parse_timeframes(tf),
                account_equity=account_equity,
                risk_pct=risk_pct,
                score_threshold=score_threshold,
            )
        except ValueError as exc:
            raise HermesIntegrationError(str(exc)) from exc

        payload["telegram_markdown_v2"] = render_momentum_scan_markdown_v2(
            payload)
        return payload

    def momentum_playbook(
        self,
        *,
        symbol: str,
        side: str,
        tf: str = "4h,1h",
        account_equity: float = 10000.0,
        risk_pct: float = 0.005,
        score_threshold: int = 75,
    ) -> dict[str, Any]:
        if account_equity <= 0:
            raise HermesIntegrationError("account_equity must be positive")
        if side not in {"long", "short"}:
            raise HermesIntegrationError("side must be long or short")
        if not 0.001 <= risk_pct <= 0.02:
            raise HermesIntegrationError(
                "risk_pct must be between 0.001 and 0.02")
        if not 1 <= score_threshold <= 100:
            raise HermesIntegrationError(
                "score_threshold must be between 1 and 100")

        from trading.crypto.momentum.service import MomentumMarketService

        service = MomentumMarketService()
        try:
            return service.playbook_live(
                symbol=service.parse_symbols(symbol)[0],
                side=side,
                timeframes=service.parse_timeframes(tf),
                account_equity=account_equity,
                risk_pct=risk_pct,
                score_threshold=score_threshold,
            )
        except ValueError as exc:
            raise HermesIntegrationError(str(exc)) from exc

    def momentum_zone_watch(
        self,
        *,
        symbols: str = "BTCUSDT,ETHUSDT",
        tf: str = "4h,1h",
        score_threshold: int = 75,
        account_equity: float = 10000.0,
        risk_pct: float = 0.005,
    ) -> dict[str, Any]:
        if account_equity <= 0:
            raise HermesIntegrationError("account_equity must be positive")
        if not 0.001 <= risk_pct <= 0.02:
            raise HermesIntegrationError(
                "risk_pct must be between 0.001 and 0.02")
        if not 1 <= score_threshold <= 100:
            raise HermesIntegrationError(
                "score_threshold must be between 1 and 100")

        from trading.alerts.entry_zone_monitor import (
            EntryZoneMonitor,
            build_zone_watch_candidates,
        )
        from trading.crypto.momentum.formatters import (
            render_entry_zone_alert_markdown_v2,
        )
        from trading.crypto.momentum.service import MomentumMarketService

        service = MomentumMarketService()

        try:
            payload = service.scan_live(
                symbols=service.parse_symbols(symbols),
                timeframes=service.parse_timeframes(tf),
                account_equity=account_equity,
                risk_pct=risk_pct,
                score_threshold=score_threshold,
            )
        except ValueError as exc:
            raise HermesIntegrationError(str(exc)) from exc

        candidates = build_zone_watch_candidates(
            payload, min_score=score_threshold)
        monitor = EntryZoneMonitor()
        monitor_result = monitor.evaluate(
            candidates,
            price_lookup=lambda symbol: service.market_client.get_mid(
                symbol.replace("USDT", "")),
        )

        monitor_result["scan_summary"] = payload.get("summary")
        monitor_result["watch_candidates"] = monitor_result.get("watch_states") or [
            {
                "symbol": candidate.symbol,
                "side": candidate.side,
                "entry_zone": [candidate.entry_zone[0], candidate.entry_zone[1]],
                "invalidation": candidate.invalidation,
                "confidence_score": candidate.confidence_score,
                "rr_estimated": candidate.rr_estimated,
                "setup_status": candidate.setup_status,
            }
            for candidate in candidates
        ]
        monitor_result["telegram_markdown_v2"] = [
            render_entry_zone_alert_markdown_v2(alert)
            for alert in monitor_result.get("alerts", [])
            if isinstance(alert, dict)
        ]
        return _with_operational_hints(
            monitor_result,
            preferred_execution="native_scheduler",
            agent_reminder_min_interval_minutes=60,
            native_scheduler_min_interval_minutes=5,
            fallback_when_provider_429=(
                "Use telegram_markdown_v2 directly or switch to scripts/monitor_entry_zones.py "
                "with --send-telegram for high-frequency monitoring."
            ),
        )

    def market_scan(
        self,
        *,
        symbols: str = "BTCUSDT,ETHUSDT",
        tf: str = "4h,1h",
        account_equity: float = 10000.0,
        risk_pct: float = 0.005,
        score_threshold: int = 75,
    ) -> dict[str, Any]:
        """Default generic scan alias: route market reads to momentum."""
        return self.momentum_scan(
            symbols=symbols,
            tf=tf,
            account_equity=account_equity,
            risk_pct=risk_pct,
            score_threshold=score_threshold,
        )

    def market_playbook(
        self,
        *,
        symbol: str,
        side: str,
        tf: str = "4h,1h",
        account_equity: float = 10000.0,
        risk_pct: float = 0.005,
        score_threshold: int = 75,
    ) -> dict[str, Any]:
        """Default generic playbook alias: route market plans to momentum."""
        return self.momentum_playbook(
            symbol=symbol,
            side=side,
            tf=tf,
            account_equity=account_equity,
            risk_pct=risk_pct,
            score_threshold=score_threshold,
        )

    def options_scan(
        self,
        *,
        ticker: str = "MSFT",
        days_to_exp: int = 30,
        source: str = "yfinance",
    ) -> dict[str, Any]:
        """Run options analysis and return ranked strategies with charts."""
        symbol = ticker.strip().upper()
        if not symbol:
            raise HermesIntegrationError("ticker must be a non-empty symbol")
        if not 1 <= days_to_exp <= 365:
            raise HermesIntegrationError(
                "days_to_exp must be between 1 and 365")

        from options.exceptions import OptionsError
        from options.formatters import render_options_scan_markdown_v2

        try:
            payload = build_options_analyzer(source=source).run(
                ticker=symbol,
                days_to_exp=days_to_exp,
            )
        except OptionsError as exc:
            raise HermesIntegrationError(str(exc)) from exc

        payload["telegram_markdown_v2"] = render_options_scan_markdown_v2(
            payload)
        return payload

    def options_sp500_weekly(
        self,
        *,
        limit: int = 40,
        top: int = 10,
        days_to_exp: int = 30,
        workers: int = 6,
        source: str = "yfinance",
    ) -> dict[str, Any]:
        """Run the weekly S&P 500 options scan with a Discord-ready report."""
        if not 1 <= limit <= 200:
            raise HermesIntegrationError("limit must be between 1 and 200")
        if not 1 <= top <= 20:
            raise HermesIntegrationError("top must be between 1 and 20")
        if not 1 <= days_to_exp <= 365:
            raise HermesIntegrationError("days_to_exp must be between 1 and 365")

        from options.formatters import render_equity_universe_scan_discord_es
        from options.universe import SP500_TOP_100_TICKERS, get_sp500_tickers
        from options.universe_scan import scan_equity_options_universe

        tickers = (
            list(get_sp500_tickers(limit))
            if limit > len(SP500_TOP_100_TICKERS)
            else list(SP500_TOP_100_TICKERS[:limit])
        )
        analyzer = build_options_analyzer(source=source)
        scan = scan_equity_options_universe(
            analyzer=analyzer,
            analyzer_factory=lambda: build_options_analyzer(source=source),
            tickers=tickers,
            days_to_exp=days_to_exp,
            top_trades=top,
            workers=min(workers, 8),
        )
        command = (
            "nave options analyze --sp500-scan "
            f"--sp500-limit {limit} --top-trades {top} --days-to-exp {days_to_exp} --json"
        )
        scan["discord_text"] = render_equity_universe_scan_discord_es(
            scan,
            command=command,
            limit=limit,
            max_ranked=top,
        )
        scan["operational_hints"] = {
            "send_preformatted_digest_first": True,
            "discord_field": "discord_text",
            "do_not_convert_inconclusive_to_no_trade": True,
            "preferred_run_window": "regular US options market hours",
        }
        return scan

    def options_opportunities(
        self,
        *,
        coins: str = "BTC,ETH",
        days_to_exp: int = 30,
        tf: str = "4h,1h",
        account_equity: float = 10000.0,
        risk_pct: float = 0.005,
        score_threshold: int = 75,
        require_tradeable: bool = True,
        source: str = "yfinance",
    ) -> dict[str, Any]:
        """Scan momentum-filtered BTC/ETH options opportunities."""
        if not 1 <= days_to_exp <= 365:
            raise HermesIntegrationError(
                "days_to_exp must be between 1 and 365")
        if account_equity <= 0:
            raise HermesIntegrationError("account_equity must be positive")
        if not 0.001 <= risk_pct <= 0.02:
            raise HermesIntegrationError(
                "risk_pct must be between 0.001 and 0.02")
        if not 1 <= score_threshold <= 100:
            raise HermesIntegrationError(
                "score_threshold must be between 1 and 100")

        from options.exceptions import OptionsError
        from options.formatters import render_options_opportunities_markdown_v2

        coin_list = [item.strip().upper() for item in coins.replace(
            " ", ",").split(",") if item.strip()]
        if not coin_list:
            raise HermesIntegrationError(
                "coins must include at least one symbol")

        try:
            payload = build_options_analyzer(source=source).scan_crypto_opportunities(
                coins=coin_list,
                days_to_exp=days_to_exp,
                tf=tf,
                account_equity=account_equity,
                risk_pct=risk_pct,
                score_threshold=score_threshold,
                require_tradeable=require_tradeable,
            )
        except OptionsError as exc:
            raise HermesIntegrationError(str(exc)) from exc

        payload["telegram_markdown_v2"] = render_options_opportunities_markdown_v2(
            payload)
        return payload

    def options_registry_build(
        self,
        *,
        include_live_options: bool = False,
        replay_json: str | None = None,
    ) -> dict[str, Any]:
        """Build S&P top-40 ticker playbook registry on disk."""
        from pathlib import Path

        from options.ticker_registry import build_registry

        replay_path = Path(replay_json) if replay_json else None
        result = build_registry(
            include_live_options=include_live_options,
            replay_json=replay_path,
        )
        return {
            "ok": True,
            "root": result["paths"]["root"],
            "index": result["index"],
        }

    def options_registry_show(self, *, ticker: str) -> dict[str, Any]:
        """Load one ticker playbook from the registry."""
        from options.ticker_registry import load_ticker_profile

        sym = ticker.strip().upper()
        profile = load_ticker_profile(sym)
        if profile is None:
            raise HermesIntegrationError(
                f"No registry profile for {sym}. Run options_registry_build first."
            )
        return profile

    def options_hidden_gems(
        self,
        *,
        limit: int = 80,
        top: int = 10,
        days_to_exp: int = 30,
        workers: int = 4,
        fetch_x_for_top: int = 0,
        source: str = "yfinance",
    ) -> dict[str, Any]:
        """Scan equity universe and return refined hidden-gem income prospects."""
        if not 10 <= limit <= 200:
            raise HermesIntegrationError("limit must be between 10 and 200")
        if not 1 <= top <= 30:
            raise HermesIntegrationError("top must be between 1 and 30")
        if not 1 <= days_to_exp <= 365:
            raise HermesIntegrationError("days_to_exp must be between 1 and 365")

        from options.formatters import render_hidden_gems_markdown_v2
        from options.gems_pipeline import format_gem_digest, run_hidden_gems_scan
        from options.universe_scan import scan_equity_options_universe
        from options.universe import SP500_TOP_100_TICKERS, get_sp500_tickers

        tickers = (
            list(get_sp500_tickers(limit))
            if limit > len(SP500_TOP_100_TICKERS)
            else list(SP500_TOP_100_TICKERS[:limit])
        )
        analyzer = build_options_analyzer(source=source)
        scan = scan_equity_options_universe(
            analyzer=analyzer,
            analyzer_factory=lambda: build_options_analyzer(source=source),
            tickers=tickers,
            days_to_exp=days_to_exp,
            top_trades=top,
            workers=min(workers, 6),
        )
        payload = run_hidden_gems_scan(
            scan,
            top=top,
            fetch_x_for_top=fetch_x_for_top,
        )
        payload["scan_summary"] = scan.get("summary")
        payload["digest_text"] = format_gem_digest(payload["hidden_gems"])
        payload["telegram_markdown_v2"] = render_hidden_gems_markdown_v2(payload)
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
        coin_list = [coin.strip().upper()
                     for coin in coins.split() if coin.strip()]

        historical_data = fetch_latest_cot(
            report_type="futures_only" if report_type == "futures_only" else "futures_and_options",
            include_micro=include_micro,
            debug=False,
            history_weeks=history_weeks,
        )
        filtered = {coin: historical_data[coin]
                    for coin in coin_list if coin in historical_data}

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

        coin_list = [coin.strip().upper()
                     for coin in coins.split() if coin.strip()]
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
            as_of_raw = str(bias.metadata.get("as_of_date")
                            or date.today().isoformat())
            market_data_4h[coin] = self._market_structure_4h(
                client=market_client,
                coin=coin,
                as_of_date=as_of_raw,
            )

        coin_sections = {coin: sections[coin]
                         for coin in coin_list if coin in sections}
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

    def position_review(
        self,
        *,
        coins: str = "BTC ETH",
        account_equity: float = 10_000.0,
        risk_pct: float = 0.005,
        apply_cadence_policy: bool = True,
        include_options: bool = True,
        options_source: str = "deribit",
    ) -> dict[str, Any]:
        """Unified BTC/ETH review: COT + momentum + regime + options (long & short)."""
        from trading.crypto.analysis import CryptoAnalysisService

        coin_list = [c.strip().upper() for c in coins.replace(",", " ").split() if c.strip()]
        return CryptoAnalysisService().review(
            coin_list,
            account_equity=account_equity,
            risk_pct=risk_pct,
            apply_cadence_policy=apply_cadence_policy,
            include_options=include_options,
            options_source=options_source,
        )

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
        coin_list = [coin.strip().upper()
                     for coin in coins.split() if coin.strip()]
        if not coin_list:
            raise HermesIntegrationError(
                "At least one coin is required for theory_v2_scan")

        from trading.crypto.theory_v2 import build_signals_for_coins  # local to keep import light

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
                {"timeframe": "1W", "gate": "range_breakout_bias",
                    "role": "direction_fallback"},
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
                        "Resolved in unified_cot_momentum_v1: extreme crowded "
                        "spec-long now supports contrarian shorts; only "
                        "blocks chasing the crowded direction."
                    ),
                    "iter_ref": "unified_cot_momentum_v1",
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
            raise HermesIntegrationError(
                "coin_scan must be a dict from theory_v2_scan output")

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
            raise HermesIntegrationError(
                "stop_loss must differ from entry_price")

        risk_advisory = _extract_suggested_risk(coin_scan)
        risk_usd = capital_usd * risk_pct
        coin_qty = risk_usd / stop_distance  # size so loss at stop = risk_usd
        notional_usd = coin_qty * entry
        margin_required_usd = notional_usd / leverage

        zc1 = targets[0]
        zc2 = targets[1] if len(targets) > 1 else None
        reward_zc1_usd = abs(zc1 - entry) * coin_qty
        reward_zc2_usd = abs(zc2 - entry) * \
            coin_qty if zc2 is not None else None
        rr_zc1 = reward_zc1_usd / risk_usd if risk_usd > 0 else None
        rr_zc2 = (reward_zc2_usd /
                  risk_usd) if reward_zc2_usd is not None else None

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

        safety: dict[str, Any] = {
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
        }
        if risk_advisory is not None:
            suggested_pct = risk_advisory["suggested_risk_pct"]
            advisory_risk_usd = capital_usd * suggested_pct
            advisory_qty = advisory_risk_usd / stop_distance
            advisory_notional = advisory_qty * entry
            risk_advisory.update(
                {
                    "sizing_unchanged": True,
                    "caller_risk_pct": risk_pct,
                    "advisory_risk_usd": round(advisory_risk_usd, 2),
                    "advisory_coin_qty": round(advisory_qty, 8),
                    "advisory_notional_usd": round(advisory_notional, 2),
                }
            )
            safety["risk_advisory"] = risk_advisory

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
            "safety": safety,
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

    def stocks_ism_report(
        self,
        *,
        kind: str = "manufacturing",
        top_n: int = 5,
        min_eps_growth_next_year: float | None = None,
        min_confidence: float = 0.3,
        min_short_score: float | None = None,
        research_mode: bool = False,
    ) -> dict[str, Any]:
        """Return ISM industry heatmap + filtered stock candidates."""
        if kind not in {"manufacturing", "services"}:
            raise HermesIntegrationError(
                "kind must be manufacturing or services")
        if top_n < 1 or top_n > 20:
            raise HermesIntegrationError("top_n must be in [1, 20]")
        if min_confidence < 0 or min_confidence > 1:
            raise HermesIntegrationError("min_confidence must be in [0, 1]")

        from trading.stocks.reporting import build_ism_industry_report
        from trading.stocks.formatters import render_ism_report_markdown_v2

        try:
            payload = build_ism_industry_report(
                kind=kind,
                top_n=top_n,
                min_eps_growth_next_year=min_eps_growth_next_year,
                min_confidence=min_confidence,
                min_short_score=min_short_score,
                research_mode=research_mode,
            )
        except ValueError as exc:
            raise HermesIntegrationError(str(exc)) from exc
        payload["telegram_markdown_v2"] = render_ism_report_markdown_v2(payload)
        return _with_operational_hints(
            payload,
            preferred_execution="agent_or_native",
            agent_reminder_min_interval_minutes=60,
            fallback_when_provider_429=(
                "Send telegram_markdown_v2 directly, or keep using the stored ISM snapshot "
                "instead of re-running an LLM-formatted reminder."
            ),
        )

    def stocks_ism_calendar(
        self,
        *,
        year: int | None = None,
        kind: str | None = None,
        next_only: bool = False,
        recent_days: int = 0,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Return the stored ISM release calendar (or the next upcoming release)."""
        from datetime import date

        from trading.stocks.ism_calendar import (
            CalendarKind,
            ISMCalendarError,
            fetch_ism_calendar,
            load_calendar,
            next_release,
            recent_release,
        )

        if kind is not None and kind not in {"manufacturing", "services"}:
            raise HermesIntegrationError(
                "kind must be manufacturing or services"
            )
        if recent_days < 0 or recent_days > 30:
            raise HermesIntegrationError(
                "recent_days must be between 0 and 30")

        kind_filter = cast(CalendarKind | None, kind)

        if recent_days > 0:
            release = recent_release(kind=kind_filter, lookback_days=recent_days)  # type: ignore[arg-type]
            return _with_operational_hints(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "recent_days": recent_days,
                    "recent_release": _to_jsonable(release) if release else None,
                },
                preferred_execution="agent_or_native",
                agent_reminder_min_interval_minutes=60,
                fallback_when_provider_429=(
                    "Reuse the stored calendar with recent_days/next_only and avoid refresh on each reminder run."
                ),
            )

        if next_only:
            release = next_release(kind=kind_filter)  # type: ignore[arg-type]
            return _with_operational_hints(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "next_release": _to_jsonable(release) if release else None,
                },
                preferred_execution="agent_or_native",
                agent_reminder_min_interval_minutes=60,
                fallback_when_provider_429=(
                    "Reuse the stored calendar with next_only and avoid refresh on each reminder run."
                ),
            )

        target_year = year or date.today().year
        if refresh:
            try:
                calendar = fetch_ism_calendar(target_year)
            except ISMCalendarError as exc:
                raise HermesIntegrationError(str(exc)) from exc
        else:
            calendar = load_calendar(target_year)
            if calendar is None:
                try:
                    calendar = fetch_ism_calendar(target_year)
                except ISMCalendarError as exc:
                    raise HermesIntegrationError(str(exc)) from exc

        releases = (
            calendar.by_kind(kind_filter)
            if kind_filter is not None
            else calendar.releases
        )
        return _with_operational_hints(
            {
                "year": calendar.year,
                "generated_at": calendar.generated_at,
                "source": calendar.source,
                "source_url": calendar.source_url,
                "releases": _to_jsonable(releases),
            },
            preferred_execution="agent_or_native",
            agent_reminder_min_interval_minutes=60,
            fallback_when_provider_429=(
                "Reuse the stored calendar payload and avoid refresh on each reminder run."
            ),
        )

    def stocks_politicians_scan(
        self,
        *,
        lookback_days: int | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Return new Congressional STOCK Act disclosures since the last scan.

        Hermes should call this once per day. The response includes
        ``new_total`` (notify the user when > 0) and ``new_trades`` with
        chamber, politician, symbol, transaction type, bucketed amount,
        transaction date, disclosure date, and the source PDF link.

        ``lookback_days`` is accepted for forward compatibility but does
        not currently filter the FMP feed — novelty is determined entirely
        by the local seen-cache.
        """
        if lookback_days is not None and not 1 <= lookback_days <= 30:
            raise HermesIntegrationError(
                "lookback_days must be between 1 and 30")

        from trading.stocks.politicians.provider import PoliticianTradesError
        from trading.stocks.politicians.formatters import (
            render_politicians_scan_markdown_v2,
        )
        from trading.stocks.politicians.scanner import run_daily_scan

        try:
            payload = run_daily_scan(persist=persist)
        except PoliticianTradesError as exc:
            raise HermesIntegrationError(str(exc)) from exc

        payload["telegram_markdown_v2"] = render_politicians_scan_markdown_v2(payload)
        return _with_operational_hints(
            payload,
            preferred_execution="native_scheduler",
            agent_reminder_min_interval_minutes=1440,
            native_scheduler_min_interval_minutes=1440,
            fallback_when_provider_429=(
                "Send telegram_markdown_v2 directly and keep politicians scans at daily cadence."
            ),
        )

    def stocks_x_analyze(
        self,
        *,
        tickers: list[str],
        days: int = 7,
        limit_per_ticker: int = 50,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Fetch X posts for tickers and return them with the analysis prompt baked in.

        The Telegram-side LLM (or any caller) reads ``analysis_prompt.system``
        and ``analysis_prompt.user`` from the response and runs them against
        its own model to produce the final markdown sentiment report.
        """
        if not isinstance(tickers, list) or not tickers:
            raise HermesIntegrationError(
                "tickers must be a non-empty list of strings")
        if not 1 <= days <= 30:
            raise HermesIntegrationError("days must be between 1 and 30")
        if not 5 <= limit_per_ticker <= 200:
            raise HermesIntegrationError(
                "limit_per_ticker must be between 5 and 200")

        from trading.stocks.social_analyzer import analyze_tickers
        from trading.stocks.formatters import render_x_summary_markdown_v2

        try:
            payload = analyze_tickers(
                tickers,
                days=days,
                limit_per_ticker=limit_per_ticker,
                persist=persist,
            )
        except ValueError as exc:
            raise HermesIntegrationError(str(exc)) from exc
        payload["telegram_markdown_v2"] = render_x_summary_markdown_v2(payload)
        return _with_operational_hints(
            payload,
            preferred_execution="agent_or_native",
            agent_reminder_min_interval_minutes=60,
            fallback_when_provider_429=(
                "Send telegram_markdown_v2 directly when the richer analysis_prompt path hits provider 429s."
            ),
        )

    def dispatch_tool_call(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Invoke a Hermes-registered tool by name with validated arguments."""
        args = arguments or {}
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "momentum_scan": self.momentum_scan,
            "momentum_zone_watch": self.momentum_zone_watch,
            "momentum_playbook": self.momentum_playbook,
            "market_scan": self.market_scan,
            "market_playbook": self.market_playbook,
            "options_scan": self.options_scan,
            "options_registry_build": self.options_registry_build,
            "options_registry_show": self.options_registry_show,
            "options_hidden_gems": self.options_hidden_gems,
            "options_sp500_weekly": self.options_sp500_weekly,
            "options_opportunities": self.options_opportunities,
            "cot_report": self.cot_report,
            "cot_history": self.cot_history,
            "weekly_plan": self.weekly_plan,
            "position_review": self.position_review,
            "theory_v2_scan": self.theory_v2_scan,
            "strategy_context": self.strategy_context,
            "recommend_position": self.recommend_position,
            "scan_history": self.scan_history,
            "stocks_ism_report": self.stocks_ism_report,
            "stocks_ism_calendar": self.stocks_ism_calendar,
            "stocks_politicians_scan": self.stocks_politicians_scan,
            "stocks_x_analyze": self.stocks_x_analyze,
        }

        handler = handlers.get(tool_name)
        if handler is None:
            raise HermesIntegrationError(f"Unknown Hermes tool: {tool_name}")

        try:
            result = handler(**args)
        except TypeError as exc:
            raise HermesIntegrationError(
                f"Invalid arguments for {tool_name}: {exc}") from exc

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
            as_of = datetime.fromisoformat(
                as_of_date).replace(tzinfo=timezone.utc)
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
