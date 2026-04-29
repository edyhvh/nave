# Iteracion 95

> **Analisis dirigido:** separar setups multi-dia de ETH con volumen de ruptura insuficiente
> **Cambio aplicado:** exigir `breakout_volume_ratio >= 2.0` cuando el setup proyecta horizonte no intraday (`expected_move_pct >= 0.10`)

## Hallazgo

- La iteracion anterior mostro que varios perdedores recientes no eran un problema simple de salida: ni el break-even despues de `tp1` ni un recorte trivial de targets tenian evidencia suficiente.
- Con los nuevos campos `best_move_pct` y `worst_move_pct`, el siguiente paso fue revisar la calidad del bucket de setups multi-dia en ETH usando los artefactos existentes.
- El corte fue limpio:
  - `non_intraday_low_volume` (`breakout_volume_ratio < 2.0`): `2 trades / 0.00% win rate / -0.6775R`
  - `non_intraday_high_volume` (`breakout_volume_ratio >= 2.0`): `6 trades / 66.67% win rate / +1.8495R`
- Los dos trades de bajo volumen provenian del slice mas debil, `2024-2025-bull`, y ambos eran perdedores.

## Cambio

- Se agrego `participation.min_volume_ratio_swing = 2.0` al config.
- `engine._is_tradeable()` ahora exige ese umbral solo cuando el setup proyecta un horizonte no intraday (`expected_move_pct >= 0.10`).
- El filtro base de participacion no cambia para setups intraday.

## Validacion focalizada

- `PYTHONPATH=. pytest tests/test_momentum_engine.py -q` -> `10 passed`
- Se agrego una prueba especifica para confirmar que un setup swing con `volume_ratio` debil deja de ser tradeable.

## Comparacion dirigida

### 2024-2025-bull / ETH

- Antes: `8 trades / 62.50% win rate / +1.5825R expectancy`
- Despues: `6 trades / 83.33% win rate / +2.3358R expectancy`

## Lectura

- Esta mejora no intenta subir el win rate con mas agresividad de salida; elimina un bucket concreto de setups swing que ya venia mostrando peor calidad.
- La evidencia actual sugiere que las rupturas multi-dia necesitan participacion mas fuerte que los setups intraday.
- El siguiente paso natural es comprobar el mismo corte sobre BTC y luego refrescar los artefactos de foco si el cambio se mantiene estable.