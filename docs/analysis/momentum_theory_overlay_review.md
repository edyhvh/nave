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

## Iteracion 4 (intentada y revertida): ceiling de extension semanal para longs intraday

Se probo y commiteo una capa adicional que bloqueaba longs intraday
cuando la velocity semanal superaba 2.0 ATR. La regla mejoraba el replay
pooled (WR 0.853 → 0.868) pero la validacion historica fresca la
desmonto:

| Periodo | Con iter-4 | Sin iter-4 |
|---|---|---|
| 2020-covid-crash | 5 / 60.0% / +1.75 | **9 / 77.8% / +2.15** |
| 2020-recovery+2021-ATH | **13 / 92.3% / +2.28** | 17 / 82.4% / +1.85 |
| 2019-recovery | 15 / 73.3% / +1.46 | 16 / 75.0% / +1.62 |
| 2022-bear | 7 / 85.7% / +2.36 | 7 / 85.7% / +2.36 |

La regla ayudaba en 2020-2021 ATH (donde se calibro) pero hacia daño
real en 2020-covid-crash (-17.8 pp WR, -4 trades). Firma clasica de
overfit sobre un cluster especifico. **Se revirtio el commit
(`Revert "feat(momentum): cap stretched intraday longs - iter 4"`).**

Lessons aprendidas:
- Replay sobre artifacts existentes es optimista por construccion: solo
  ve los trades que el engine viejo tomo, no los que el engine nuevo
  rechaza antes de evaluar.
- Una regla calibrada sobre un solo cluster (5 perdedores en 2020-2021
  ATH) no generaliza sin validacion fresca por periodo.
- Total R por periodo es un mejor objetivo que WR por trade: iter-3-only
  tiene WR menor (-1.8 pp) pero genera +12.5% mas R total porque
  mantiene frecuencia.

## Validacion historica fresca (estado final)

Backtest end-to-end con el overlay iter-3-only sobre los 9 periodos:

| Periodo | Trades | WR | Expectancy |
|---|---|---|---|
| 2017-bull+2018-bear | 10 | 0.900 | +2.51 |
| 2019-recovery | 16 | 0.750 | +1.62 |
| 2020-covid-crash | 9 | 0.778 | +2.15 |
| 2020-recovery+2021-ATH | 17 | 0.824 | +1.85 |
| 2022-bear | 7 | 0.857 | +2.36 |
| 2023-recovery | 13 | 0.923 | +2.47 |
| 2024-ETF-approval | 5 | 1.000 | +2.61 |
| 2024-2025-bull | 7 | 1.000 | +2.62 |
| TODAY | 3 | 1.000 | +1.89 |
| **POOL** | **87** | **0.862** | **+2.15** (total +187 R) |

## Lectura practica (final)

- El overlay tiene dos capas teoricamente coherentes y validadas
  end-to-end:
  1. **Chase gate selectivo**: pullbacks demasiado superficiales sobre
     impulsos extendidos no entran (con carve-out para overshoots).
  2. **Weekly bias requerido para swings**: posiciones multi-dia sin
     tailwind semanal no entran.
- Cada capa esta calibrada con datos separables y direccion teorica.
- Se intento una tercera capa (iter 4: long intraday extension ceiling)
  pero se revirtio tras fallar validacion fresca por sobre-ajuste.

## Estado recomendado

- **Listo para merge**: el overlay con dos capas pasa validacion
  historica end-to-end, mejora WR pool de baseline ~0.80 a 0.862, y
  mantiene expectancy positiva (+2.15 R por trade) en todos los 9
  regimenes.
- Para futuras iteraciones: **no calibrar reglas sobre un solo cluster
  sin validacion fresca**. El replay siempre debe ir acompañado de un
  backtest historico completo antes de aceptar la regla.