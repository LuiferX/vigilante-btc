<div align="center">

```
 ██████╗ ██╗  ██╗    ██╗    ██╗  ██╗██╗   ██╗
██╔═══██╗██║  ██║    ██║    ██║  ██║██║   ██║
██║   ██║███████║    ██║    ███████║██║   ██║
██║   ██║██╔══██║    ██║    ██╔══██║╚██╗ ██╔╝
╚██████╔╝██║  ██║    ╚═╝    ██║  ██║ ╚████╔╝
 ╚═════╝ ╚═╝  ╚═╝           ╚═╝  ╚═╝  ╚═══╝
```

### *¿Por qué un nivel de Bitcoin aguanta... o no?*

**El bot que mide en vez de prometer.** Sin órdenes, sin claves, sin cuentos.

`Solo-lectura` · `Stdlib` · `Medición honesta` · `Negativos publicados`

</div>

---

## 🧠 La idea

Cada 15 minutos, el Vigilante mira el mercado público de BTC y construye una
foto honesta: zonas reales (3+ toques en 6h), sesgo 1h/4h/1D, liquidez, macro,
noticias con peso, y una **probabilidad calibrada** de que un nivel aguante las
próximas 4h.

Y cuando la evidencia no da, **se calla**. Un bot que te dice "hoy no operes"
vale más que uno que siempre tiene una respuesta.

> *"OH WHY" no es un gritó de frustración: es la única pregunta que este repo
> se tomó en serio — y la razón por la que sus métricas se publican con la
> misma letra cuando salen mal.*

---

## 🛡️ Lo que garantiza

| Promesa | Cómo se cumple |
|---|---|
| **Nunca opera** | `guardia_lectura()` fail-closed: si ve claves de trading, se niega a arrancar |
| **Nunca miente** | Gate de validación: sin muestra, skill y calibración, la alerta direccional **se silencia** |
| **Nunca reinventa** | Modelo congelado (`toques-wf-1`): no se mueve por corazonada, solo por evidencia |
| **Siempre verificable** | 700+ tests, ruff `E,F,W,I`, mypy, CI verde en cada commit |

---

## 📡 Ahora mismo

- **Gate direccional:** `CERRADO` — la ventana viva (skill −0,9%, n=84) no
  sostiene el canal OOS. El bot informa y **no invita a entrar**.
- **Modelo:** `toques-wf-1` — OOS +2,6% (n=254), ECE 0,012. Congelado desde
  el 24/10/2026 con criterios públicos de descongelamiento.
- **Producción:** decisiones cada 15 min, [monitor en vivo](https://luiferx.github.io/vigilante-btc/monitor.html)
  y [motor 4h](https://luiferx.github.io/vigilante-btc/motor.html).
- **Calidad:** SCORECARD 8,6/10 — subiendo por ingeniería, no por promesas.

---

## 🧩 Qué hay dentro

```
collector/    datos públicos de Binance + noticias RSS (con fallback oficial)
analysis/     modelo de aguante, motor de decisión, evaluación, backtest OOS
vigilante/    14 módulos: matemática, mercado, papel, gate, render, comandos...
docs/         arquitectura, runbook, auditoría (BASELINE / FINAL / RUNBOOK)
.github/      pipeline cada 15 min + tests + validación + vigilia
```

- **`vigilante_cloud.py`** — 1.492 líneas de orquestación (eran 5.820)
- **`test_vigilante.py`** — 703 pruebas
- **Dashboards** en `dashboard/` y `docs/monitor.html` — solo lectura.

---

## 🔬 Cómo se mide (y por qué creerle)

- **Etiquetas auditadas**: una reimplementación independiente reproduce las
  métricas oficiales al decimal (diferencial en `docs/audit/`).
- **Sin look-ahead**: los buckets HTF se anclan al reloj y solo se usan velas
  cerradas; hay test de regresión para cada uno.
- **Skill neta de costos**: `analysis/cost_model.py` calcula cuánto acierto
  hace falta solo para pagar las comisiones (con marco 0,5%: 64%).
- **Papel con comisiones**: la curva del paper trading es neta, no un dibujo.

---

## 🚀 Uso local

```bash
python collector/collector.py
python analysis/run_decision.py --klines collector/data/btcusdt/klines_5m.jsonl --out analysis/data/decisions.jsonl
python analysis/validation.py --eval analysis/data/eval.json --backtest analysis/data/backtest.json --decisions analysis/data/decisions.jsonl --klines collector/data/btcusdt/klines_5m.jsonl --collector-health collector/data/health.json --out analysis/data/validation.json --history analysis/data/validation_history.jsonl
python analysis/check_health.py
```

Loop local:

```bash
python analysis/run_loop.py --minutes 60
```

Tests:

```bash
python collector/test_collector.py
cd analysis && python test_hold_model.py && python test_decision_engine.py
python test_pipeline.py && python test_validation.py && python test_dashboard.py
```

---

## 📚 Documentación

[Arquitectura](ARCHITECTURE.md) · [Runbook](RUNBOOK.md) · [Scorecard](SCORECARD.md) ·
[Experimentos](analysis/EXPERIMENTOS.md) · [Auditoría](docs/audit/FINAL.md) ·
[Camino a operar](CAMINO_A_OPERAR.md)

---

## 🚫 Lo que NO es

- No es señal de compra/venta. No es win rate. No ejecuta órdenes.
- La probabilidad de aguante es condicional al nivel y a 4h; **no promete
  ganancia**.
- El backtest OOS (muestra chica) mostró calibración razonable y
  **edge predictivo no demostrado**: el repo lo dice en su propio README.

---

<div align="center">

**OH WHY?** — porque la única ventaja que no se puede copiar es la honestidad.

</div>
