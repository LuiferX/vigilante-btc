# docs/audit/BASELINE.md — Fase 0: diagnóstico reproducible

**Fecha:** 2026-10-29 · **Commit base:** `main@HEAD` · **Misión:** auditoría P0/P1/P2
**Regla aplicada:** nada de código de producción hasta cerrar este documento.
Cada hallazgo del pliego se verificó **ejecutándolo**, no leyéndolo.

## 1. Comandos y salidas

```
python test_vigilante.py              → OK 699 pruebas | FALLOS 0
python collector/test_collector.py    → Ran 12 tests ... OK
cd analysis && python test_*.py        → todos OK (11 suites, 96+ casos)
python -m compileall -q .             → exit 0
python -m ruff check .                → All checks passed!  (select=["F"])
python -m mypy vigilante/ collector/ tools/ → Success: no issues found in 18 files
```

## 2. Veredicto de cada claim del pliego

| # | Claim del pliego | Veredicto | Evidencia ejecutada |
|---|---|---|---|
| 1 | Suite 699 en verde | **CONFIRMADO** | salida arriba |
| 2 | `validation.json`: status muestra_media, vivo skill −0.009, n=84, PSI 0.206, gate ok con canal oos, OOS n=254 skill +0.026, `solape_descontado=false` | **CONFIRMADO** (valores exactos de hoy) | pull de `main` |
| 3 | `hold_model.coef`: 6/9 en 0, sobreviven hourc/dow/x_atr288 | **CONFIRMADO** | lectura de `MODEL` |
| 4 | Paper: 12 cerradas, pnl −33.57, PF 0.11, sharpe −0.33, r_medio −2.306, peor −25.67 | **CONFIRMADO** | `dashboard/paper_summary.json` (publicado) |
| 5 | `LICENSE` = "OH why?" (9 bytes) | **REFUTADO** | es "LICENCIA DE USO PERSONAL Y PRIVADO", Copyright LuiferX 2026, 739 bytes. Es licencia válida explícita (todos los derechos reservados) |
| 6 | skill vivo oficial es honesto | **CONFIRMADO (diferencial)** | mi implementación independiente sobre `decisions.jsonl` + cache propio: n=1330, skill −0.0094, brier 0.1378, ECE 0.0312 vs oficial n=1328, −0.0093, 0.1380, 0.0310. **La divergencia inicial fue mi caché de velas vieja**: con cache refrescado coinciden |
| 7 | `aplicar_gate_alerta` fail-open con gate no-dict | **CONFIRMADO (bug real)** | `aplicar_gate_alerta(True, "Señal fuerte ALZA (confianza 75%)", "alerta", None)` → `(True, …, False)`: **la alerta pasa**. Con `{}` y con `{"ok":False}` sí silencia |
| 8 | `aggregate()` ancla buckets al primer bar | **CONFIRMADO (con radio acotado)** | datos desde 03:10 → buckets 03:10/04:10/05:10: **0/10 alineados a reloj**. Radio: solo sesgo HTF de *fallback* (`agregado_desde_5m`) y pivotes de confluencia; el vivo usa `nativo_1h_4h_1d` cuando hay HTF; las 9 features del modelo de aguante **no dependen** de aggregate |
| 9 | `cortar_htf` (bisect_right) look-ahead de borde | **CONFIRMADO** | corte 10:30 → devuelve el bar 10:00 en curso, cuyo OHLC en el archivo llega hasta las 11:00 (futuro). Afecta features HTF del replay/entrenamiento |
| 10 | `decide()` sin `now` reporta frescura falsa | **CONFIRMADO** | L722: `now = now or event_time` → con datos viejos y sin `now`, `data_age_min≈0`: **el dato viejo parece fresco** |
| 11 | OOS requiere `solape_descontado=true` | **REFUTADO** | `backtest.py`: step=48 y horizon=48 → las ventanas de futuro **no se solapan**; el flag false significa "no hacía falta descontar" |
| 12 | `latest_decision`: levels_with_hold=0, calidad 6.2, grado D | **REFUTADO hoy** | calidad 6.8/10, summary "BAJA · vol expansion · esperar_confirmacion" (los claims eran de otro momento) |
| 13 | NN muerta en `vigilante_cloud.py` L880-887 | **YA RESUELTO** | bloque fantasma retirado el 2026-10-27; queda comentario de auditoría (ver EXPERIMENTOS.md) |
| 14 | `test.yml` no cubre `vigilante/**` | **CONFIRMADO** | paths: solo 5 archivos raíz + workflows/** |
| 15 | Fallos de workflows | **CONFIRMADO (censo propio)** | últimos 100 runs: Vigilia 73 (histórico del bug ya arreglado; ahora verde), Pages 8, Oyente 4, Lint 3, Tests 3, Vigilante 2, OOS diario 2, OOS semanal 2 |

## 3. Hallazgo NUEVO no listado en el pliego (grave)

**Las dos clasificaciones de "direccional" no coinciden:**

| motivo | `tipo_de_motivo` (medible) | `es_alerta_direccional` (lo que el gate silencia) |
|---|---|---|
| "ruptura BAJISTA confirmada en 82.000" | `ruptura` → **medible=True** | **False** |
| "mecha de rechazo en soporte" | `otro` → medible=False | **True** |
| "Señal fuerte ALZA (confianza 75%)" | `fuerte` → True | True |

Consecuencia: una **ruptura** se contabiliza como direccional en las estadísticas (scoreboard, pendientes) pero **el gate no la silencia** — la promesa "si no hay evidencia, el bot se calla" tiene un agujero justo en la familia `ruptura/estructura`, que el pliego explícitamente quiere cerrada. Y a la inversa, la `mecha` se silencia sin medirse.

## 4. Discrepancias de mi propio proceso (declaradas)

- Mi copia local de `analysis/data/validation.json` estaba **del 24-10** (skill −6.8% vs el −0.9% actual): el diferencial inicial "divergía" por datos viejos, no por bug. Refrescada.
- El cache local de velas llegaba al 27-10; refresqué la cola (858 velas) para poder etiquetar los eventos del 28-29.
- Un motivo sintético mío ("ruptura BAJISTA confirmada…") resultó no-direccional para el gate; con el motivo canónico de los tests el fail-open quedó probado.

## 5. Estado de las "puertas" que el pliego exige cerrar

| Puerta | Hoy |
|---|---|
| Gate con `validation.json` actual | **ABIERTO (canal oos)** pese a vivo skill −0.009 · n=84 · PSI watch. Política a corregir en P0-1.1 |
| Look-ahead de borde HTF | presente, P0-1.2 |
| Buckets de agregación | desalineados, P0-1.2 |
| Frescura fail-closed en `decide()` | `now or event_time`, P0-1.5 |
| Clasificadores direccionales | divergentes, P0-1.1 (nuevo) |
| Modelo duplicado en 3 copias | sigue (P0-1.3) |

## 6. Conclusión de Fase 0

**El pliego acierta en los 5 puntos P0 que propone** (gate, alineación HTF, fuente única del modelo, frescura, ledger) **y yerra en dos** (LICENSE, solape_descontado). Las métricas vivas publicadas son honestas — verificado por diferencial independiente. El fallo más grave no estaba en la lista: **el gate no cubre la familia `ruptura`**, que la propia medición trata como direccional.

Siguiente: Fase 1 (fixes P0 con test de regresión que falle antes y pase después). Sin tocar coeficientes del modelo.
