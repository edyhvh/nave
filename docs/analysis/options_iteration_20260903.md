STOCKS: Investigación de opciones — iteración acotada 2026-09-03

## Hipótesis

**HYPOTHESIS:** En un universo pequeño de acciones líquidas del S&P 500, los spreads definidos de crédito (bull put / bear call) seleccionados con PoP >= 60%, probabilidad de toque < 72% y aproximadamente 30 DTE mantienen expectativa positiva después de comisión y slippage realista durante un holding de 30 días.

- **Universo:** los primeros 10 símbolos devueltos por el universo S&P 500 del script; 30 observaciones símbolo/mes en tres entradas mensuales.
- **Timeframe:** entrada 2026-06-01, 2026-07-01 y 2026-08-01; salida a 30 días (2026-07-01, 2026-07-31 y 2026-08-31).
- **Estructura:** solo spreads definidos de crédito; nunca opciones desnudas.
- **Riesgo máximo:** el max loss modelado por spread y contrato x100; no se asumió tamaño de cuenta ni se autorizó ejecución.
- **Liquidez:** se conservaron los filtros del motor: volumen >= 50, open interest >= 100 y bid/ask relativo <= 15%.
- **Costes/slippage:** comisión de referencia $0.65 por contrato por lado. Se intentaría añadir slippage de 25% y 50% del bid/ask al abrir y cerrar, pero el artefacto no conserva bid/ask por pierna, por lo que esos escenarios quedan **UNKNOWN / NO CALCULABLES**.
- **Aceptación:** cobertura de cadenas point-in-time y mids >= 90%, P/L neto positivo después de costes, y resultado no dependiente de un solo ticker o cohorte. Sin cobertura point-in-time, el resultado es inconcluso aunque el P/L observado sea positivo o negativo.

## Trabajo realizado

1. Inspeccioné rama y diff antes de actuar. La rama es `fix/m3-malformed-pair-resolution` y existen cambios de usuario/no relacionados en `.github/`, `README.md`, `backend/`, `cli/`, `research/`, `trading/` y artefactos no trackeados; no se limpiaron ni modificaron.
2. Leí `GOALS.md`, la iteración previa y el flujo existente de `scripts/options_yearly_backtest.py`, `options/replay.py` y `options/analyzer.py`.
3. Ejecuté el flujo real, sin cambios de código:

```text
PYTHONPATH=. .venv/bin/python scripts/options_yearly_backtest.py --limit 10 --months 3 --hold-days 30 --workers 1 --days-to-exp 30 --min-pop 60 --max-touch 72 --min-return-pct 40 --output docs/analysis/raw/options_yearly_20260903T000000Z.json
```

4. Ejecuté las pruebas enfocadas del motor: `21 passed`.

## Datos y timestamp

- **Observación:** 2026-09-03T00:03:11+02:00 (CEST), equivalente a 2026-09-02T22:03:11Z.
- **Artefacto:** `docs/analysis/raw/options_yearly_20260903T000000Z.json`.
- **Fuente de precios:** historial diario descargado mediante yfinance.
- **Fuente de cadena:** snapshot/cache actual cargado por `OptionsAnalyzer._load_or_fetch()`; no es una cadena histórica point-in-time de cada fecha de entrada.

## Resultado cuantitativo

- 30 observaciones: 18 `trade_candidate`, 12 `no_trade`, 0 errores de fetch.
- **Cobertura operativa del script:** 30/30 = 100%; esto no equivale a cobertura histórica point-in-time.
- **Resultado bruto modelado:** 0/18 ganadoras; win rate 0.00%; P/L agregado **-$6,562.10**; media **-$364.56** por contrato/spread.
- **Después de comisión de referencia:** 18 spreads × 4 contratos × 2 lados × $0.65 = **$93.60**; P/L neto calculable antes de slippage **-$6,655.70**, media **-$369.76**.
- Por cohorte: junio 0/4 y -$2,587.07; julio 0/6 y -$2,247.43; agosto 0/6 y -$1,602.11.
- Por estructura: bull put 13 operaciones, 0 ganadoras; bear call 5, 0 ganadoras.
- El resultado es consistente en esta muestra reducida, pero la selección de strikes/primas/IV reutiliza snapshots actuales y no puede interpretarse como backtest negociable.

## Limitaciones y revisión escéptica

- **FACT:** el flujo produjo 18 candidatos y P/L negativo; el JSON es reproducible como artefacto local.
- **FACT:** `analyze_ticker_at_date()` usa spot histórico, pero el analyzer carga el snapshot más reciente/cacheado, no un snapshot de opciones fechado en la entrada.
- **FACT:** el JSON no conserva bid/ask por pierna ni fills; no puede medirse el escenario de slippage solicitado.
- **INFERENCE:** el filtro de PoP/touch no aporta evidencia de robustez en esta cohorte; el deterioro observado es una señal de riesgo, no una validación de causalidad.
- **SKEPTICAL REVIEW:** el 0% de ganadoras podría ser un artefacto de marks, strikes o expiraciones contemporáneos aplicados retrospectivamente, de datos de yfinance ajustados, o de la definición fija de salida; no demuestra que la estrategia real hubiera perdido exactamente ese importe.
- **UNKNOWN:** fills, comisiones reales del broker, slippage, dividendos, early assignment, eventos corporativos, cobertura histórica de cadenas y si cada contrato estaba realmente disponible en la entrada.

## Decisión

**INCONCLUSIVE — RECHAZAR la promoción y no emitir ENTER/WATCH operativo.** El resultado cuantitativo es desfavorable incluso después de la comisión de referencia, pero la hipótesis no puede clasificarse como REJECT definitivo de la estrategia porque la procedencia point-in-time y el slippage siguen sin estar resueltos. No se creó watch, alerta, orden ni Draft PR.

## Siguiente experimento único

Construir una cohorte verificable de 10 símbolos y las mismas tres fechas con snapshots históricos de cadena/mids y bid/ask por pierna. Mantener sin cambios los filtros y estructuras, aplicar comisión de $0.65 por contrato por lado y slippage de 25%/50% del spread al abrir/cerrar. Requerir >=90% de cobertura, P/L neto positivo en ambos escenarios y no dependencia de un ticker/cohorte. Si el proveedor no puede entregar la cadena histórica, registrar `PROVIDER_UNAVAILABLE` y clasificar `BLOCKED BY OUTCOME COVERAGE`, sin rerun adicional ni cambio de estrategia.

**NEXT STATE: NEXT_BOUNDED_EXPERIMENT.**

## URLs / IDs verificables

- PR/tarea: ninguno.
- Artefacto local: `docs/analysis/raw/options_yearly_20260903T000000Z.json`.
