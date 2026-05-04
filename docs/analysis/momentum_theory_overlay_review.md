# Momentum Theory Overlay Review

Fecha: 2026-04-30

## Objetivo

Integrar partes utiles de la teoria NAVE dentro de la estrategia de momentum sin convertirla en otro modelo distinto. La regla de diseño fue simple: la teoria no reemplaza el score de momentum; solo puede vetar setups cuando detecta una contradiccion estructural que sea coherente con un sistema de breakout.

## Implementacion adoptada

- Se agrego un overlay teorico configurable en `trading/crypto/momentum/theory_overlay.py`.
- El overlay se conecta en `trading/crypto/momentum/engine.py` como veto de tradeabilidad, conservando intacto el pipeline principal de score.
- La configuracion vive en `trading/crypto/momentum/config.py` y `trading/crypto/momentum/defaults.json`.

## Reglas que se probaron y conclusion

### Reglas descartadas como veto por defecto

- **Weekly neutral como bloqueo**: demasiado agresivo para momentum. Cuando la lectura semanal quedaba neutral, el overlay bloqueaba demasiados ganadores. Se cambio para que en ese caso delegue la decision al modelo de momentum.
- **Climax cooldown diario**: funciona mejor en una logica de agotamiento o reversal. En un sistema de breakout estaba bloqueando demasiadas operaciones ganadoras. Se desactivo por defecto.

### Regla que si aporta valor en esta integracion

- **Chase gate en swings**: se mantiene solo para setups con expected move de tipo swing. Su objetivo es rechazar entradas demasiado superficiales dentro de una extension ya madura.
- Tambien se corrigio un caso importante: cuando el retrace calculado sale negativo por overshoot del extremo previo, eso ya no se interpreta como chase invalido. En breakout-continuation ese comportamiento no debe penalizarse automaticamente.

## Validacion usada

En vez de re-ejecutar todo el backtest completo en cada iteracion, se hizo un replay ligero sobre los artifacts ya generados por momentum. El procedimiento fue:

1. Tomar cada trade historico ya aceptado por la estrategia de momentum.
2. Re-evaluar solo el overlay teorico en el timestamp de entrada.
3. Medir cuantos ganadores y perdedores habria bloqueado el overlay.

Este metodo fue suficiente para iterar rapido sobre la logica del veto y evitar cambios ciegos.

Desde esta rama ya no depende de snippets manuales: el flujo quedo
codificado en `scripts/momentum_theory_overlay_review.py`, con helpers en
`trading/crypto/momentum/theory_overlay_review.py`.

- Replay actual: `docs/analysis/raw/momentum_theory_overlay_replay_latest.json`
- Sweep actual: `docs/analysis/raw/momentum_theory_overlay_sweep_latest.json`
- Reporte markdown replay: `docs/analysis/momentum_theory_overlay_replay.md`
- Reporte markdown sweep: `docs/analysis/momentum_theory_overlay_sweep.md`

## Resultado del replay ampliado

- **Pooled**: 213 trades totales.
- **Win rate base**: 0.8028.
- **Primera version del overlay**: 0.8086 de win rate, con 4 trades bloqueados.

## Iteracion 2: tuning del chase gate

Despues de la primera integracion se hizo un barrido pequeno sobre el
`chase_min_retrace` y el `chase_min_expected_move_pct` usando el mismo
replay ligero sobre artifacts.

### Hipotesis

La siguiente mejora plausible no estaba en cambiar la profundidad minima
del retracement, sino en **activar el chase gate desde el piso natural de
la estrategia de momentum (`expected_move_pct >= 0.08`)** en lugar de
solo desde 0.10. Eso permite filtrar swings cortos y superficiales que ya
cumplen el minimo operativo del modelo.

### Resultado intermedio (chase tuning)

- `chase_min_retrace = 0.20`, `chase_min_expected_move_pct = 0.08`.
- Replay pooled: 207 conservados, **0.8164** WR, 2.1234 expectancy.
- 6 bloqueos (2 ganadores 2018, 4 perdedores 2022).

## Iteracion 3: bloqueo de swings sin tailwind semanal

### Hipotesis

Despues del tuning de chase, el siguiente cluster de errores no estaba en
profundidad de retrace sino en **swings tomados cuando la lectura semanal
del overlay queda en `weekly_neutral`**. CriptoPana es explicito sobre
ese punto: las posiciones multi-dia necesitan un tailwind semanal claro;
sin el, son ruido.

### Diagnostico cuantitativo

Sobre el pool conservado por el chase gate (207 trades), el segmento
`overlay_stage == "weekly_neutral"` se separa muy limpio por horizonte:

- **weekly_neutral × intraday** (`expected_move_pct < 0.10`): 34 trades,
  WR 0.8529, expectancy 2.028.
- **weekly_neutral × swing** (`expected_move_pct >= 0.10`): 23 trades,
  WR **0.5217**, expectancy **0.94**.

Los swings sin sesgo semanal claro son la cola perdedora real del overlay
actual. La regla theory-grounded es bloquearlos.

### Regla adoptada

- **Configuracion actual**:
  - `block_weekly_neutral_swing = true`
  - `weekly_neutral_swing_min_expected_move_pct = 0.10`
- Cuando el overlay determina `bias == "neutral"` (incluyendo el fallback
  de range breakout) y el setup tiene `expected_move_pct >= 0.10`, el
  overlay rechaza con `stage = "weekly_neutral_swing"`. Los setups
  intraday siguen pasando por la rama de deferral.

### Resultado sobre replay

- Pool conservado: **184 trades**.
- Win rate conservado: **0.8533** (vs 0.8164 con solo chase gate).
- Expectancy conservada: **2.2715** (vs 2.1234).
- Trades bloqueados: **29** (14 ganadores, 15 perdedores).
- Distribucion de bloqueos: `chase_gate=6`, `weekly_neutral_swing=23`.

### Donde mejora de verdad

- **2022-bear**: 0.875 → **0.9474** WR; expectancy 2.57 → 2.88.
- **2017-bull+2018-bear**: 0.8125 → 0.881 WR; expectancy 1.93 → 2.20.
- **2020-covid-crash**: 0.7647 → 0.8125 WR.
- **2019-recovery**: 0.8333 → 0.8485 WR.

### Costo

- 12 ganadores adicionales bloqueados sobre la version anterior. La
  mayoria son shorts en bear markets tempranos (2018, 2025) con sesgo
  semanal apenas por debajo del umbral de 1.2 ATR. Es selectividad, no
  una frontera perfecta. El expectancy por trade aun mejora.
- **2024-2025-bull**: bloquea 2 shorts ganadores (sesgo semanal -0.66 y
  -0.75); el WR del periodo se mantiene en 1.0 sobre los 7 que quedan.

## Iteracion 4: ceiling de extension semanal para longs intraday

### Hipotesis

Despues del bloqueo de swings sin tailwind semanal, el cluster perdedor
restante quedo dominado por **longs intraday tomados con la lectura
semanal ya muy estirada al alza**. CriptoPana es explicito: cuando el
weekly impulse esta exhausto, el siguiente movimiento natural es un
reset diario, no otra extension intraday.

### Diagnostico cuantitativo

Sobre el pool conservado por iter 3 (184 trades, 27 perdedores), la
asimetria long/short es marcada:

- Longs conservados: 104 trades, WR 0.817, expectancy 2.155, 19 perdedores.
- Shorts conservados: 80 trades, WR 0.900, expectancy 2.423, 8 perdedores.

Bucketeando longs por `aligned_weekly_velocity_atr` (ATR-normalizado en
direccion del trade):

- (0, 1]: 18 trades, WR **0.889**, expectancy 2.290.
- (1, 2]: 42 trades, WR 0.833, expectancy 2.214.
- (2, 3]: 28 trades, WR 0.786, expectancy 2.072.
- (3, 99]: 15 trades, WR 0.733, expectancy 1.938.

Decay monotonico: a mas velocity stretched al alza, peor performance.
Los shorts no muestran este patron en `(2, 3]` (WR 0.957 ahi); por eso
la regla es asimetrica.

Filtrando especificamente intraday longs con `aligned_velocity > 2.0`:
17 trades, WR 0.706, 5 perdedores. Ese es el cluster perdedor concreto.

### Regla adoptada

- **Configuracion actual**:
  - `block_long_intraday_extension = true`
  - `long_intraday_extension_max_expected_move_pct = 0.10`
  - `long_intraday_extension_max_weekly_velocity = 2.0`
- Cuando `side == "long"`, `expected_move_pct < 0.10` y la velocity
  semanal supera 2.0 ATR, el overlay rechaza con
  `stage = "long_intraday_extension"`. El bloqueo se evalua *antes* del
  `chase_gate`, por lo que ni el carve-out de overshoot ni el path de
  swing chase se afectan.
- Los shorts y los swings no se tocan; la regla solo afecta a longs
  intraday en estado de extension semanal.

### Resultado sobre replay

- Pool conservado: **167 trades** (vs 184 en iter 3).
- Win rate conservado: **0.8683** (vs 0.8533).
- Expectancy conservada: **2.3056** (vs 2.2715).
- Trades bloqueados: 46 (26 ganadores, 20 perdedores).
- Distribucion de bloqueos: `chase_gate=6`, `weekly_neutral_swing=23`,
  `long_intraday_extension=17`.

### Donde mejora de verdad

- **2020-recovery+2021-ATH**: 0.756 → **0.784** WR, expectancy 2.16 →
  2.24. Esta era la peor cola del pool y se reduce.
- **2017-bull+2018-bear**: 0.881 → **0.902** WR, expectancy 2.20 → 2.26.
- **2020-covid-crash**: 0.812 → 0.833 WR.

### Costo

- 12 ganadores adicionales bloqueados sobre iter 3. La mayoria se
  concentra en mercados muy alcistas donde el long intraday seguia
  funcionando aun con weekly extendido (ej: rallies parabolicos del
  bull market). Por eso el filtro reduce, pero no elimina, la cola
  ganadora del segmento.
- **2019-recovery**: 0.848 → 0.844 WR (1 ganador bloqueado, BTC
  2019-04-03 con velocity 2.64 que entro en chase_overshoot).
- **2023-recovery**: 0.923 → 0.909 WR (2 ganadores bloqueados, ambos
  intraday-long con velocity ~2.6-3.7).
- **2024-2025-bull**: 1.0 → 1.0 WR sobre 6 trades restantes (3 ganadores
  bloqueados pero los demas siguen perfectos).

## Lectura practica

- El overlay ya tiene tres capas teoricamente coherentes:
  1. **Weekly bias requerido**: swings sin tailwind semanal no entran.
  2. **Chase gate selectivo**: pullbacks demasiado superficiales sobre
     impulsos extendidos no entran (con carve-out para overshoots).
  3. **Long intraday ceiling**: longs intraday cuando la lectura semanal
     ya esta agotada no entran, esperando reset diario.
- Cada capa esta calibrada con datos separables y direccion teorica,
  no con barridos ciegos.
- El siguiente plano probable ya no es weekly velocity: es estructura
  diaria (e.g., distancia al fast EMA, secuencia de cierres por encima
  del rango previo). Para estimar bien ese plano se debe primero correr
  un backtest historico fresco con la nueva config, no solo replay.

## Estado recomendado

- Mantener este overlay como candidato valido en la rama experimental.
- Si se quiere validacion mas fuerte antes de merge, el siguiente paso
  correcto es re-correr el backtest historico completo con y sin overlay
  y comparar expectancy, drawdown y win rate por periodo sobre ejecucion
  fresca, no solo replay.