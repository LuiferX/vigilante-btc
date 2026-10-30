# BTC Trading System

Sistema de **analisis y contexto** para BTC. No ejecuta ordenes, no usa claves privadas y no manda dinero a ningun exchange.

## Vigilante BTC

El bot de alertas sigue en `vigilante_cloud.py` (modelo de aguante v2, detector de toques y avisos). Sus pruebas estan en `test_vigilante.py`. El workflow `Vigilante BTC Cloud` corre cada 5 minutos y solo avisa; no opera.

Desde el 22/10/2026, las **alertas direccionales** consultan `analysis/data/validation.json`. Solo se permiten si el estado es `ok`, hay al menos 100 muestras efectivas, el Brier skill es positivo, la calibracion ECE <= 0,08 y no hay drift en alerta. Si no se cumple, la alerta se silencia y se avisa una vez al dia; los avisos de contexto siguen saliendo sin plan de entrada. **Desde el 30/10/2026 el canal OOS tampoco abre si el canal vivo contradice** (skill<=0 o ECE>0,08 o drift en alerta, con >=30 muestras vivas): el puente OOS se cayó. Con el `validation.json` del 30/10 (vivo -0,009, n=84) el gate del bot queda **CERRADO** aunque el fichero siga reportando el canal OOS. El umbral de movimiento brusco subio a 1,5% en 1h y el de ritmo a 1,5% en 30 min.

La medicion del bot ahora usa la **direccion real del plan** (`ALZA: stop...` o `BAJA: stop...`), no el sesgo general. Una alerta de VENTA con sesgo ALZA se evalua como BAJA, y un aviso de contexto sin plan no entra al scoreboard. El historico anterior a este cambio puede estar sesgado; el scoreboard semanal, `/precision` y la calibracion del dashboard solo muestran muestras nuevas (`metodo=plan`). Las alertas que el gate silencia se evaluan aparte en `eval_gate` como contrafactual: no se enviaron, pero sirven para auditar si el filtro protege o bloquea señales buenas.

El bot de Telegram tambien lee `analysis/data/latest_decision.json` como **contexto**, no como orden: los reportes muestran una linea del motor 4h y el comando `/motor` resume accion, trigger e invalidacion. El motor nuevo no ejecuta ni cambia la logica de alertas.

## Componentes

- `collector/`: datos publicos de Binance Futures y noticias RSS, con fallback oficial (Binance Vision, Bybit, Kraken, OKX) y `health.json`.
- `analysis/`: modelo de aguante, motor de decision, registro, evaluacion, backtest OOS, validation bot y chequeo de salud.
- `dashboard/`: dashboard HTML de solo lectura que consume `latest_decision.json`, `eval.json` y `validation.json`.
- `.github/workflows/`: pipeline unico cada 15 min, self-heal desde el Vigilante, tests, salud al final del pipeline, validation bot y backtest manual.

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
python analysis/validation.py --eval analysis/data/eval.json --backtest analysis/data/backtest.json --decisions analysis/data/decisions.jsonl --klines collector/data/btcusdt/klines_5m.jsonl --collector-health collector/data/health.json --out analysis/data/validation.json --history analysis/data/validation_history.jsonl
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
python test_validation.py
python test_dashboard.py
python test_workflows.py
```

## GitHub Actions

- `BTC analysis pipeline`: cada 15 minutos. Colecta, decide, evalua, valida, chequea salud y commitea `collector/data/` + `analysis/data/` en un solo job. Es el flujo principal.
- `Analysis self-heal`: se dispara al terminar `Vigilante BTC Cloud`; si `latest_decision` tiene 15 min o mas, corre colector + decision + validacion.
- `Collect BTC public data (manual)` y `BTC decision log (manual)`: reintentos a pedido.
- `BTC validation bot (manual)`: recalcula `validation.json` sobre los datos ya commiteados.
- `Analysis tests`: compile + tests de collector, motor, pipeline, validation bot, backtest y dashboard.
- `Pipeline health (manual)`: inspeccion de frescura y colector a pedido.
- `OOS backtest (manual)`: reconstruye contexto sin futuro y actualiza `analysis/data/backtest.json` + `validation.json`.

Los workflows de escritura comparten `concurrency: data-write` y hacen `pull --rebase` antes del push para evitar carreras. Solo usan endpoints publicos/RSS y permisos del propio repo. No hay secretos de trading.

GitHub puede demorar o limitar los `schedule` cuando hay muchos workflows programados. Por eso el flujo principal es uno solo. Si se necesita puntualidad estricta, configurar un cron externo (por ejemplo cron-job.org) que dispare `workflow_dispatch` de `pipeline.yml`; el repo ya expone ese trigger.

## Dashboard

`dashboard/index.html` se puede abrir local o publicar con GitHub Pages. Lee el mercado y derivados en vivo, y ademas `latest_decision.json`, `eval.json`, `validation.json` y el estado de frescura del motor. Es solo lectura; el diario manual se guarda en `localStorage` del navegador.

El dashboard actual de Pages se conserva. La version nueva del motor se publica en `https://luiferx.github.io/vigilante-btc/motor.html` y se enlaza desde el dashboard con el boton `Motor 4h`.

## Limites honestos

- La probabilidad de aguante es condicional a 4h y no es win rate.
- El backtest OOS del 21-10-2026 (39 muestras) tiene Brier 0,164 y skill -0,007 frente a la tasa base: calibracion razonable, **edge predictivo no demostrado**. La muestra es chica.
- El repo busca 8,5/10 en calidad de ingenieria, medicion y operacion; no en prometer ganancias. Ver `SCORECARD.md`.
