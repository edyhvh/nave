# Iteracion 96

> **Analisis dirigido:** `2023-recovery` ETH despues del filtro swing de volumen
> **Cambio aplicado:** exigir `atr_ratio >= 1.0` cuando el setup proyecta horizonte no intraday (`expected_move_pct >= 0.10`)

## Hallazgo

- Tras `iter_95`, el foco reciente se movio a `2023-recovery` ETH y `2024-ETF-approval`.
- El slice debil de `2023-recovery` ETH tenia tres perdedores, pero solo uno seguia perteneciendo al bucket swing (`1-3 days`).
- Ese trade perdedor era muy especifico:
  - `2022-11-22T09:00:00+00:00`
  - `side=short`
  - `expected_move_pct=0.1179`
  - `atr_ratio=0.959`
  - `breakout_volume_ratio=2.819`
  - `r=-1.0`
- En los artefactos recientes de ETH (`2023-recovery`, `2024-ETF-approval`, `2024-2025-bull`), el bucket swing con `atr_ratio < 1.0` quedo asi:
  - `1 trade / 0.00% win rate / -1.0R`
- El bucket swing con `atr_ratio >= 1.0` quedo asi:
  - `5 trades / 80.00% win rate / +2.4194R`

## Cambio

- Se agrego `volatility.min_atr_ratio_swing = 1.0` al config.
- `engine._is_tradeable()` ahora exige ese piso de ATR solo cuando el setup proyecta un horizonte no intraday (`expected_move_pct >= 0.10`).
- El filtro base de volatilidad no cambia para setups intraday.

## Control cercano

- Se reviso el mismo bucket sobre BTC en los artefactos recientes.
- Resultado:
  - `btc_swing_low_atr`: `0 trades`
  - `btc_swing_high_atr`: `2 trades / 50.00% win rate / +1.0065R`
- En otras palabras, el nuevo corte no borra un bucket bueno de BTC en los periodos recientes usados como control.

## Lectura

- El filtro de swing por volumen de `iter_95` mejoro la calidad de setups multi-dia, pero aun quedaba un outlier de swing con ATR 4H insuficiente.
- Esta iteracion refuerza la misma idea desde otra dimension: un setup multi-dia necesita no solo volumen suficiente, sino tambien expansion de ATR real por encima de `1.0`.
- La combinacion volumen+ATR para swings sigue siendo local y acotada: no toca los setups intraday.

## Validacion

- `PYTHONPATH=. pytest tests/test_momentum_engine.py tests/test_momentum_workflow.py tests/test_momentum_scripts.py -q` -> `23 passed`# Iteracion 96

> **Backtest command:** `python scripts/momentum_backtest.py --period 2023-recovery --symbols BTC ETH --trigger-timeframe 1H`
> **Artifact:** `docs/analysis/raw/momentum_backtest_2023-recovery_20260429T071433Z.json`

## Resumen

- Periodo: `2023-recovery`
- Ventana solicitada: `2023-01-01T00:00:00+00:00` -> `2023-12-31T00:00:00+00:00`
- Ventana efectiva: `2022-11-02T00:00:00+00:00` -> `2023-12-31T00:00:00+00:00`
- Cobertura completa: `True`
- Trades totales: `16`
- Win rate pool: `0.8125`
- Expectancy pool: `2.0697`

## Observaciones

### BTC

- Cobertura: `2022-11-02T00:00:00+00:00` -> `2023-12-31T00:00:00+00:00` (completa=`True`)
- Trades: `7`
- Win rate: `1.0`
- Expectancy: `2.9883`
- Nota: No obvious structural defect from aggregate stats; inspect individual losing trades before changing thresholds.

### ETH

- Cobertura: `2022-11-02T00:00:00+00:00` -> `2023-12-31T00:00:00+00:00` (completa=`True`)
- Trades: `9`
- Win rate: `0.6667`
- Expectancy: `1.3552`
- Nota: Too few trades are reaching 8%; inspect whether entries are late and whether retest tolerance is too loose.
