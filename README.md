# BTC Trading System

Sistema de **analisis y contexto** para BTC. No ejecuta ordenes, no usa claves privadas y no manda dinero a ningun exchange.

## Vigilante BTC

El bot de alertas sigue en `vigilante_cloud.py` (modelo de aguante v2, detector de toques y avisos). Sus pruebas estan en `test_vigilante.py`. El workflow `Vigilante BTC Cloud` corre cada 5 minutos y solo avisa; no opera.

El sistema de analisis de este README es independiente y no modifica la ejecucion del Vigilante.

## Componentes

- `collector/`: datos publicos de Binance Futures y noticias RSS, con fallback oficial (Binance Vision, Bybit, Kraken, OKX) y `health.json`.
- `analysis/`: modelo de aguante, motor de decision, registro, evaluacion, backtest OOS y chequeo de salud.
- `dashboard/`: dashboard HTML de solo lectura que consume `latest_decision.json` y `eval.json`.
- `.github/workflows/`: recoleccion horaria, decision horaria, tests, salud cada 2h y backtest semanal.

Documentacion: [arquitectura](ARCHITECTURE.md), [runbook](RUNBOOK.md) y [scorecard](SCORECARD.md).

## Que produce el motor

- Zonas de soporte/resistencia con ancho `max(0,30% del precio, 0,30 * ATR4h)`.
- Sesgo nativo 1h/4h/1D.
- Perfil de volumen: POC y value area.
- Estado de la zona: dentro/arriba/abajo, sweep reciente y ruptura confirmada por cierres.
- Aguante del nivel solo si hay 3+ toques reales en 6h.
- Escenario base, alternativo, trigger, invalidacion, riesgos y "no hacer nada".
- Calidad 0-10 por zona y calidad compuesta, con objetivo 8,5.
- **Guardrail de frescura:** con mas de 20 minutos sin vela cerrada, la accion pasa a `datos_desactualizados` y el trigger se bloquea.
- Registro en `analysis/data/decisions.jsonl`, `latest_decision.json`, `health.json` y evaluacion Brier/calibracion.

## Lo que NO es

- No es una senal de compra/venta.
- No es un win rate.
- No ejecuta ordenes.
- La probabilidad de aguante es condicional al nivel y a 4h; no promete ganancia.

## Uso local

```bash
python collector/collector.py
python analysis/run_decision.py --klines collector/data/btcusdt/klines_5m.jsonl --out analysis/data/decisions.jsonl
python analysis/evaluate_decisions.py --decisions analysis/data/decisions.jsonl --klines collector/data/btcusdt/klines_5m.jsonl --out analysis/data/eval.json
python analysis/check_health.py
python analysis/backtest.py --start 2026-10-01 --out analysis/data/backtest.json
```

Loop local cada hora:

```bash
python analysis/run_loop.py --minutes 60
```

Tests:

```bash
python collector/test_collector.py
cd analysis
python test_hold_model.py
python test_decision_engine.py
python test_pipeline.py
python test_dashboard.py
python test_workflows.py
```

## GitHub Actions

- `BTC hourly pipeline`: cada hora en el minuto 17. Colecta, decide, evalua, chequea salud y commitea `collector/data/` + `analysis/data/` en un solo job. Es el flujo principal.
- `Collect BTC public data (manual)` y `BTC decision log (manual)`: reintentos a pedido.
- `Analysis tests`: compile + tests de collector, motor, pipeline, backtest y dashboard.
- `Pipeline health (manual)`: inspeccion de frescura y colector a pedido.
- `OOS backtest (manual)`: reconstruye contexto sin futuro y actualiza `analysis/data/backtest.json`.

Los workflows de escritura comparten `concurrency: data-write` y hacen `pull --rebase` antes del push para evitar carreras. Solo usan endpoints publicos/RSS y permisos del propio repo. No hay secretos de trading.

GitHub puede demorar o limitar los `schedule` cuando hay muchos workflows programados. Por eso el flujo principal es uno solo. Si se necesita puntualidad estricta, configurar un cron externo (por ejemplo cron-job.org) que dispare `workflow_dispatch` de `pipeline.yml`; el repo ya expone ese trigger.

## Dashboard

`dashboard/index.html` se puede abrir local o publicar con GitHub Pages. Lee el mercado y derivados en vivo, y ademas `latest_decision.json`, `eval.json` y el estado de frescura del motor. Es solo lectura; el diario manual se guarda en `localStorage` del navegador.

El dashboard actual de Pages se conserva. La version nueva del motor se publica en `https://luiferx.github.io/vigilante-btc/motor.html` y se enlaza desde el dashboard con el boton `Motor 4h`.

## Limites honestos

- La probabilidad de aguante es condicional a 4h y no es win rate.
- El backtest OOS del 21-10-2026 (39 muestras) tiene Brier 0,164 y skill -0,007 frente a la tasa base: calibracion razonable, **edge predictivo no demostrado**. La muestra es chica.
- El repo busca 8,5/10 en calidad de ingenieria, medicion y operacion; no en prometer ganancias. Ver `SCORECARD.md`.
