"""Agent-facing formatters for options analysis payloads."""

from __future__ import annotations

from typing import Any


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _fmt_money(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_num(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _short_strategy(value: Any) -> str:
    strategy = str(value or "n/a").replace("_", " ")
    replacements = {
        "bull put credit spread": "bull put",
        "bear call credit spread": "bear call",
        "bull call debit spread": "bull call",
        "bear put debit spread": "bear put",
    }
    return replacements.get(strategy, strategy)


def render_equity_universe_scan_discord_es(
    payload: dict[str, Any],
    *,
    command: str | None = None,
    limit: int | None = None,
    max_ranked: int | None = None,
) -> str:
    """Render a Spanish Discord-ready S&P 500 options scan report."""
    summary = payload.get("summary") or {}
    ranked = list(payload.get("ranked") or [])
    warnings = list(payload.get("warnings") or [])
    scan_status = str(summary.get("scan_status") or "unknown")
    trade_candidates = int(summary.get("trade_candidates") or 0)
    tickers_requested = int(summary.get("tickers_requested") or 0)
    tickers_scanned = int(summary.get("tickers_scanned") or 0)
    errors = int(summary.get("errors") or 0)
    coverage = summary.get("coverage_ratio")

    if scan_status == "inconclusive":
        verdict = "DATOS INSUFICIENTES / RERUN"
        lead = (
            "Nave no tuvo cobertura suficiente para emitir una lectura semanal confiable. "
            "No interpretar este resultado como NO TRADE; repetir el scan durante horario regular "
            "de opciones US."
        )
    elif trade_candidates == 0:
        verdict = "NO TRADE / STAND ASIDE"
        lead = "Nave no encontro setups accionables bajo los filtros actuales."
    else:
        verdict = "SETUPS DETECTADOS / REVISAR EJECUCION"
        lead = "Validar liquidez, EV y riesgo antes de operar."

    ranked_limit = max_ranked if max_ranked is not None else int(
        summary.get("top_trades_returned") or len(ranked)
    )

    lines = [
        "## Opciones S&P 500 - Nave",
        "",
        "## Resumen",
        f"**Veredicto operativo:** **{verdict}**",
        "",
        lead,
        "",
        f"- Solicitados: {tickers_requested} | validos: {tickers_scanned} | errores: {errors}",
        f"- Candidates: {trade_candidates} | top devueltos: {summary.get('top_trades_returned')}",
        f"- Estado: `{scan_status}`",
    ]
    if coverage is not None:
        lines.append(f"- Cobertura valida: {_fmt_pct(float(coverage) * 100.0)}")
    if command:
        lines.append(
            f"- Cmd: `sp500-scan limit={limit or tickers_requested} "
            f"top={summary.get('top_trades_returned')} dte={payload.get('days_to_exp')}`"
        )

    if warnings:
        lines.extend(["", "## Alerta de calidad de datos"])
        for warning in warnings[:3]:
            lines.append(f"- {warning}")

    lines.extend(["", "## Mejores oportunidades"])
    if scan_status == "inconclusive":
        lines.append(
            "No publicar oportunidades ni conclusion de no-trade: el scan debe repetirse con "
            "mejor cobertura de cadenas."
        )
    elif not ranked:
        lines.append("No hay oportunidades ejecutables segun Nave.")
    else:
        for idx, item in enumerate(ranked[:ranked_limit], start=1):
            strategy = _short_strategy(item.get("strategy_name"))
            setup = item.get("setup_summary")
            setup_text = f" | {setup}" if setup else ""
            lines.append(
                f"{idx}. **{item.get('ticker')}** {strategy} | "
                f"S {_fmt_num(item.get('composite_score'))} | "
                f"PoP {_fmt_pct(item.get('pop'))} | "
                f"T {_fmt_pct(item.get('probability_of_touch'))} | "
                f"EV {_fmt_money(item.get('expected_value'))}{setup_text}"
            )

    lines.extend(["", "## Entradas / zonas"])
    if scan_status == "inconclusive":
        lines.append("No abrir entradas desde este resultado. Repetir scan antes de operar.")
    elif ranked:
        lines.append("Usar solo setups listados; confirmar bid/ask, OI y sizing antes de entrar.")
    else:
        lines.append("No hay entradas validas.")

    lines.extend(["", "## Riesgo / invalidacion"])
    if scan_status == "inconclusive":
        lines.append(
            "Invalidacion del reporte: cobertura insuficiente. El riesgo principal es convertir "
            "un fallo de datos/liquidez en una conclusion operativa falsa."
        )
    elif ranked:
        lines.append(
            "Invalidar si se deteriora liquidez, el precio toca zona de riesgo antes de entrada, "
            "o Nave deja de marcarlo como candidato."
        )
    else:
        lines.append("Mientras Nave devuelva 0 trade candidates con cobertura completa, el plan es no operar.")

    lines.extend(["", "## Seguimiento"])
    if scan_status == "inconclusive":
        lines.append("- Repetir durante horario regular de opciones US.")
        lines.append("- Exigir cobertura suficiente antes de publicar veredicto operativo.")
    else:
        lines.append("- Repetir si cambia la volatilidad, liquidez o estructura de spreads.")
        lines.append("- Priorizar setups con EV positivo, touch controlado y riesgo definido.")

    lines.extend(["", "## Liquidez"])
    if scan_status == "inconclusive":
        lines.append(
            "El bloqueo principal fue calidad/cobertura de datos. Esto suele ocurrir premarket "
            "o con cadenas parciales del proveedor."
        )
    elif errors:
        lines.append(
            f"{errors} tickers fallaron por datos, liquidez o ausencia de candidatos. "
            "No forzar trades en esas cadenas."
        )
    else:
        lines.append("No se detectaron bloqueos amplios de cobertura en el scan.")

    if limit is not None:
        lines.append(f"Universo: Top {limit} S&P 500 / SP500")
    return "\n".join(lines)


def render_options_scan_markdown_v2(payload: dict[str, Any]) -> list[str]:
    """Render a compact Telegram MarkdownV2 digest for Hermes output."""
    ticker = str(payload.get("ticker") or "?")
    underlying = payload.get("underlying_analysis") or {}
    overlay = payload.get("analysis_overlay") or {}
    price = underlying.get("price")
    iv = (underlying.get("implied_volatility") or {}).get("iv_mean")
    hv = (underlying.get("historical_volatility") or {}).get("hv_30")
    final_recs = overlay.get("final_recommendations") or {}
    trade_decision = overlay.get("trade_decision") or {}
    executive_summary = list(overlay.get("executive_summary") or [])
    warnings = list(overlay.get("warnings") or [])

    recs = payload.get("recommendations") or []
    lines = [
        "*NAVE Options Scan*",
        f"Ticker: *{ticker}*",
        f"Price: {price}",
        f"IV mean / HV30: {iv} / {hv}",
    ]

    if executive_summary:
        lines.append("Executive summary:")
        for bullet in executive_summary[:2]:
            lines.append(f"- {bullet}")

    conservative = final_recs.get("best_conservative_executable_setup") or {}
    aggressive = final_recs.get("best_aggressive_setup") or {}
    modeled = final_recs.get("best_modeled_setup") or {}
    if modeled:
        lines.append(
            "Modeled: "
            f"{str(modeled.get('strategy_name') or 'n/a').replace('_', ' ')}"
            f" | EV {(modeled.get('metrics') or {}).get('expected_value')}"
        )
    if trade_decision:
        decision = str(trade_decision.get("status") or "unknown").replace("_", " ")
        lines.append(f"Decision: {decision} | {trade_decision.get('reason')}")
    if conservative:
        lines.append(
            "Conservative: "
            f"{str(conservative.get('strategy_name') or 'n/a').replace('_', ' ')}"
            f" | EV {(conservative.get('metrics') or {}).get('expected_value')}"
        )
    if aggressive:
        lines.append(
            "Aggressive: "
            f"{str(aggressive.get('strategy_name') or 'n/a').replace('_', ' ')}"
            f" | EV {(aggressive.get('metrics') or {}).get('expected_value')}"
        )

    if recs:
        lines.append("Top strategies:")
        for idx, rec in enumerate(recs[:3], start=1):
            strategy = ((rec.get("strategy") or {}).get(
                "name") or "unknown").replace("_", " ")
            score = (rec.get("metrics") or {}).get("composite_score")
            pop = (rec.get("metrics") or {}).get("pop")
            ev = (rec.get("metrics") or {}).get("expected_value")
            touch = (rec.get("metrics") or {}).get("probability_of_touch")
            tradeoff = rec.get("tradeoff_comment") or ""
            lines.append(
                f"{idx}. {strategy} | score {score} | PoP {pop}% | EV {ev} | Touch {touch}%")
            if tradeoff:
                lines.append(f"   - {tradeoff}")

    if warnings:
        lines.append("Warnings:")
        for warning in warnings[:3]:
            lines.append(f"- {warning}")

    return ["\n".join(lines)]


def render_options_opportunities_markdown_v2(payload: dict[str, Any]) -> list[str]:
    """Render BTC/ETH options opportunity scan as Telegram MarkdownV2 digest."""
    summary = payload.get("summary") or {}
    momentum = payload.get("momentum") or {}
    ranked = list(payload.get("ranked") or [])
    opportunities = payload.get("opportunities") or {}

    lines = [
        "*NAVE Options Opportunities*",
        f"Coins requested: {summary.get('coins_requested')}",
        f"Momentum allowed: {summary.get('momentum_allowed')}",
        f"Options ready: {summary.get('options_ready')}",
    ]

    tf = momentum.get("timeframes") or {}
    if tf:
        lines.append(
            f"Timeframes: bias {tf.get('bias')} | setup {tf.get('setup')} | trigger {tf.get('trigger')}"
        )

    if ranked:
        lines.append("Top opportunities:")
        for idx, item in enumerate(ranked[:3], start=1):
            strategy = str(item.get("strategy_name")
                           or "n/a").replace("_", " ")
            lines.append(
                f"{idx}. {item.get('coin')} {strategy} | score {item.get('strategy_score')} | EV {item.get('expected_value')}"
            )

    blocked = []
    unavailable = []
    for coin, entry in opportunities.items():
        status = str((entry or {}).get("status") or "")
        if status == "filtered_by_momentum":
            blocked.append(coin)
        elif status == "options_unavailable":
            unavailable.append(coin)

    if blocked:
        lines.append("Momentum filtered: " + ", ".join(sorted(blocked)))
    if unavailable:
        lines.append("Options unavailable: " + ", ".join(sorted(unavailable)))

    return ["\n".join(lines)]


def render_hidden_gems_markdown_v2(payload: dict[str, Any]) -> list[str]:
    """Telegram digest for hidden-gem equity scan."""
    gems_block = payload.get("hidden_gems") or payload
    gems = list(gems_block.get("gems") or [])
    filt = gems_block.get("filter") or {}
    lines = [
        "*NAVE Hidden Gems*",
        f"Prospects: {gems_block.get('actionable_gems', len(gems))}",
        f"X snapshots: {gems_block.get('x_snapshots_loaded', 0)}",
    ]
    if filt:
        lines.append(
            f"Filters: pop>={filt.get('min_pop')} touch<{filt.get('max_touch')} "
            "bullish bull-put only"
        )
    for idx, item in enumerate(gems[:6], start=1):
        metrics = item.get("metrics") or {}
        strategy = str(item.get("strategy") or "n/a").replace("_", " ")
        reasons = "; ".join(item.get("reasons") or [])[:120]
        lines.append(
            f"{idx}. *{item.get('ticker')}* [{item.get('tier')}] "
            f"score {item.get('gem_score')} {strategy} "
            f"PoP {metrics.get('pop')}% touch {metrics.get('probability_of_touch')}%"
        )
        if reasons:
            lines.append(f"   {reasons}")
    if not gems:
        lines.append("_No names passed refined filters today._")
    return ["\n".join(lines)]
