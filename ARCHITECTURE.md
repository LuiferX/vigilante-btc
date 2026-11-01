# Arquitectura — máquina de análisis cuantitativo

**REARME 2026-11-01.** El repo ya no opera. Esta es la arquitectura de lo que
hace: medir, contrastar y publicar.

## Vista general

```text
Binance Futures (API pública) ──┐
Binance Vision (klines históricos)─�┤
OKX / Bybit / Kraken / RSS (fallback) ─┤
                                     ▼
                        ┌────────────────────────┐
                        │  collector/collector   │  adquisición viva (5 min)
                        │  analysis/backfill     │  histórico completo
                        │  analysis/archivo_micro│  microestructura DURABLE
                        └───────────┬────────────┘
                                    ▼
                  analysis/data/archivo/*.jsonl  (append-only, ordenado, dedup)
                                    ▼
                        ┌────────────────────────┐
                        │ analysis/percentiles   │  percentil CAUSAL (sin futuro)
                        │ vigilante/*            │  indicadores, niveles, régimen
                        │ analysis/expr_*        │  investigación con pre-registro
                        └───────────┬────────────┘
                                    ▼
                        ┌────────────────────────┐
                        │ analysis/informe.py    │  informe json + markdown
                        └───────────┬────────────┘
                                    ▼
                     main + GitHub Pages (público)
```

## Piezas

| Pieza | Qué hace | No hace |
|---|---|---|
| `collector/collector.py` | baja klines/micro/noticias cada 5 min y las guarda con dedup | no decide nada |
| `analysis/archivo_micro.py` | archivo **durable** de OI/taker/ballenas/funding (la API solo da 30 días: sin esto, se pierde la historia para siempre) | no recorta, no borra |
| `analysis/percentiles.py` | percentil causal por serie y ventana: "percentil 91 de 1.666 días" | no predice |
| `vigilante/indicadores.py` | matemáticas puras: EMA, RSI, ADX, ATR, estructura, swings | no envía nada |
| `vigilante/analisis.py` | velas → régimen, niveles, sesgo, sesión | no propone entradas |
| `analysis/expr_*.py` | investigación con hipótesis pre-registrada y criterio de muerte | no toca producción |
| `analysis/informe.py` | junta lo medido y escribe el informe | no opera |

## Reglas que la arquitectura garantiza

1. **Cero look-ahead.** Los percentiles y los experimentos solo miran el pasado;
   hay tests que lo verifican con un futuro que no debe cambiar el pasado.
2. **Costes siempre.** Toda expectativa se publica neta de fee + slippage
   (+ funding cuando el hold lo merece).
3. **Independencia.** Un trade simulado a la vez, con cooldown explícito; se
   publica `n_independientes`.
4. **Negativo se publica.** Seis hipótesis medidas, seis refutadas, todas en
   `analysis/EXPERIMENTOS.md`. Ni una borrada.
5. **Degradación honesta.** Con <30 observaciones los percentiles devuelven
   `None`, no un número inventado.
6. **El informe no habla de operar.** Hay un test que falla si el informe
   contiene "objetivo de precio", "stop loss", "take profit", "plan 2R"…

## Workflows (`.github/workflows/`)

| Workflow | Ritmo | Qué hace |
|---|---|---|
| `archivo.yml` | diario | baja el corte de microestructura y lo commitea |
| `informe.yml` | diario | recalcula percentiles y publica el informe |
| `collect.yml` | manual | recolección puntual del colector |
| `test.yml`, `analysis-tests.yml`, `lint.yml` | por push | verde obligatorio |
| `vigilia.yml` | 15 min | latido + alerta si un crítico falla dos veces |
| `resumen.yml` | semanal | resumen público |

## Dónde vive cada cosa

```
analysis/data/archivo/    microestructura durable (versionada, irrecuperable si se pierde)
analysis/data/cache/      klines para replay (regenerable, NO versionado)
analysis/data/informe.*   última publicación del informe
analysis/EXPERIMENTOS.md  el cuaderno: pre-registro y resultados reales
docs/audit/               informes de cada investigación
tests_operacion_archivados/  la capa de operar retirada (consulta histórica)
```

## Qué se retiró y por qué

El sistema tenía una capa completa de operación (paper trading, planes 2R,
alertas de entrada, comandos por chat, motor de decisión). La investigación
midió que su expectativa era **−0,10 a −0,25 % por operación** neta de coste, y
el papel vivo lo confirmó por un camino independiente. Se retiró entera, con
historial intacto en `tests_operacion_archivados/`. Lo que queda mide.
