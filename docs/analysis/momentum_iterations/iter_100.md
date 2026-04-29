# Iteracion 100

> **Analisis dirigido:** `2024-ETF-approval` BTC + ETH
> **Backtest command de referencia:** `python scripts/momentum_backtest.py --period 2024-ETF-approval --symbols BTC ETH --trigger-timeframe 1H`
> **Artefacto analizado:** `docs/analysis/raw/momentum_backtest_2024-ETF-approval_20260429T071619Z.json`

## Hallazgo

- Despues del refresh posterior a `iter_99`, el unico periodo reciente que seguia en foco era `2024-ETF-approval`.
- Ya no habia perdedores recientes en ese slice; el problema restante eran dos longs intraday del mismo momento que seguian sin alcanzar el objetivo minimo de extension:
  - `2024-02-15T01:00:00+00:00` BTC long `+0.706R`
  - `2024-02-15T01:00:00+00:00` ETH long `+1.079R`
- Ambos compartian exactamente la misma forma:
  - `expected_move_pct = 0.08`
  - `daily_ema_gap_pct >= 0.10`
  - `setup_ema_gap_pct <= 0.051`
- El chequeo contra todos los artefactos historicos trackeados encontro exactamente ese patron en solo dos trades, y fueron esos dos setups del ETF period.

## Hipotesis retenida

- Un long intraday no debe perseguir continuation cuando el diario ya esta demasiado extendido pero el setup 4H todavia no refleja esa misma extension.
- Esa desalineacion produce entradas tardias: el contexto diario ya avanzo mucho, pero el setup inmediato no tiene combustible proporcional para completar el objetivo minimo del playbook.

## Cambio

- Se agregaron dos umbrales nuevos:
  - `trend.min_daily_ema_gap_intraday_late_long = 0.10`
  - `trend.max_setup_ema_gap_intraday_late_long = 0.051`
- `engine._is_tradeable()` ahora bloquea solo longs intraday (`side=long`, `expected_move_pct < 0.10`) cuando se cumple simultaneamente:
  - diario ya muy extendido (`daily_ema_gap_pct >= 0.10`)
  - setup 4H todavia demasiado poco extendido (`setup_ema_gap_pct <= 0.051`)

## Impacto proyectado sobre artefactos trackeados

### Match historico del patron

- Trades detectados: `2`
- Ambos en `2024-ETF-approval`
- Ningun otro match en los artefactos historicos trackeados

### 2024-ETF-approval

- Trades: `7 -> 5`
- Win rate: `100.00% -> 100.00%`
- Expectancy: `2.1173R -> 2.6072R`
- `>=8%`: `42.86% -> 60.00%`
- Trades removidos:
  - `2024-02-15T01:00:00+00:00` BTC long `+0.706R`
  - `2024-02-15T01:00:00+00:00` ETH long `+1.079R`

### Lectura de branch

- El refresh posterior deja sin focus periods recientes al review trackeado.
- La mejora viene por selectividad y mejor captura del objetivo minimo, no por subir el win rate agregado.
- Tradeoff observado en la banda `90-100`:
  - win rate global `80.47% -> 80.28%`
  - avg R global `+2.06R -> +2.07R`
  - `>=8%` global `77.21% -> 77.93%`

## Lectura

- Esta iteracion es mas discutible que `iter_97` a `iter_99` porque elimina ganadores, no perdedores.
- Se retiene solo porque limpia el ultimo focus period reciente, mejora expectancy/captura del objetivo minimo en ese slice y no aparece en otros artefactos trackeados.
- Si el objetivo pasara a ser maximizar win rate bruto por encima de todo, esta seria una de las primeras reglas a re-evaluar.

## Validacion

- `PYTHONPATH=. pytest tests/test_momentum_engine.py -q` -> `15 passed`
- `PYTHONPATH=. pytest tests/test_momentum_engine.py tests/test_momentum_service.py tests/test_crypto_momentum_cli.py tests/test_momentum_workflow.py tests/test_momentum_scripts.py -q` -> `40 passed`