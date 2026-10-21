# Modelo de aguante de niveles v2

Modelo logistico que estima una sola cosa:

> Despues de 3+ toques de un nivel, probabilidad de que el precio **no cierre 0,5% mas alla del nivel** en las siguientes **4 horas**.

No es un win rate, no es una senal de entrada y no ejecuta ordenes. Es contexto para decidir si un nivel se esta defendiendo o se esta desgastando.

## Que cambio frente al modelo anterior

- Regresion logistica con regularizacion L1 (`C=0.03`), que apaga features ruidosas.
- 9 features: distancia al nivel, ATR 14, distancia a EMA200, rango de la vela, hora, dia de la semana y ATR de 4h/12h/24h.
- Se agregaron ATR de 4h, 12h y 24h. La volatilidad de 24h es el driver negativo mas fuerte: a mas volatilidad, menos aguante.
- Se quitaron features que no aportaban fuera de muestra.

## Metricas fuera de muestra

Entrenamiento hasta el 31-12 del ano anterior; prueba en el ano siguiente.

| Ano | AUC antes | AUC v2 | Brier antes | Brier v2 |
|---|---:|---:|---:|---:|
| 2024 | 0,601 | 0,606 | 0,2035 | 0,2015 |
| 2025 | 0,645 | 0,664 | 0,1705 | 0,1702 |
| 2026 | 0,650 | 0,665 | 0,1765 | 0,1746 |

Base 2026: 75,7% de los eventos aguantan. El modelo no cambia la base; ordena mejor los casos.

## Calibracion 2026

| Score | n | Aguante real | Score medio |
|---|---:|---:|---:|
| < 0,60 | 28 | 57,1% | 53,4% |
| 0,60 - 0,70 | 112 | 58,9% | 66,2% |
| 0,70 - 0,80 | 318 | 76,1% | 75,5% |
| >= 0,80 | 167 | 89,2% | 82,8% |

El tramo >= 0,80 es conservador: predice ~83% y acierta ~89% en 2026. El tramo 0,60-0,70 esta algo sobreconfiado (~7 puntos).

## Backtest OOS del motor

`backtest.py` recorre el historico, construye cada contexto solo con datos disponibles en ese momento y etiqueta el futuro a 4h. Es una prueba honesta, no una optimizacion.

Corte del 21-10-2026 sobre datos posteriores al entrenamiento (2026-10-01 a la fecha):

| Metrica | Valor |
|---|---:|
| Muestras | 39 |
| Decisiones | 25 |
| Brier | 0,1642 |
| Tasa base | 79,5% |
| Brier skill vs base | -0,0069 |
| Tramo >= 0,80: n | 24 |
| Tramo >= 0,80: real | 83,3% |

Lectura: la calibracion es razonable (predice ~80%, acierta ~79,5%), pero el modelo **no demuestra edge** frente a predecir la tasa base en esta muestra chica. No se cambia el modelo por este corte; se sigue midiendo. El valor del repo esta en la calidad del contexto y la medicion, no en prometer una ventaja predictiva.

## Interpretacion

Los `drivers` del modelo se leen como aportes al logit:

- `x_atr288` negativo: volatilidad de 24h alta empuja el aguante hacia abajo.
- `rng` negativo: una vela actual amplia tambien empuja hacia abajo.
- `hourc` / `dow`: hay horas y dias con mas aguante que otros (liquidez/estacionalidad).
- `dist`, `atr`, `ema200`: ajustes finos; no dominan.

Ejemplo:

```python
import hold_model as hm

kl = hm.load_klines_jsonl("data/btcusdt/klines_5m.jsonl")
r = hm.score_level(
    kl,
    level=82_500,
    price=kl[-1]["c"],
    now=kl[-1]["t"],
    side="Resistencia",
)
print(r["prob"], r["tier"])
for d in r["drivers"]:
    print(d["feature"], round(d["contribution"], 3))
```

## Caveats

- La probabilidad es condicional al evento: 3+ toques en 6h y salida por **cierre** de 0,5%, no por mecha.
- Un score alto no significa movimiento favorable ni ganancia; significa que el nivel aguanto el rango de 4h.
- Es un modelo de BTC 2023-2026. Si cambia el regimen, hay que revalidar.
- No usar el score para filtrar todas las alertas sin medir: la muestra alta es chica y puede sobreajustar al ultimo mes.

## Motor de decision

`decision_engine.py` conecta este modelo con la lectura de niveles y el contexto:

- Detecta pivotes de 5m y los agrupa en zonas con ancho `max(0,30% del precio, 0,30 * ATR4h)`.
- Si el colector tiene `klines_1h/4h/1d.jsonl`, usa velas nativas para sesgo y pivotes. Si no, agrega desde 5m. Los pivotes de 1h/4h/1D son **confluencia**, no toques de 5m, y no se usan para inventar aguante.
- Calcula perfil de volumen de 24h: POC y value area (70%). El POC entra como nivel de contexto.
- Marca cada zona como soporte/resistencia segun el precio actual.
- Calcula el aguante con `hold_model` solo si la zona tiene 3+ toques en 6h.
- Clasifica la estructura actual: `dentro` / `arriba` / `abajo`, `recent_sweep` y `break_confirmed` (2+ cierres fuera).
- Devuelve estado (sesgo 1h/4h, volatilidad, POC), escenarios base/alternativo/no hacer nada, trigger, invalidacion, confianza, riesgos y "no hacer nada".
- Incluye un `summary` de una linea y `drivers` por nivel para interpretar el aguante.
- **Guardrail de frescura:** si la ultima vela cerrada tiene mas de 20 minutos, `decision.action = datos_desactualizados`, la confianza baja y el trigger se reemplaza por "Sin trigger". No se publica una accion accionable con datos vencidos.
- Devuelve `data_status` con `fresh`, `age_min` y `max_age_min`.
- No ejecuta ordenes ni usa claves.

### Sesgo de mayor temporalidad

El sesgo principal ya no sale solo de 5m. Si hay velas nativas:

- 1h: EMA20/EMA50, precio contra EMA50 y pendiente.
- 4h: EMA8/EMA21, precio contra EMA21 y pendiente.
- 1D: EMA20/EMA50, precio contra EMA50 y pendiente.
- Si 4h y 1D coinciden, ese es el sesgo. Si estan en conflicto, `LATERAL`.
- Si faltan 4h/1D, usa 1h/4h agregadas desde 5m.
- `htf_bias_override` permite pasar el sesgo del Vigilante si se prefiere esa fuente.

### Puntuacion de calidad

Cada zona recibe una nota de 0 a 10. No es probabilidad de ganar:

- 4+ toques reales en 6h: hasta 3 puntos,
- aguante del modelo: hasta 3 puntos,
- volumen dentro de la zona: hasta 2 puntos,
- recencia del ultimo toque: 1 punto,
- confluencia (Vigilante + pivotes 1h/4h/1D): 1 punto,
- nivel redondo dentro de la zona: hasta 0,5 puntos.

La salida trae:

- `engine_quality`: completitud/coherencia del motor (datos, zonas, aguante, escenario, riesgos, frescura).
- `setup_quality`: la mejor zona.
- `quality.composite`: promedio de ambas.
- `quality.target` = 8,5, `quality.gap` y `quality.grade` (A/B/C/D).

El objetivo 8,5 es una meta de calidad de contexto, no una garantia ni una probabilidad. Si el score queda debajo, el `gap` dice cuanto falta y los riesgos dicen por que. No se infla el numero para llegar a 8,5: un setup con 4 toques, poco volumen o sin 1D puede quedar en 7-8.

### Uso

```bash
python decision_engine.py ../collector/data/btcusdt/klines_5m.jsonl
```

Uso desde Python:

```python
import decision_engine as de

out = de.decide_from_jsonl(
    "../collector/data/btcusdt/klines_5m.jsonl"
)
print(out["summary"])
print(out["quality"])
print(out["decision"]["base_scenario"])
print(out["decision"]["trigger"])
print(out["decision"]["invalidation"])
```

Para sumar niveles del Vigilante sin acoplarse a su repo:

```python
out = de.decide(
    kl,
    price=kl[-1]["c"],
    extra_levels=[{"precio": 82_500, "tipo": "resistencia", "toques": 4}],
)
```

O leer el estado publicado (solo lectura, sin token):

```python
extra = de.fetch_vigilante_levels()
out = de.decide(kl, price=kl[-1]["c"], extra_levels=extra)
```

Los niveles del Vigilante traen `n` como numero de origenes/confluencia, no como toques. El motor los muestra como contexto, pero no inventa aguante: solo calcula `hold_model` si la zona tiene 3+ toques reales en 6h.

La regla de ruptura es por **cierre** fuera de la zona. Mecha que sale y vuelve a entrar = sweep/falso quiebre, no continuidad.

### Registro, salud y evaluacion

`run_decision.py` ejecuta el motor y agrega una linea a `data/decisions.jsonl`. Evita duplicados por `event_time`. Tambien escribe:

- `data/latest_decision.json`: lectura para dashboard/clientes.
- `data/health.json`: frescura, accion, confianza, calidad y niveles con aguante.
- `data/eval.json` (via evaluador): Brier, skill, calibracion e intervalos.

```bash
python run_decision.py --out data/decisions.jsonl
python run_decision.py --vigilante https://raw.githubusercontent.com/LuiferX/vigilante-btc/estado/estado.json
```

`run_loop.py` repite el proceso cada hora en local. Es el equivalente al workflow sin depender de GitHub:

```bash
python run_loop.py --minutes 60
python run_loop.py --once
```

`evaluate_decisions.py` mide si el nivel aguanto 4h con la misma definicion del modelo (cierre 0,5% mas alla). Calcula Brier, Brier skill frente a la tasa base, calibracion, intervalos de Wilson por tramo y corte por lado. No mide win rate ni ganancia.

```bash
python evaluate_decisions.py --decisions data/decisions.jsonl
```

`backtest.py` hace la misma medicion sobre el historico OOS, reconstruyendo el contexto sin mirar el futuro:

```bash
python backtest.py --start 2026-10-01 --out data/backtest.json
```

`check_health.py` valida que la decision sea reciente y que el colector haya traido velas. Sale con codigo 1 si algo critico falla; el pipeline horario lo corre al final; el workflow manual permite repetirlo.

```bash
python check_health.py
```

### Tests

```bash
python test_hold_model.py
python test_decision_engine.py
python test_pipeline.py
python test_dashboard.py
python test_workflows.py
python ../collector/test_collector.py
```

Cobertura actual: 5 del modelo, 18 del motor, 7 de runner/evaluador/backtest/salud, 4 del dashboard, 6 de workflows y 10 del colector. CI compila todo y corre la suite en cada cambio de codigo.


