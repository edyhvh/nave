"""Formatting utilities for COT weekly and historical reports."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


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

    def normalize_payload(self, value: Any) -> Any:
        """Convert dataclass payloads into plain Python structures for JSON output."""
        if is_dataclass(value):
            return asdict(value)
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
