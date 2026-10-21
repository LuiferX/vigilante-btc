# Runbook

## Chequeo diario (2 minutos)

1. Abrir Actions y confirmar que `BTC hourly pipeline` corrio en la ultima hora. Si GitHub demoro el schedule, lanzarlo con `Run workflow`.
2. Abrir `analysis/data/latest_decision.json`:
   - `data_status.fresh` debe ser `true`.
   - `decision.action` no debe ser `datos_desactualizados`.
   - `quality.composite` puede estar debajo de 8,5; el `gap` y los riesgos explican por que.
3. Abrir `collector/data/health.json`:
   - `ok` y `kline_ok` deben ser `true`.
   - Revisar `jobs` con `ok: false`; los top traders pueden quedar atrasados si Binance bloquea.
4. Abrir `analysis/data/eval.json`:
   - `samples` crece con el tiempo.
   - Menos de 30 muestras = no sacar conclusiones.
5. Abrir el dashboard y verificar que el boton `Motor 4h` lleva a `/motor.html` y muestra datos frescos.

## Comandos locales

```bash
python collector/collector.py
python analysis/run_decision.py --klines collector/data/btcusdt/klines_5m.jsonl --out analysis/data/decisions.jsonl
python analysis/evaluate_decisions.py --decisions analysis/data/decisions.jsonl --klines collector/data/btcusdt/klines_5m.jsonl --out analysis/data/eval.json
python analysis/check_health.py
python analysis/backtest.py --start 2026-10-01 --out analysis/data/backtest.json
```

Tests:

```bash
python collector/test_collector.py
cd analysis
python test_hold_model.py
python test_decision_engine.py
python test_pipeline.py
python test_dashboard.py
```

## Fallas comunes

### Binance responde 451/403 en GitHub Actions

Es geo-bloqueo del runner, no un bug del codigo.

- Velas: deben caer a Binance Vision, Bybit o Kraken. Revisar `source` en el ultimo registro.
- Funding/OI/global LS/taker: deben caer a OKX.
- Top traders: no tienen fallback; pueden quedar atrasados. Queda registrado en `health.json`.
- Si todas las velas fallan, el job sale con error y `Pipeline health` lo detecta.

### `data_status.fresh = false`

- Revisar el ultimo run del colector.
- Ejecutar `workflow_dispatch` en `Collect BTC public data`.
- Volver a ejecutar `BTC decision log` después de que el colector termine.
- No usar el trigger viejo: el motor ya lo bloquea.

### `eval.json` con 0 muestras

Es normal al inicio. Hacen falta 4h de velas futuras después de cada decision. El evaluador tambien necesita que el nivel tenga `hold_prob`.

### Workflow falla al hacer push

- Los workflows de escritura comparten `concurrency: data-write`.
- Ya hacen `pull --rebase` antes del push.
- Si persiste, revisar que otro proceso este escribiendo en `main` y volver a lanzar el workflow.

### El dashboard no muestra la decision

- Verificar que `analysis/data/latest_decision.json` exista en `main`.
- GitHub raw puede cachear; el dashboard agrega `?x=timestamp`.
- Si el navegador bloquea CORS, abrir el dashboard desde GitHub Pages o local; `raw.githubusercontent.com` permite CORS.

## Seguridad

- No agregar claves de exchange al repo.
- No agregar endpoints de ordenes.
- Los workflows solo necesitan `contents: write` para commitear datos; no usar `pull_request_target`.
- Si se agrega una API de IA, usar GitHub Secrets y solo para resumen/contexto, nunca para decidir niveles.

## Actualizar el modelo

1. Entrenar offline y guardar model card (`modelo_toques.json`).
2. Validar holdout y backtest OOS.
3. Actualizar `hold_model.py` y sus tests.
4. Correr la suite completa.
5. Desplegar y monitorear `eval.json` y `backtest.json` durante varias semanas.
6. No cambiar el modelo por una muestra chica o un solo corte.

## Retencion y crecimiento

- `klines_5m.jsonl`: maximo 200.000 lineas.
- `news.jsonl`: maximo 5.000 lineas.
- El resto de archivos crece lento (1h/4h/1D y derivados).
- Si el repo se acerca al limite de GitHub, archivar datos viejos en una rama o release, no borrar la historia sin respaldo.
