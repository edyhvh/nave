# Iteracion 94

> **Analisis dirigido:** `2024-2025-bull` ETH para distinguir entre defecto de entrada y defecto de salida
> **Cambio retenido:** persistir `best_move_pct` y `worst_move_pct` por trade en los artefactos del backtest
> **Hipotesis rechazada:** mover el stop a break-even despues de `tp1`

## Hallazgo

- La hipotesis de retest tardio quedo descartada antes de tocar ejecucion: en el slice debil de ETH, ganadores y perdedores estaban confirmando en el mismo piso de `6h`.
- El problema restante parecia mas cercano a ejecucion, asi que esta iteracion agrego excursion favorable y excursion adversa por trade para ver si los perdedores estaban regalando ganancias ya ganadas.
- En `2024-2025-bull` ETH, los tres perdedores mostraron `best_move_pct` de `3.54%`, `1.72%` y `4.85%`.
- Eso significa que dos perdedores nunca mostraron recorrido suficiente para una proteccion razonable, y el tercero quedo cerca pero sin tocar el `tp1` vigente.

## Cambio retenido

- `BacktestTrade` ahora persiste `best_move_pct` y `worst_move_pct`.
- `workflow._with_trade_diagnostics()` agrega valores por defecto para artefactos viejos, igual que con `score_breakdown` y `diagnostics`.
- Este cambio mejora la precision del workflow porque ahora separa con claridad:
  - trades que nunca tuvieron follow-through real
  - trades que si lo tuvieron pero lo devolvieron por la logica de salida

## Hipotesis probada y revertida

- Se probo una salida minima usando la infraestructura ya existente de `tp1/tp2/tp3`: armar break-even despues de tocar `tp1`.
- La prueba fue conservadora: el break-even solo se activaba desde la barra siguiente para no introducir sesgo optimista intrabar.
- El resultado en `2024-2025-bull` ETH fue nulo:
  - win rate: `0.625 -> 0.625`
  - expectancy: `1.5825 -> 1.5825`
- Con esa evidencia, el cambio se revirtio.

## Lectura

- El slice debil restante no parece resolverse con un ajuste simple de salida.
- La nueva evidencia apunta a que el siguiente refinamiento deberia buscar mejor calibracion de targets o mejor separacion de entradas extendidas, no solo proteger beneficios con una regla mecanica despues de `tp1`.
- La mejora retenida de esta iteracion es observabilidad, no win rate.

## Validacion

- `PYTHONPATH=. pytest tests/test_momentum_engine.py tests/test_momentum_workflow.py tests/test_momentum_scripts.py -q` -> `21 passed`