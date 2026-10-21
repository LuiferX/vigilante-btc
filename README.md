# BTC Trading System

Sistema de **analisis y contexto** para BTC. No ejecuta ordenes, no usa claves privadas y no manda dinero a ningun exchange.

## Vigilante BTC

El bot de alertas sigue en `vigilante_cloud.py` (modelo de aguante v2, detector de toques y avisos). Sus pruebas estan en `test_vigilante.py`. El workflow `Vigilante BTC Cloud` corre cada 5 minutos y solo avisa; no opera.

El sistema de analisis de este README es independiente y no modifica la ejecucion del Vigilante.

## Componentes

- `collector/`: datos publicos de Binance Futures y noticias RSS. Guarda velas 5m/1h/4h/1D, funding, open interest, long/short y taker.
- `analysis/`: modelo de aguante, motor de decision, registro y evaluacion.
- `dashboard/`: dashboard HTML de solo lectura, negro/blanco/gris con acentos neon.
- `.github/workflows/`: recoleccion horaria y decision horaria.

## Que produce el motor

- Zonas de soporte/resistencia con ancho `max(0,30% del precio, 0,30 * ATR4h)`.
- Sesgo nativo 1h/4h/1D.
- Perfil de volumen: POC y value area.
- Estado de la zona: dentro/arriba/abajo, sweep reciente y ruptura confirmada por cierres.
- Aguante del nivel solo si hay 3+ toques reales en 6h.
- Escenario base, alternativo, trigger, invalidacion, riesgos y "no hacer nada".
- Calidad 0-10 por zona y calidad compuesta, con objetivo 8,5.
- Registro en `analysis/data/decisions.jsonl` y evaluacion Brier/calibracion.

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
```

Loop local cada hora:

```bash
python analysis/run_loop.py --minutes 60
```

Tests:

```bash
cd analysis
python test_hold_model.py
python test_decision_engine.py
python test_pipeline.py
```

## GitHub Actions

- `Collect BTC public data`: cada hora en el minuto 17. Hace commit de `collector/data/`.
- `BTC decision log`: cada hora en el minuto 27. Hace commit de `analysis/data/`.

Ambos usan solo endpoints publicos/RSS y permisos de escritura del propio repo. No hay secretos de trading.

## Dashboard

`dashboard/index.html` se puede abrir local o publicar con GitHub Pages. Es solo lectura; el diario manual se guarda en `localStorage` del navegador.
