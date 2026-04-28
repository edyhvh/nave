from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RECENT_PERIODS = {
    "2023-recovery",
    "2024-ETF-approval",
    "2024-2025-bull",
    "TODAY",
}


def latest_artifacts(raw_dir: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    latest: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(raw_dir.glob("momentum_backtest_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        period = str(payload.get("period", path.stem))
        latest[period] = (path, payload)
    return latest


def _band(score: int) -> str:
    if score >= 90:
        return "90-100"
    if score >= 80:
        return "80-89"
    if score >= 75:
        return "75-79"
    return "<75"


def _readiness_summary(periods: list[dict[str, Any]], bands_out: list[dict[str, Any]]) -> dict[str, Any]:
    total_periods = len(periods)
    complete_periods = sum(1 for row in periods if row["complete"])
    high_confidence = next((row for row in bands_out if row["band"] == "90-100"), None)
    focus_periods = [
        row["period"]
        for row in periods
        if row["period"] in RECENT_PERIODS
        and (
            not row["complete"]
            or row["win_rate"] < 0.7
            or row["expectancy"] < 1.25
            or row["pct_reaching_8"] < 0.5
        )
    ]

    reasons: list[str] = []
    if high_confidence:
        reasons.append(
            f"La banda 90-100 mantiene {high_confidence['win_rate']:.2%} de win rate con {high_confidence['avg_r']:+.2f}R promedio."
        )
    if focus_periods:
        reasons.append(f"Los periodos que aun requieren vigilancia operativa son: {', '.join(focus_periods)}.")
    if complete_periods < max(total_periods - 1, 1):
        reasons.append("La cobertura historica todavia tiene mas de un periodo parcial.")

    status = "research-only"
    if high_confidence and complete_periods >= max(total_periods - 1, 1):
        if high_confidence["count"] >= 100 and high_confidence["win_rate"] >= 0.75 and high_confidence["avg_r"] >= 1.5:
            status = "shadow-ready"
        elif high_confidence["win_rate"] >= 0.7 and high_confidence["avg_r"] >= 1.25:
            status = "candidate-ready"

    return {
        "status": status,
        "focus_periods": focus_periods,
        "reasons": reasons,
    }


def _recommendation(readiness: dict[str, Any]) -> str:
    focus_periods = readiness.get("focus_periods", [])
    focus_text = ", ".join(focus_periods)

    if readiness.get("status") == "shadow-ready":
        if focus_text:
            return (
                "Modelo listo para shadow deployment con umbral operativo de 90; "
                f"vigilar la extension real de los setups en {focus_text}."
            )
        return "Modelo listo para shadow deployment con umbral operativo de 90 y revision manual de perdedores aislados."

    if readiness.get("status") == "candidate-ready":
        if focus_text:
            return f"Modelo apto para paper trading; concentrar el siguiente refinamiento en {focus_text}."
        return "Modelo apto para paper trading; mantener parametros y revisar perdedores manualmente."

    return "Modelo todavia en fase de investigacion; no relajar filtros hasta cerrar los periodos debiles restantes."


def _warning(code: str, severity: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
    }


def _automation_summary(periods: list[dict[str, Any]], readiness: dict[str, Any], total_trades: int) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    partial_periods = [row["period"] for row in periods if not row["complete"]]
    if partial_periods:
        warnings.append(
            _warning(
                "partial_regimes",
                "warning",
                f"Historical coverage is still partial for: {', '.join(partial_periods)}.",
            )
        )

    focus_periods = readiness.get("focus_periods", [])
    if focus_periods:
        warnings.append(
            _warning(
                "focus_periods",
                "warning",
                f"Recent regimes still requiring operator review: {', '.join(focus_periods)}.",
            )
        )

    today_row = next((row for row in periods if row["period"] == "TODAY"), None)
    if today_row and int(today_row.get("trade_count", 0) or 0) < 10:
        warnings.append(
            _warning(
                "today_low_sample",
                "warning",
                f"TODAY has only {today_row['trade_count']} trades; keep live rollout in shadow mode until more live-window observations accumulate.",
            )
        )

    if total_trades < 100:
        warnings.append(
            _warning(
                "aggregate_sample",
                "warning",
                f"Only {total_trades} aggregate trades are represented in the latest review; treat regime-level stability as provisional.",
            )
        )

    ready = readiness.get("status") == "shadow-ready" and not any(warning["severity"] == "error" for warning in warnings)
    return {
        "ready": ready,
        "warnings": warnings,
    }


def build_review_summary(raw_dir: Path) -> dict[str, Any]:
    latest = latest_artifacts(raw_dir)
    periods: list[dict[str, Any]] = []
    bands: dict[str, dict[str, float]] = {}
    pooled_trades = 0

    for period in [
        "2017-bull+2018-bear",
        "2019-recovery",
        "2020-covid-crash",
        "2020-recovery+2021-ATH",
        "2022-bear",
        "2023-recovery",
        "2024-ETF-approval",
        "2024-2025-bull",
        "TODAY",
    ]:
        if period not in latest:
            continue
        path, payload = latest[period]
        pooled = payload.get("pooled", {})
        metrics = pooled.get("metrics", {})
        periods.append(
            {
                "period": period,
                "complete": payload.get("coverage", {}).get("complete", True),
                "trade_count": pooled.get("trade_count", 0),
                "win_rate": metrics.get("win_rate", 0.0),
                "expectancy": metrics.get("expectancy", 0.0),
                "max_drawdown": metrics.get("max_drawdown", 0.0),
                "pct_reaching_8": metrics.get("pct_reaching_8", 0.0),
                "artifact": str(path),
            }
        )
        pooled_trades += int(pooled.get("trade_count", 0) or 0)
        for result in payload.get("results", {}).values():
            for trade in result.get("trades", []):
                band = _band(int(trade.get("confidence_score", 0) or 0))
                bucket = bands.setdefault(band, {"count": 0, "wins": 0.0, "r_sum": 0.0, "reach8": 0.0})
                bucket["count"] += 1
                bucket["wins"] += 1.0 if float(trade.get("r_multiple", 0.0)) > 0 else 0.0
                bucket["r_sum"] += float(trade.get("r_multiple", 0.0))
                bucket["reach8"] += 1.0 if bool(trade.get("reached_8_pct", False)) else 0.0

    bands_out = []
    for label in ["<75", "75-79", "80-89", "90-100"]:
        data = bands.get(label)
        if not data or not data["count"]:
            continue
        count = int(data["count"])
        bands_out.append(
            {
                "band": label,
                "count": count,
                "win_rate": round(data["wins"] / count, 4),
                "avg_r": round(data["r_sum"] / count, 4),
                "pct_reaching_8": round(data["reach8"] / count, 4),
            }
        )

    complete_periods = [row for row in periods if row["complete"]]
    partial_periods = [row for row in periods if not row["complete"]]
    readiness = _readiness_summary(periods, bands_out)
    recommendation = _recommendation(readiness)
    automation = _automation_summary(periods, readiness, pooled_trades)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "periods": periods,
        "confidence_bands": bands_out,
        "total_trades": pooled_trades,
        "complete_periods": len(complete_periods),
        "partial_periods": len(partial_periods),
        "readiness": readiness,
        "automation": automation,
        "recommendation": recommendation,
    }


def write_review_markdown(summary: dict[str, Any], output_path: Path) -> Path:
    periods = summary.get("periods", [])
    bands = summary.get("confidence_bands", [])
    readiness = summary.get("readiness", {})
    automation = summary.get("automation", {})
    focus_periods = readiness.get("focus_periods", [])
    lines = [
        "# Revision historica de momentum BTC / ETH",
        "",
        f"> Generado: {summary.get('generated_at', 'unknown')}",
        f"> Trades analizados: {summary.get('total_trades', 0)}",
        "",
        "## Resumen ejecutivo",
        "",
        f"- Periodos completos: {summary.get('complete_periods', 0)}",
        f"- Periodos parciales: {summary.get('partial_periods', 0)}",
        f"- Estado operativo: {readiness.get('status', 'unknown')}",
        f"- Automatizacion: {'lista para shadow' if automation.get('ready', False) else 'requiere supervision'}",
        f"- Recomendacion inicial: {summary.get('recommendation', 'sin recomendacion')}",
        "",
        "## Periodos",
        "",
        "| Periodo | Cobertura | Trades | Win rate | Expectancy | Max DD | >=8% |",
        "| ------- | --------- | ------ | -------- | ---------- | ------ | ---- |",
    ]
    for row in periods:
        coverage = "completa" if row["complete"] else "parcial"
        lines.append(
            f"| {row['period']} | {coverage} | {row['trade_count']} | {row['win_rate']:.2%} | {row['expectancy']:+.2f} | {row['max_drawdown']:.2f} | {row['pct_reaching_8']:.2%} |"
        )

    lines.extend(
        [
            "",
            "## Bandas de confianza",
            "",
            "| Banda | Trades | Win rate | Avg R | >=8% |",
            "| ----- | ------ | -------- | ----- | ---- |",
        ]
    )
    for row in bands:
        lines.append(
            f"| {row['band']} | {row['count']} | {row['win_rate']:.2%} | {row['avg_r']:+.2f} | {row['pct_reaching_8']:.2%} |"
        )

    if readiness.get("reasons"):
        lines.extend(
            [
                "",
                "## Preparacion operativa",
                "",
            ]
        )
        lines.extend(f"- {reason}" for reason in readiness["reasons"])

    if automation.get("warnings"):
        lines.extend(
            [
                "",
                "## Alertas de automatizacion",
                "",
            ]
        )
        lines.extend(f"- {warning['message']}" for warning in automation["warnings"])

    lines.extend(
        [
            "",
            "## Lectura",
            "",
            "- La banda 90-100 es la referencia principal para setups de mayor calidad.",
            (
                f"- Los periodos que merecen vigilancia inmediata son: {', '.join(focus_periods)}."
                if focus_periods
                else "- No hay periodos recientes en observacion inmediata bajo los umbrales actuales."
            ),
            "- TODAY debe evaluarse como ventana viva; no debe pedir barras futuras para considerarse completo.",
            "",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path