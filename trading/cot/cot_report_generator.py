"""Formatting utilities for COT weekly and historical reports."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, cast


class COTReportGenerator:
    """Render COT report payloads into stable text/JSON-friendly structures."""

    @staticmethod
    def format_signed(value: Any) -> str:
        if value is None:
            return "N/A"
        return f"{int(value):+,}"

    @staticmethod
    def format_int(value: Any) -> str:
        if value is None:
            return "N/A"
        return f"{int(value):,}"

    @staticmethod
    def format_pct(value: Any) -> str:
        if value is None:
            return "N/A"
        return f"{float(value):.1f}%"

    def format_section_lines(self, section: dict[str, Any] | None) -> list[str]:
        """Format Futures/Options/Combined section lines with trader counts."""
        if not section:
            return [
                "Net Non-Comm: N/A (Δ N/A)     | % of OI: N/A",
                "Net Commercial: N/A (Δ N/A)",
                "Open Interest: N/A (Δ N/A)",
                "# Traders: Non-Comm: N/A | Commercial: N/A",
            ]

        return [
            f"Net Non-Comm: {self.format_signed(section.get('net_non_commercial'))} (Δ {self.format_signed(section.get('net_non_commercial_delta'))})     | % of OI: {self.format_pct(section.get('pct_oi'))}",
            f"Net Commercial: {self.format_signed(section.get('net_commercial'))} (Δ {self.format_signed(section.get('net_commercial_delta'))})",
            f"Open Interest: {self.format_int(section.get('open_interest'))} (Δ {self.format_signed(section.get('open_interest_delta'))})",
            f"# Traders: Non-Comm: {self.format_int(section.get('traders_non_commercial'))} | Commercial: {self.format_int(section.get('traders_commercial'))}",
        ]

    def render_historical_markdown(
        self,
        *,
        months: int,
        as_of: str,
        per_asset: dict[str, list[dict[str, Any]]],
        observations: list[str],
    ) -> str:
        """Render the historical variation report in the current markdown format."""
        lines: list[str] = [
            f"NAVE COT HISTORICAL VARIATION REPORT - Last {months} Months (as-of {as_of})",
            "",
        ]

        for asset, rows in per_asset.items():
            lines.append(f"[{asset}]")
            lines.append(
                "| Period | Dates | Net Non-Comm (Delta) | Net Commercial (Delta) | OI (Delta) | %OI (Delta) | # Traders Non-Comm | # Traders Comm |"
            )
            lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
            for row in rows:
                lines.append(
                    "| "
                    f"{row['period']} | "
                    f"{row['start_date']} to {row['end_date']} | "
                    f"{self.format_signed(row['net_non_commercial'])} ({self.format_signed(row['net_non_commercial_delta'])}) | "
                    f"{self.format_signed(row['net_commercial'])} ({self.format_signed(row['net_commercial_delta'])}) | "
                    f"{self.format_int(row['open_interest'])} ({self.format_signed(row['open_interest_delta'])}) | "
                    f"{self.format_pct(row['pct_oi'])} ({self.format_pct(row['pct_oi_delta'])}) | "
                    f"{self._format_trader_range(row['traders_non_commercial_start'], row['traders_non_commercial'])} | "
                    f"{self._format_trader_range(row['traders_commercial_start'], row['traders_commercial'])} |"
                )
            lines.append("")

        if observations:
            lines.append("Key Observations:")
            for obs in observations:
                lines.append(f"- {obs}")

        return "\n".join(lines).strip()

    def render_weekly_plan_markdown(self, weekly_plan: dict[str, Any]) -> str:
        """Render a detailed, operator-friendly weekly execution plan."""
        lines: list[str] = ["NAVE WEEKLY COT EXECUTION PLAN", ""]
        generated_at = str(weekly_plan.get("generated_at", "N/A"))
        lines.append(f"Generated At: {generated_at}")
        lines.append("")

        assets = weekly_plan.get("assets", {})
        for asset, plan in assets.items():
            lines.append(f"[{asset}]")
            lines.append(
                f"Bias: {str(plan.get('bias', 'neutral')).upper()} | Confidence: {float(plan.get('confidence', 0.0)):.0%}"
            )
            lines.append(f"Explanation: {plan.get('bias_explanation', 'N/A')}")

            levels = plan.get("key_levels", {})
            lines.append(
                "Key Levels: "
                f"S: {levels.get('swing_low', 'N/A')} | "
                f"EQ: {levels.get('equilibrium', 'N/A')} | "
                f"R: {levels.get('swing_high', 'N/A')}"
            )

            lines.append("Setups:")
            for setup in plan.get("setups", []):
                entry_zone = setup.get("entry_zone", {})
                tp_levels = setup.get("take_profit_levels", [])
                tp_line = ", ".join(
                    [f"{tp.get('label')}: {tp.get('price')} ({tp.get('rr')}R)" for tp in tp_levels]
                )
                lines.append(
                    f"- {setup.get('name')}: {str(setup.get('direction', 'long')).upper()} | "
                    f"Entry Zone {entry_zone.get('low')} - {entry_zone.get('high')} | "
                    f"SL {setup.get('stop_loss')} | TPs {tp_line}"
                )
                lines.append(
                    f"  Risk {float(setup.get('recommended_risk_pct', 0.0)) * 100:.2f}% | "
                    f"Risk Budget ${float(setup.get('position_size_usd', 0.0)):.2f} | "
                    f"Size {setup.get('position_size_coin')} | Notional@10x ${float(setup.get('notional_usd_10x', 0.0)):.2f}"
                )
                lines.append(f"  Rationale: {setup.get('rationale', 'N/A')}")

            notes = plan.get("risk_management_notes", [])
            if notes:
                lines.append("Risk Notes:")
                for note in notes:
                    lines.append(f"- {note}")
            lines.append("")

        return "\n".join(lines).strip()

    def normalize_payload(self, value: Any) -> Any:
        """Convert dataclass payloads into plain Python structures for JSON output."""
        if is_dataclass(value):
            try:
                return asdict(cast(Any, value))
            except TypeError:
                return value
        if isinstance(value, dict):
            return {k: self.normalize_payload(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.normalize_payload(v) for v in value]
        return value

    def _format_trader_range(self, start: int | None, end: int | None) -> str:
        if end is None and start is None:
            return "N/A"
        if end is None:
            return self.format_int(start)
        if start is None or start == end:
            return self.format_int(end)
        return f"{self.format_int(start)} -> {self.format_int(end)}"
