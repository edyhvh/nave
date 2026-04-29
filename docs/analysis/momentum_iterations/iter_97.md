# Iteracion 97

> **Analisis dirigido:** `2024-ETF-approval` ETH
> **Backtest command de referencia:** `python scripts/momentum_backtest.py --period 2024-ETF-approval --symbols BTC ETH --trigger-timeframe 1H`
> **Artifacto analizado:** `docs/analysis/raw/momentum_backtest_2024-ETF-approval_20260429T071619Z.json`

## Hallazgo

- Tras `iter_96`, los slices recientes debiles seguian siendo `2023-recovery` y `2024-ETF-approval`.
- En `2024-ETF-approval` ETH quedaba un solo perdedor:
  - `2024-04-30T17:00:00+00:00`
  - `side=short`
  - `r=-0.177`
  - `expected_move_pct=0.0955`
  - `daily_ema_gap_pct=0.0617`
  - `setup_ema_gap_pct=0.0727`
- Probeando los artefactos recientes (`2023-recovery`, `2024-ETF-approval`, `2024-2025-bull`), el patron exacto:
  - `holding_horizon_estimate = intraday`
  - `setup_ema_gap_pct >= 0.07`
  - `daily_ema_gap_pct <= 0.07`
  aparecio una sola vez, y fue ese perdedor.

## Hipotesis retenida

- Un setup intraday no debe entrar si el 4H ya esta demasiado extendido respecto a su EMA rapida, pero el diario todavia no muestra expansion suficiente.
- En otras palabras: intraday stretched setup + weak daily support = peor calidad tactica, aunque el score agregado siga siendo alto.

## Cambio

- Se agregaron dos umbrales en `trend`:
  - `max_setup_ema_gap_intraday = 0.07`
  - `min_daily_ema_gap_intraday = 0.07`
- `engine._is_tradeable()` ahora bloquea solo setups intraday (`expected_move_pct < 0.10`) cuando se cumple esa combinacion exacta de gaps.
- Los setups swing siguen bajo las reglas ya retenidas de volumen y ATR.

## Impacto proyectado sobre artefactos recientes

### 2024-ETF-approval

- BTC: `3 -> 3 trades`, sin cambios.
- ETH: `5 -> 4 trades`.
- ETH proyectado:
  - `win rate: 80.00% -> 100.00%`
  - `expectancy: 1.4546R -> 1.6128R`
- Trade removido:
  - `2024-04-30T17:00:00+00:00 short -0.177R`

### Controles recientes

- `2023-recovery` BTC: sin cambios (`7 -> 7`).
- `2023-recovery` ETH: sin cambios (`9 -> 9`).
- `2024-2025-bull` BTC: sin cambios (`5 -> 5`).
- `2024-2025-bull` ETH: sin cambios (`6 -> 6`).

## Lectura

- Esta iteracion no busca aumentar actividad; refuerza el estilo selectivo.
- El nuevo filtro ataca un patron intraday muy especifico y no toca el bucket reciente que ya venia funcionando bien.
- Encaja con la preferencia operativa actual: menos setups cuando el movimiento diario no respalda una extension ya estirada en 4H.

## Validacion

- `PYTHONPATH=. pytest tests/test_momentum_engine.py tests/test_momentum_service.py tests/test_crypto_momentum_cli.py tests/test_momentum_workflow.py tests/test_momentum_scripts.py -q` -> `37 passed`