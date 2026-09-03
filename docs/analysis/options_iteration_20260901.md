STOCKS: Investigación de opciones — iteración acotada 2026-09-01

## Hipótesis

**HYPOTHESIS:** En un universo líquido de acciones S&P 500, los candidatos de spreads de crédito definidos por el modelo (bull put / bear call), filtrados por PoP >= 60% y probabilidad de toque < 72%, conservan expectativa positiva después de costes realistas durante un horizonte de 30 días.

- **Universo:** primeros 20 símbolos devueltos por `get_sp500_tickers(20)`; el artefacto identifica las observaciones efectivas.
- **Timeframe:** entrada mensual en 2026-06-01, 2026-07-01 y 2026-08-01; salida 30 días después (2026-07-01, 2026-07-31 y 2026-08-31).
- **Estructura:** únicamente candidatos definidos por el motor; en las operaciones observadas fueron bull put credit spreads y bear call credit spreads. No naked options.
- **Riesgo:** el P/L se expresa por 1 contrato con multiplicador 100; el riesgo máximo es el max loss del spread. No se aprobó tamaño de cuenta ni ejecución.
- **Liquidez:** filtros configurados del motor: volumen >= 50, open interest >= 100 y bid/ask relativo <= 15%.
- **Costes/slippage:** el replay no incorpora una comisión explícita adicional ni un escenario de slippage; los marks usan la cadena disponible y, por tanto, no satisfacen todavía el gate after-fee.
- **Aceptación:** win rate y P/L agregados positivos, con cadena histórica point-in-time verificable y cobertura de fills/mids suficiente. Rechazo: P/L negativo aun con datos point-in-time válidos. Si la cadena histórica no es point-in-time, el resultado es inconcluso.

## Trabajo realizado

1. Inspeccioné la rama y el diff existente. Hay cambios de usuario no relacionados en `.github/`, `README.md`, `cli/`, `trading/` y artefactos no trackeados; no se modificaron ni limpiaron.
2. Leí la implementación existente de `scripts/options_yearly_backtest.py`, `options/replay.py`, el fetcher de yfinance y la estrategia documentada de opciones.
3. Ejecuté el flujo real con:

```text
PYTHONPATH=. python3 scripts/options_yearly_backtest.py --limit 20 --months 3 --hold-days 30 --workers 1 --days-to-exp 30 --min-pop 60 --max-touch 72 --min-return-pct 40 --output docs/analysis/raw/options_yearly_20260901T190000Z.json
```

4. Ejecuté las pruebas enfocadas antes y después: `tests/test_options_replay.py`, `tests/test_options_strategies.py`, `tests/test_options_analytics.py` y `tests/test_options_probability.py`.

## Datos y timestamp

- **Artefacto:** `docs/analysis/raw/options_yearly_20260901T190000Z.json`
- **Generado por el proceso:** 2026-09-01T17:03:39.923479+00:00 (19:03:39 CEST).
- **Observación de ejecución:** 2026-09-01T17:04:49Z (19:04:49 CEST), timestamp de verificación posterior.
- **Datos subyacentes:** precios históricos descargados con yfinance para las fechas de entrada/salida; las cadenas de opciones se cargan mediante el snapshot/cache actual del fetcher y no mediante snapshots históricos por fecha.

## Resultado cuantitativo observado

- 60 filas: 26 `trade_candidate`, 32 `no_trade`, 2 `no_candidates`, 0 errores de fetch/reportados por el script.
- Todos los 26 candidatos pasaron el filtro high-odds configurado.
- **Win rate:** 7/26 = 26.92%.
- **P/L medio:** -$240.14 por 1 contrato.
- **P/L agregado:** -$6,243.70.
- Bull put: 17 operaciones, 5 ganadoras / 12 perdedoras.
- Bear call: 9 operaciones, 2 ganadoras / 7 perdedoras.
- Por cohorte: junio 4/9 y -$1,296.15; julio 1/9 y -$3,168.32; agosto 2/8 y -$1,779.23.
- Los tres ejemplos con retorno relativo alto fueron NVDA +$180.39, AMZN +$94.29 y META +$318.60, todos del 2026-06-01; no compensaron las pérdidas agregadas.

## Evidencia frente a interpretación

- **FACT:** El flujo produjo el resultado numérico anterior y guardó el JSON reproducible.
- **FACT:** Los tests enfocados terminaron `14 passed` y los tests replay/strategies terminaron `15 passed`.
- **FACT:** El resultado observado es negativo bajo la reconstrucción ejecutada.
- **INFERENCE:** El filtro PoP/touch, tal como se reconstruyó, no demuestra robustez; el resultado es una señal de deterioro importante, no una validación.
- **UNKNOWN / LIMITACIÓN CRÍTICA:** `analyze_ticker_at_date()` calcula el spot histórico, pero `OptionsAnalyzer._load_or_fetch()` obtiene una cadena actual/cacheada, no la cadena point-in-time de cada fecha histórica. Por ello, strikes, primas, IV, disponibilidad, selección y marks no representan necesariamente lo que se habría podido negociar en la fecha de entrada. No se puede atribuir el P/L a una estrategia histórica válida.
- **UNKNOWN:** no hay verificación de fills reales, comisiones por contrato, slippage de entrada/salida, dividendos, early assignment o riesgo de evento entre entrada y salida.
- **UNKNOWN:** no se verificó una cobertura independiente de los 20 símbolos contra un proveedor histórico de cadenas.

## Decisión

**INCONCLUSIVE — NO ENTER / NO WATCH operativo.** La hipótesis no se acepta. Tampoco se emite `REJECT` definitivo de la estrategia porque la ausencia de cadenas point-in-time contamina la medición; el P/L negativo se conserva como resultado exploratorio y como blocker de calidad de datos. No se creó alerta, watch ni orden.

## Siguiente experimento único

Construir una cohorte pequeña point-in-time de 10 símbolos y las mismas tres fechas usando snapshots históricos verificables (o declarar `PROVIDER_UNAVAILABLE` si no existen), manteniendo exactamente PoP >= 60%, touch < 72%, 30 DTE y spreads definidos. Añadir escenarios de coste: comisión de $0.65 por contrato por lado más slippage de 25% y 50% del bid/ask al abrir y cerrar. Aceptar solo si la cobertura de cadena/mids es >= 90%, el P/L neto es positivo, y el resultado no depende de un único ticker/cohorte; si no hay cobertura, clasificar `BLOCKED BY OUTCOME COVERAGE`.

**NEXT STATE: NEXT_BOUNDED_EXPERIMENT.** No se creó Draft PR ni se modificó código: en esta iteración no está justificado un cambio de implementación antes de resolver la procedencia point-in-time.

## URLs / IDs verificables

- URL/ID de PR o tarea: **ninguno**.
- Artefacto local verificable: `docs/analysis/raw/options_yearly_20260901T190000Z.json`.
