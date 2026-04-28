"""Historical COT analyzer for calendar-window variation reports."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

import pandas as pd


class COTHistoricalAnalyzer:
    """Build precise historical variation tables from raw weekly COT rows."""

    def generate_historical_variation(
        self,
        *,
        months: int,
        cot_data: dict[str, Any],
        as_of_date: str | None = None,
    ) -> dict[str, Any]:
        """Generate period deltas for last week and the last N calendar months."""
        if months < 1:
            raise ValueError("months must be >= 1")

        asset_frames: dict[str, pd.DataFrame] = {}
        for asset, raw in cot_data.items():
            rows = raw.get("raw", []) if isinstance(raw, dict) else []
            frame = self._build_history_frame(rows)
            if not frame.empty:
                asset_frames[asset] = frame

        if not asset_frames:
            return {
                "months": months,
                "as_of_date": as_of_date or "N/A",
                "assets": {},
                "observations": ["No historical COT rows available for report generation."],
            }

        as_of = self._resolve_report_as_of_date(
            cot_data=cot_data,
            asset_frames=asset_frames,
            override=as_of_date,
        )

        per_asset: dict[str, list[dict[str, Any]]] = {}
        for asset in sorted(asset_frames.keys()):
            periods = self._build_asset_period_rows(asset_frames[asset], months, as_of)
            if periods:
                per_asset[asset] = periods

        observations = self._generate_historical_observations(per_asset, months)
        return {
            "months": months,
            "as_of_date": as_of.isoformat(),
            "assets": per_asset,
            "observations": observations,
        }

    def _build_history_frame(self, rows: list[dict[str, Any]]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame()

        df["report_date"] = df.apply(self._parse_history_row_date, axis=1)
        df = df.dropna(subset=["report_date"]).sort_values("report_date")
        if df.empty:
            return pd.DataFrame()

        metrics = df.apply(self._extract_row_metrics, axis=1, result_type="expand")
        out = pd.concat(
            [df[["report_date"]].reset_index(drop=True), metrics.reset_index(drop=True)],
            axis=1,
        )
        out = out.drop_duplicates(subset=["report_date"], keep="last").reset_index(drop=True)
        return out

    def _resolve_report_as_of_date(
        self,
        *,
        cot_data: dict[str, Any],
        asset_frames: dict[str, pd.DataFrame],
        override: str | None,
    ) -> date:
        if override:
            parsed = self._safe_parse_date(override)
            if parsed is not None:
                return parsed

        for asset in sorted(cot_data.keys()):
            raw = cot_data.get(asset, {})
            if not isinstance(raw, dict):
                continue
            for key in ("as_of_date", "latest_date", "report_date"):
                parsed = self._safe_parse_date(str(raw.get(key, "")))
                if parsed is not None:
                    return parsed

        latest = max(frame["report_date"].max() for frame in asset_frames.values())
        return latest.date() if isinstance(latest, pd.Timestamp) else latest

    def _build_asset_period_rows(
        self, frame: pd.DataFrame, months: int, as_of: date
    ) -> list[dict[str, Any]]:
        if frame.empty:
            return []

        df = frame[frame["report_date"].dt.date <= as_of].reset_index(drop=True)
        if df.empty:
            return []

        end_idx = len(df) - 1
        periods: list[dict[str, Any]] = []

        if end_idx >= 1:
            periods.append(
                self._compose_period_row(
                    df=df, label="Last Week", start_idx=end_idx - 1, end_idx=end_idx
                )
            )

        end_date = df.iloc[end_idx]["report_date"].date()
        for month in range(1, months + 1):
            target_start = self._subtract_calendar_months(end_date, month)
            start_candidates = df.index[df["report_date"].dt.date >= target_start].tolist()
            start_idx = start_candidates[0] if start_candidates else 0
            label = f"Last {month} Month" if month == 1 else f"Last {month} Months"
            periods.append(
                self._compose_period_row(df=df, label=label, start_idx=start_idx, end_idx=end_idx)
            )

        return periods

    def _compose_period_row(
        self, *, df: pd.DataFrame, label: str, start_idx: int, end_idx: int
    ) -> dict[str, Any]:
        start_row = df.iloc[start_idx]
        end_row = df.iloc[end_idx]

        start_date = start_row["report_date"].date()
        end_date = end_row["report_date"].date()

        return {
            "period": label,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "net_non_commercial": int(end_row["net_non_commercial"]),
            "net_non_commercial_delta": int(
                end_row["net_non_commercial"] - start_row["net_non_commercial"]
            ),
            "net_commercial": int(end_row["net_commercial"]),
            "net_commercial_delta": int(end_row["net_commercial"] - start_row["net_commercial"]),
            "open_interest": int(end_row["open_interest"]),
            "open_interest_delta": int(end_row["open_interest"] - start_row["open_interest"]),
            "pct_oi": round(float(end_row["pct_oi"]), 1),
            "pct_oi_delta": round(float(end_row["pct_oi"] - start_row["pct_oi"]), 1),
            "traders_non_commercial": self._optional_int(end_row.get("traders_non_commercial")),
            "traders_non_commercial_start": self._optional_int(
                start_row.get("traders_non_commercial")
            ),
            "traders_commercial": self._optional_int(end_row.get("traders_commercial")),
            "traders_commercial_start": self._optional_int(start_row.get("traders_commercial")),
        }

    def _generate_historical_observations(
        self,
        per_asset: dict[str, list[dict[str, Any]]],
        months: int,
    ) -> list[str]:
        observations: list[str] = []
        target_label = f"Last {months} Month" if months == 1 else f"Last {months} Months"

        for asset, rows in per_asset.items():
            period_row = next((r for r in rows if r["period"] == target_label), None)
            if period_row is None:
                continue

            non_comm_delta = period_row["net_non_commercial_delta"]
            comm_delta = period_row["net_commercial_delta"]
            oi_delta = period_row["open_interest_delta"]

            if non_comm_delta > 0:
                observations.append(
                    f"{asset}: Non-Commercial net exposure increased over the last {months} month(s) (bullish crowding build-up)."
                )
            elif non_comm_delta < 0:
                observations.append(
                    f"{asset}: Non-Commercial net exposure decreased over the last {months} month(s) (spec positioning unwind)."
                )

            if comm_delta > 0:
                observations.append(
                    f"{asset}: Commercial net exposure increased over the last {months} month(s)."
                )
            elif comm_delta < 0:
                observations.append(
                    f"{asset}: Commercial net exposure decreased over the last {months} month(s)."
                )

            if oi_delta > 0:
                observations.append(f"{asset}: Open Interest expanded across the selected horizon.")
            elif oi_delta < 0:
                observations.append(
                    f"{asset}: Open Interest contracted across the selected horizon."
                )

        return observations

    @staticmethod
    def _subtract_calendar_months(anchor: date, months: int) -> date:
        year = anchor.year
        month = anchor.month - months
        while month <= 0:
            month += 12
            year -= 1
        day = min(
            anchor.day,
            [
                31,
                29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                31,
                30,
                31,
                30,
                31,
                31,
                30,
                31,
                30,
                31,
            ][month - 1],
        )
        return date(year, month, day)

    @staticmethod
    def _safe_parse_date(value: str) -> date | None:
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(value[:10], fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None

    def _parse_history_row_date(self, row: pd.Series) -> pd.Timestamp | None:
        for key in (
            "report_date_as_yyyy_mm_dd",
            "report_date_as_of_yyyy_mm_dd",
            "Report_Date_as_of",
            "report_date",
            "date",
        ):
            if key in row and pd.notna(row.get(key)):
                parsed = pd.to_datetime(str(row.get(key)), errors="coerce")
                if pd.notna(parsed):
                    return parsed

        raw_id = str(row.get("id", ""))
        if len(raw_id) >= 6 and raw_id[:6].isdigit():
            parsed = pd.to_datetime(raw_id[:6], format="%y%m%d", errors="coerce")
            if pd.notna(parsed):
                return parsed

        report_week = str(row.get("report_week", ""))
        match = re.search(r"(\d{4})\s+Report Week\s+(\d{1,2})", report_week)
        if match:
            year = int(match.group(1))
            week = int(match.group(2))
            try:
                return pd.Timestamp(datetime.fromisocalendar(year, week, 2))
            except ValueError:
                return None

        return None

    def _extract_row_metrics(self, row: pd.Series) -> pd.Series:
        noncomm_long = self._first_numeric_from_row(
            row, ["noncomm_positions_long_all", "Noncommercial_Positions_Long"]
        )
        noncomm_short = self._first_numeric_from_row(
            row, ["noncomm_positions_short_all", "Noncommercial_Positions_Short"]
        )

        if noncomm_long is None:
            noncomm_long = sum(
                self._first_numeric_from_row(row, [name]) or 0.0
                for name in [
                    "asset_mgr_positions_long",
                    "lev_money_positions_long",
                    "other_rept_positions_long",
                ]
            )
            noncomm_short = sum(
                self._first_numeric_from_row(row, [name]) or 0.0
                for name in [
                    "asset_mgr_positions_short",
                    "lev_money_positions_short",
                    "other_rept_positions_short",
                ]
            )

        net_noncomm = (noncomm_long or 0.0) - (noncomm_short or 0.0)

        comm_long = self._first_numeric_from_row(
            row, ["comm_positions_long_all", "Commercial_Positions_Long"]
        )
        comm_short = self._first_numeric_from_row(
            row, ["comm_positions_short_all", "Commercial_Positions_Short"]
        )
        if comm_long is None and "dealer_positions_long_all" in row:
            comm_long = self._safe_float(row.get("dealer_positions_long_all"))
            comm_short = self._safe_float(row.get("dealer_positions_short_all"))
        net_comm = (comm_long or 0.0) - (comm_short or 0.0)

        oi = self._first_numeric_from_row(row, ["open_interest_all", "Open_Interest_All"]) or 0.0
        pct_oi = (net_noncomm / oi * 100) if oi else 0.0

        traders_noncomm = self._extract_trader_count(
            row,
            direct_aliases=[
                "number_of_traders_noncommercial_all",
                "Number_of_Traders_Noncommercial_All",
                "number_traders_noncommercial_all",
            ],
            long_aliases=[
                "traders_noncomm_long_all",
                "traders_noncomm_long_old",
                "traders_noncomm_long_other",
            ],
            short_aliases=[
                "traders_noncomm_short_all",
                "traders_noncomm_short_old",
                "traders_noncomm_short_other",
            ],
            fallback_sum_aliases=[
                "traders_asset_mgr_long_all",
                "traders_lev_money_long_all",
                "traders_other_rept_long_all",
            ],
        )
        traders_comm = self._extract_trader_count(
            row,
            direct_aliases=[
                "number_of_traders_commercial_all",
                "Number_of_Traders_Commercial_All",
                "number_traders_commercial_all",
            ],
            long_aliases=[
                "traders_comm_long_all",
                "traders_comm_long_old",
                "traders_comm_long_other",
            ],
            short_aliases=[
                "traders_comm_short_all",
                "traders_comm_short_old",
                "traders_comm_short_other",
            ],
            fallback_sum_aliases=["traders_dealer_long_all"],
        )

        return pd.Series(
            {
                "net_non_commercial": int(round(net_noncomm)),
                "net_commercial": int(round(net_comm)),
                "open_interest": int(round(oi)),
                "pct_oi": round(float(pct_oi), 1),
                "traders_non_commercial": traders_noncomm,
                "traders_commercial": traders_comm,
            }
        )

    def _extract_trader_count(
        self,
        row: pd.Series,
        *,
        direct_aliases: list[str],
        long_aliases: list[str],
        short_aliases: list[str],
        fallback_sum_aliases: list[str],
    ) -> int | None:
        direct = self._first_numeric_from_row(row, direct_aliases)
        if direct is not None and direct > 0:
            return int(round(direct))

        long_val = self._first_numeric_from_row(row, long_aliases)
        short_val = self._first_numeric_from_row(row, short_aliases)
        if long_val is not None or short_val is not None:
            return int(round(max(long_val or 0.0, short_val or 0.0)))

        fallback_values = [
            self._first_numeric_from_row(row, [name]) for name in fallback_sum_aliases
        ]
        fallback_values = [v for v in fallback_values if v is not None]
        if fallback_values:
            return int(round(sum(fallback_values)))

        return None

    def _first_numeric_from_row(self, row: pd.Series, aliases: list[str]) -> float | None:
        for name in aliases:
            if name in row and pd.notna(row.get(name)):
                return self._safe_float(row.get(name), default=0.0)
        return None

    def _optional_int(self, val: Any) -> int | None:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_float(val: Any, default: float = 0.0) -> float:
        if val is None:
            return default
        try:
            value = float(val)
            return default if math.isnan(value) else value
        except (ValueError, TypeError):
            return default
