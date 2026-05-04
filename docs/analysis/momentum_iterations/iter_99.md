# Iteracion 99

> **Analisis dirigido:** `2024-2025-bull` BTC + ETH
> **Backtest command de referencia:** `python scripts/momentum_backtest.py --period 2024-2025-bull --symbols BTC ETH --trigger-timeframe 1H`
> **Artefacto analizado:** `docs/analysis/raw/momentum_backtest_2024-2025-bull_20260429T071529Z.json`

## Hallazgo

- Despues de `iter_98`, el siguiente outlier reciente quedo concentrado en un mismo momento del ciclo bull:
  - `2025-02-28T09:00:00+00:00` BTC `short` `r=-1.0`
  - `2025-02-28T09:00:00+00:00` ETH `short` `r=-1.0`
- Ambos seguian entrando con score muy alto (`98`) y expectativa swing (`expected_move_pct >= 0.15`), pero compartian una forma de extension tardia:
  - `daily_ema_gap_pct >= 0.10`
  - `range_expansion < 2.20`
- El chequeo barato contra todos los artefactos historicos trackeados encontro exactamente ese patron en solo dos trades, y ambos fueron perdedores.

## Hipotesis retenida

- Un short swing no debe activarse cuando el diario ya viene demasiado extendido a la baja pero la expansion efectiva del setup 4H todavia no acompana con suficiente fuerza.
- En esa combinacion, el sistema termina persiguiendo una continuation tardia que ya no tiene combustible proporcional al grado de extension del contexto.

## Cambio

- Se agregaron dos umbrales nuevos:
  - `trend.max_daily_ema_gap_swing_short = 0.10`
  - `volatility.min_range_expansion_swing_short = 2.20`
- `engine._is_tradeable()` ahora bloquea solo shorts swing (`side=short`, `expected_move_pct >= 0.10`) cuando se cumple simultaneamente:
  - diario ya muy extendido (`daily_ema_gap_pct >= 0.10`)
  - expansion 4H todavia insuficiente (`range_expansion < 2.20`)

## Impacto proyectado sobre artefactos trackeados

- Match historico del patron: `2 trades`.
- Ganadores afectados: `0`.
- Perdedores afectados: `2`.
- Trades detectados por el patron:
  - `2025-02-28T09:00:00+00:00` BTC short `-1.0R`
  - `2025-02-28T09:00:00+00:00` ETH short `-1.0R`

## Lectura

- Esta iteracion no baja el umbral general ni endurece los shorts de forma amplia.
- El corte solo aparece cuando la extension diaria ya es agresiva y el setup 4H no confirma una nueva expansion suficientemente fuerte.
- Encaja con la preferencia operativa del branch: menos trades forzados en zonas tardias, mas selectividad cuando el movimiento ya esta avanzado.

## Validacion

- `PYTHONPATH=. pytest tests/test_momentum_engine.py -q` -> `14 passed`
- `PYTHONPATH=. pytest tests/test_momentum_engine.py tests/test_momentum_service.py tests/test_crypto_momentum_cli.py tests/test_momentum_workflow.py tests/test_momentum_scripts.py -q` -> `39 passed`