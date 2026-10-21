# Arquitectura

## Vista general

```text
Binance Futures / Binance Vision / Bybit / Kraken / OKX / RSS
                         |
                         v
              collector/collector.py
        (dedup, fallback, retencion, health)
                         |
                         v
        collector/data/btcusdt/*.jsonl + health.json
                         |
                         v
              analysis/decision_engine.py
     (zonas, HTF, POC, sweep, aguante, escenarios)
                         |
                         v
              analysis/run_decision.py
       (decisions.jsonl, latest_decision.json, health.json)
                         |
              +----------+----------+
              |                     |
              v                     v
     analysis/evaluate_decisions.py  dashboard/index.html
       (Brier, skill, calibracion)   (solo lectura, GitHub raw)
              |
              v
       analysis/data/eval.json
```

## Componentes

### Colector

- Solo endpoints publicos y RSS. Sin claves ni ordenes.
- Velas 5m/1h/4h/1D con dedup por `openTime`.
- Derivados: funding, open interest, long/short global, top traders y taker.
- Fallback de velas: Binance Futures -> Binance Vision -> Bybit -> Kraken.
- Fallback de derivados: Binance Futures -> OKX para funding, OI, global LS y taker.
- `collector/data/health.json` resume fuentes, filas nuevas, errores y ultima clave.
- Retencion: 200.000 lineas de 5m y 5.000 noticias.

### Motor de decision

- Zonas de pivotes 5m agrupadas; ancho `max(0,30% precio, 0,30 * ATR4h)`.
- Sesgo nativo 1h/4h/1D; si 4h y 1D chocan, `LATERAL`.
- Pivotes HTF como confluencia, nunca como toques.
- POC y value area de 24h como contexto.
- Aguante solo con 3+ toques reales en 6h.
- Sweep y ruptura confirmada por 2+ cierres fuera.
- Escenarios base, alternativo y no hacer nada; trigger e invalidacion.
- Calidad de zona 0-10 y calidad compuesta con objetivo 8,5.
- Guardrail: si la ultima vela cerrada tiene >20 min, `datos_desactualizados` y trigger bloqueado.
- No hay llamadas a exchanges ni claves en este modulo.

### Evaluacion

- `evaluate_decisions.py` mide aguante a 4h: cierre 0,5% mas alla del nivel.
- Reporta Brier, tasa base, Brier skill, calibracion por tramos, intervalos de Wilson y corte por lado.
- `backtest.py` reconstruye el contexto historico sin mirar el futuro y etiqueta solo con las velas siguientes.
- Menos de 30 muestras = muestra chica; no se cambia el modelo por un corte.

### Dashboard

- Solo lectura, negro/blanco/gris con acentos neon.
- Mercado y derivados en vivo desde Binance en el navegador.
- Lee `latest_decision.json` y `eval.json` desde `raw.githubusercontent.com`.
- Se publica como `motor.html` en GitHub Pages sin reemplazar el dashboard actual.
- Diario manual en `localStorage`; no se envia a ningun servidor.
- No tiene botones de compra/venta ni ejecucion.

## Workflows

| Workflow | Frecuencia | Funcion |
|---|---|---|
| `BTC analysis pipeline` | cada 15 min | colecta, decide, evalua, chequea salud y commitea todo |
| `Collect BTC public data (manual)` | a pedido | reintento del colector |
| `BTC decision log (manual)` | a pedido | recalculo sin colector |
| `Analysis tests` | push de codigo | compile + tests |
| `Pipeline health (manual)` | a pedido | inspeccion de frescura |
| `OOS backtest (manual)` | a pedido | actualiza `analysis/data/backtest.json` |
| `Tests` | push a `main` | suite del Vigilante |
| `Vigilante BTC Cloud` | cada 5 min (cron externo) | alertas del bot; no opera |

GitHub puede limitar los schedules cuando hay muchos workflows. El pipeline principal es uno solo;
si hace falta puntualidad estricta, un cron externo puede disparar `pipeline.yml` por `workflow_dispatch`.

Los workflows que escriben comparten `concurrency: data-write` y hacen `pull --rebase` antes del push.

## Datos y schemas

- Klines: `source`, `interval`, `openTime`, `open`, `high`, `low`, `close`, `volume`, `closeTime`, `quoteVolume`, `trades`, `collected_at`.
- Funding: `source`, `symbol`, `fundingRate`, `fundingTime`, `markPrice`.
- Open interest: `source`, `symbol`, `sumOpenInterest`, `sumOpenInterestValue`, `timestamp`.
- Long/short: `source`, `symbol`, `timestamp`, `longShortRatio`, `longAccount`, `shortAccount`.
- Taker: `source`, `symbol`, `timestamp`, `buySellRatio`, `buyVol`, `sellVol`.
- Noticias: `source`, `title`, `link`, `pubDate`, `description`, `collected_at`.

## Seguridad y limites

- Sin claves privadas, sin API keys de trading, sin ejecucion de ordenes.
- Permisos de workflows limitados a `contents: write` solo donde se commitea.
- `Pipeline health` y tests usan `contents: read`.
- El riesgo principal es de datos (fuente/mezcla spot-futures/frescura), no de ejecucion.
