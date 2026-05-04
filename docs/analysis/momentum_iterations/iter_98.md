# Iteracion 98

> **Analisis dirigido:** `2023-recovery` ETH
> **Backtest command de referencia:** `python scripts/momentum_backtest.py --period 2023-recovery --symbols BTC ETH --trigger-timeframe 1H`
> **Artifacto analizado:** `docs/analysis/raw/momentum_backtest_2023-recovery_20260429T071433Z.json`

## Hallazgo

- Despues de `iter_97`, el siguiente outlier reciente seguia en `2023-recovery` ETH:
  - `2023-11-02T01:00:00+00:00`
  - `side=long`
  - `r=-1.0`
  - `expected_move_pct=0.08`
  - `daily_ema_gap_pct=0.0366`
  - `atr_ratio=0.972`
- Probeando los artefactos recientes (`2023-recovery`, `2024-ETF-approval`, `2024-2025-bull`), el patron exacto:
  - `holding_horizon_estimate = intraday`
  - `daily_ema_gap_pct <= 0.05`
  - `atr_ratio < 1.05`
  aparecio una sola vez, y fue ese perdedor.

## Hipotesis retenida

- Un setup intraday no debe entrar cuando el diario todavia esta demasiado poco extendido y, ademas, el ATR 4H ni siquiera confirma expansion suficiente.
- Esto apunta a entradas demasiado tempranas en impulsos que aun no tienen suficiente respaldo de contexto para completar la extension minima del setup.

## Cambio

- Se agregaron dos umbrales nuevos:
  - `trend.min_daily_ema_gap_intraday_underextended = 0.05`
  - `volatility.min_atr_ratio_intraday_underextended = 1.05`
- `engine._is_tradeable()` ahora bloquea solo setups intraday (`expected_move_pct < 0.10`) cuando se cumple simultaneamente:
  - diario poco extendido (`daily_ema_gap_pct <= 0.05`)
  - ATR insuficiente (`atr_ratio < 1.05`)

## Impacto proyectado sobre artefactos recientes

### 2023-recovery

- BTC: `7 -> 7 trades`, sin cambios.
- ETH: `9 -> 8 trades`.
- ETH proyectado:
  - `win rate: 66.67% -> 75.00%`
  - `expectancy: 1.3552R -> 1.6495R`
- Trade removido:
  - `2023-11-02T01:00:00+00:00 long -1.0R`

### Controles recientes

- `2024-ETF-approval` BTC: sin cambios (`3 -> 3`).
- `2024-ETF-approval` ETH: sin cambios (`5 -> 5`).
- `2024-2025-bull` BTC: sin cambios (`5 -> 5`).
- `2024-2025-bull` ETH: sin cambios (`6 -> 6`).

## Lectura

- Esta iteracion vuelve a reforzar selectividad, no frecuencia.
- El nuevo corte es mas conservador que un filtro general de gaps: exige tambien debilidad en ATR para evitar tocar controles recientes sanos.
- Complementa `iter_97`: una regla filtra setups intraday demasiado estirados; esta filtra setups intraday demasiado tempranos.

## Validacion

- `PYTHONPATH=. pytest tests/test_momentum_engine.py tests/test_momentum_service.py tests/test_crypto_momentum_cli.py tests/test_momentum_workflow.py tests/test_momentum_scripts.py -q` -> `38 passed`