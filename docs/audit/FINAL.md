# docs/audit/FINAL.md — Informe final de la misión de auditoría

**Fecha:** 2026-10-30 · **Rama fusionada:** `audit-p0` → `main` (`be04da1e56`)
**Baseline:** `docs/audit/BASELINE.md` (Fase 0, cada claim verificado ejecutándolo)

## 1. Tabla: hallazgo → fix → test → evidencia

| Hallazgo | Fix | Test de regresión | Evidencia |
|---|---|---|---|
| **Gate fail-open**: `aplicar_gate_alerta(True, motivo_direccional, 'alerta', None)` dejaba **pasar** la alerta | Fail-closed: gate no-dict ⇒ silenciar | `gate fail-closed sin dict` (fallaba: `(True,…)`) | 700 pruebas/3 fallos → **703/0** |
| **Clasificadores divergentes**: `ruptura` se medía como direccional pero el gate no la silenciaba; `mecha` al revés | `es_alerta_direccional` ampliado con las familias que `DIRECCIONES_MEDIBLES` mide (los contextos "no es entrada/chop/contra sesgo" siguen excluidos) | `ruptura es direccional para el gate` | mismo |
| **Canal OOS abría con el vivo negativo** (hoy skill −0,009, n=84) | El canal OOS exige además que el vivo no contradiga (skill>0, ECE≤0,08, drift≠alert, con ≥30 efectivas) | `gate no abre con vivo negativo` | gate con `validation.json` de hoy: **ABIERTO(oos) → CERRADO** con razón explícita |
| **`aggregate()` anclado al primer bar** (0/10 buckets alineados) | Buckets anclados a **borde de reloj** (múltiplo de bars×5min) | `test_aggregate_alineado_a_reloj` (antes: 03:10/04:10) | ahora :00 y 00/04/08 |
| **`cortar_htf` incluía la vela HTF en curso** (look-ahead de borde en el replay) | Cuenta solo la vela **cerrada** (openTime + dur ≤ cutoff) | `test_cortar_htf_sin_vela_en_curso` | corte 10:30 con velas 1h → solo la 09:00 |
| **`decide()` sin `now` media frescura contra la propia vela** (dato viejo parecía fresco) | Default = **reloj real**; replays/tests fijan `now` | `test_decide_sin_now_reporta_edad_real` | sin now → `data_age_min` real y `fresh=False` |
| **3 copias del modelo podían divergir en silencio** | Test de **fuente única** (versión/coef/intercept/features/mean/scale + sello) | `test_copias_no_divergen`, `test_toques_apunta_al_mismo_modelo` | 3 copias idénticas hoy |
| **Cierres de papel duplicados** (el log real tenía 1 exacto) | Si el último registro es idéntico (dir/res/pnl/fecha), no se añade | guardia en `main()` + verificación del log de `estado` | duplicados reales: 1 → 0 en escritura nueva |

## 2. Métricas post-fix (reportadas tal cual salieron, como manda el pliego)

| Métrica | Antes | Después |
|---|---|---|
| Backtest WF (11 folds, 11.049 muestras) | baseline 0.0247 · c0 0.0286 · e1 0.0243 · e3 0.0284 · e4 0.0285 · e2 0.0164 · meta 0.0232 | **IDÉNTICO** (el look-ahead de borde existía pero el sesgo nativo no lo mezclaba; la métrica no mejora ni empeora) |
| Gate con datos de hoy (vivo −0,009, n=84) | ABIERTO (canal oos) | **CERRADO** con razón: "muestra_media · 84 efectivas · skill −0,01 · ECE 0,03 · veto vivo bloquea OOS" |
| Frescura | `now or event_time` | reloj real por defecto |
| Suites | 699 | **703** (4 regresiones nuevas) + 2 en analysis |

## 3. Lo que NO hice y por qué (honesto)

| Pendiente | Por qué |
|---|---|
| `LICENSE` → MIT/Apache | **Refutado en el baseline**: ya es licencia válida explícita (personal, todos los derechos reservados, 739 B). Sustituirla por MIT es decisión del autor, no un arreglo de ingeniería |
| Exigir `solape_descontado=true` para el OOS | **Refutado**: `backtest.py` usa step=48=horizon ⇒ las ventanas no se solapan; el flag false solo dice "no hacía falta descontar" |
| Ledger `legacy` vs `post-fix` y etiquetar la LIQ −25,67R como outlier | El split de reporte es trabajo de `paper_report.py` (dueño: pista T3); llegó el corte de contexto. Queda anotado |
| CI que cubra `vigilante/**` (paths de `test.yml`) | P1; requiere decisión de alcance (¿correr 703 casos en cada push de vigilante/?). Anotado, no hecho |
| Una sola dueña de la rama `dashboard` | P1; el arreglo toca dos workflows y su protocolo de publicación. Anotado, no hecho |
| `RUNBOOK.md` con los fallos de workflows | P1; el censo está en el baseline (Vigilia 73 históricos = bug ya arreglado; Pages 8, Oyente 4…). Anotado, no escrito |
| Reducir 376 `except Exception` / trocear `main()` | P2; requiere cirugía mayor con su propia tanda de tests |
| Alinear docs al gate real | P2; `CAMINO_A_OPERAR.md` se actualiza al cierre de la tanda P1 |

## 4. Veredicto honesto

**¿Hay edge demostrado? No — y ahora el bot lo dice más fuerte que antes.**
La skill OOS sigue siendo +2,6% (n=245+), la viva sigue **negativa** (−0,9%, n=84), y el gate —que antes se abría por el canal OOS ignorando al vivo— **hoy está cerrado**. Es la primera consecuencia real de esta auditoría: el bot pasó de "señal con evidencia débil" a **silencio honesto**, que es lo que el pliego pedía.

**¿Se rompió algo?** No: 703 tests, 10 suites de analysis, colector, `ruff`, `compileall` y `mypy` verdes; CI verde en cada commit fusionado. Dos errores de proceso cometidos y reparados en el camino (empujar con test local en rojo dos veces) quedan documentados en el historial de commits; la lección quedó aplicada: **verificar local todo antes de cada push**.

**Commits:** `4fcb23a6` (gate) · `624bffb8` (HTF) · `d803f796`+`782df042` (frescura) · `34f42a1d` (fuente única + duplicados) · fusionado `be04da1e56`.

## 6. P2 — higiene (2026-10-30, commit `5fbe2b2c11`)

| Ítem | Estado | Evidencia |
|---|---|---|
| `comandos.py` de la raíz | ✅ BORRADO | nadie lo usaba: 0 workflows, 0 imports, 0 tests. El chat en dos vidas vive en `vigilante/comandos.py` |
| `backtest.py` de la raíz | ✅ CONSERVADO (con test) | 3 tests de `test_vigilante.py` lo ejecutan y leen: cumplió la regla "si se conserva, que esté testeado" |
| Bloque NN muerto | ✅ (ya estaba, 27/10) | el fantasma salió antes de esta misión; queda registrado en EXPERIMENTOS.md |
| **README alineado** | ✅ | documenta que desde el 30/10 el canal OOS tampoco abre con el vivo en contra, y que con el `validation.json` de hoy el gate del bot queda **CERRADO** aunque el fichero reporte OOS |
| **SCORECARD alineado** | ✅ | "Validación del modelo" **9,0 → 6,0** y el global **9,0 → 8,6**, con el motivo escrito: la ventana viva está en −0,9% (n=84) |
| Trocear `main()` / `decide` / `build_parte` | 📋 PENDIENTE | cirugía mayor; requiere su propia tanda de tests de extracción |
| Reducir 376 `except Exception` / ruff E,W,I | 📋 PENDIENTE | P2 profunda; ver docs/TIPADO.md para el punto de partida |

## 7. Veredicto final de la misión

**El objetivo del pliego — "corregir defectos de correctitud sin maquillar métricas y sin afirmar edge que no está demostrado" — está cumplido.** El hallazgo más importante de la auditoría fue que **el gate se abría por un canal OOS mientras el canal vivo decía lo contrario**; hoy el bot está **CERRADO** y ningún doc afirma edge sin citar su fecha.

**Commits de la misión:** `4fcb23a6` gate · `624bffb8` HTF · `d803f796`/`782df042` frescura · `34f42a1d` fuente única + duplicados · `3619c2b252` CI + RUNBOOK · `04e3cf7127` higiene de datos · `5fbe2b2c11` higiene + docs · fusionado `7f81631b74`, `audit-p0/p1/p1b/p2` fusionadas y borradas.

## 8. P1 — lo cerrado después (2026-10-30)

| Ítem | Estado | Evidencia |
|---|---|---|
| **CI que cubre lo que importa** | ✅ HECHO (`3619c2b252`) | `test.yml` ahora dispara con `vigilante/**`, `analysis/**`, `modelo_toques.json`, `collector/**`, `tools/**` (antes 5 archivos raíz) y corre las suites de `analysis/` en cada push que las toca |
| **RUNBOOK con fallos medidos** | ✅ HECHO | `docs/audit/RUNBOOK.md`: latencia por API (Vigilante 41 s mediana, gap 15,3 min ⇒ el README no miente), censo de los últimos 100 fallos y su causa raíz |
| **Latencia ~4 h del pipeline** | ⛔ REFUTADO | mediana 41 s, gap 15,3 min |
| **Dos dueñas en `dashboard`** | ⛔ REFUTADO | solo `oyente.yml` escribe esa rama (`contents: write # solo para publicar la rama dashboard`); `oos-refresh` hace `force-with-lease` sobre `main`, no sobre `dashboard` |
| **Carreras de escritura git** (Oyente/OOS-refresh) | 🔎 DOCUMENTADO con dirección | patrón común: `force-push` a ramas compartidas. Dirección: agrupar concurrencia y publicar evidencia como artefacto. No implementado (toca protocolo de dos workflows) |
| **Alerta si un crítico falla 2 veces** | 📋 PROPUESTO | en RUNBOOK §5; no implementado |
| **Poda de JSONL / append sin leer todo / escritura atómica** | ✅ HECHO (`04e3cf7127`) | `append_jsonl` ya no lee el fichero completo (índice incremental `.idx` con fallback correcto si el fichero cambió por fuera; el test cazó un bug propio: el índice stringificaba claves y el dedup compara tipos). Escritura **atómica** (tmp+fsync+`os.replace`) en `latest_decision.json`/`health.json`. Colector: 13 casos. |
| **Concurrencia de la rama `dashboard`** | ✅ RESUELTO | `oyente.yml` ya tiene `concurrency: group: oyente` y es la única escritora (verificado): no hay segunda dueña que agrupar. |
| **Alerta si un crítico falla 2 veces** | 📋 PROPUESTO | queda para la siguiente tanda |

**Veredicto P1:** el agujero que dejaba pasar código roto a producción está
cerrado (CI real sobre el árbol que importa). Lo que queda de P1 es protocolo de
ramas y retención de datos: trabajo de precisión, no de parches.

