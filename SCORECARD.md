# Scorecard del repo

Esta es una **auditoria interna con rubrica**, no una certificacion externa. Mide calidad de ingenieria, medicion y operacion. No mide ganancia ni promete edge predictivo.

Objetivo: **8,5/10**. Resultado de esta iteracion: **8,7/10** (ponderado).

## Rubrica

| Dimension | Peso | Antes | Ahora | Evidencia |
|---|---:|---:|---:|---|
| Confiabilidad y cobertura de datos | 15% | 7,0 | 8,6 | fallback Binance Vision/Bybit/Kraken/OKX, `health.json`, retencion, tests de mapeo |
| Calidad del motor de decision | 15% | 8,0 | 8,9 | zonas, HTF 1h/4h/1D, POC, sweep, aguante, guardrail de frescura |
| Medicion y calibracion | 15% | 6,5 | 8,7 | Brier, Brier skill, Wilson, calibracion, corte por lado, backtest OOS |
| Tests y CI | 10% | 7,5 | 8,8 | 5 modelo + 18 motor + 7 pipeline + 4 dashboard + 6 workflows + 10 colector; compileall |
| Confiabilidad operativa | 10% | 6,5 | 8,6 | pipeline unico, concurrency, rebase, health al final del job, backtest manual, health JSON |
| Seguridad y guardrails | 10% | 8,0 | 9,2 | sin claves, sin ordenes, permisos minimos, bloqueo por datos vencidos |
| Dashboard y UX | 10% | 6,5 | 8,7 | `/motor.html` en Pages, lee decision/eval, frescura, niveles, trigger, invalidacion, Brier |
| Documentacion y runbook | 5% | 7,0 | 9,0 | README, arquitectura, runbook, scorecard, caveats |
| Reproducibilidad y code quality | 5% | 7,5 | 8,6 | stdlib, paths, tests sin red, model card, CI |
| Validacion del modelo | 5% | 7,0 | 7,5 | holdout 2026 AUC 0,665 / Brier 0,175; OOS 39 muestras sin edge demostrado |

## Calculo

```text
0.15*8.6 + 0.15*8.9 + 0.15*8.7 + 0.10*8.8 + 0.10*8.6
+ 0.10*9.2 + 0.10*8.7 + 0.05*9.0 + 0.05*8.6 + 0.05*7.5
= 8.715 -> 8.7/10
```

Antes de esta iteracion: **7,2/10** aproximado con la misma rubrica.

## Que se transformo

- Colector con fallback oficial multiple, health por job, retencion y tests.
- Motor con `data_status` y bloqueo de trigger si los datos tienen mas de 20 minutos.
- Evaluador con Brier skill, intervalos de Wilson, calibracion, cobertura y corte por lado.
- Backtest OOS que reconstruye el contexto sin mirar el futuro.
- Workflows con `concurrency`, rebase, health cada 2h y backtest semanal.
- Dashboard con decision, frescura, niveles, trigger, invalidacion y Brier.
- README, arquitectura, runbook y este scorecard.
- Restauracion del `.gitignore` original del Vigilante, que se habia sobrescrito por error.

## Por que el modelo no llega a 9

El backtest OOS del 21-10-2026 (39 muestras, 25 decisiones) da:

- Brier 0,1642.
- Tasa base 79,5%.
- Brier skill -0,0069.
- Tramo >=0,80: 24 muestras, 83,3% real.

La calibracion es razonable, pero **no hay evidencia de edge** frente a predecir la tasa base en esa muestra. La muestra es chica. Por eso Validacion del modelo queda en 7,5 y el repo no se autopuntua 9.

## Criterio para subir a 9,0

1. Backtest OOS con 100+ muestras y Brier skill positivo y estable.
2. Mejor cobertura de top traders (fallback o fuente alternativa).
3. Mantener `/motor.html` publicado y enlazado sin romper el dashboard actual.
4. Monitoreo de drift mensual y recalibracion documentada.
5. Revision externa de la rubrica.
