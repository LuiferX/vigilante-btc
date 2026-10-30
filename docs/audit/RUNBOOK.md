# docs/audit/RUNBOOK.md — fallos medidos y qué significan

**Fecha:** 2026-10-30 · Verificado por API contra el repo real (no de memoria).

## 1. Latencia y cadencia (el pliego pedía medirla)

| Workflow | Duración mediana (10 corridas) | Gap real entre corridas |
|---|---|---|
| Vigilante BTC Cloud | **41 s** (39-43) | **15,3 min** mediana (cron `*/5` de respaldo; el motor real es cron-job.org) |
| Oyente | 11 s | ~5 min |
| OOS refresh (diario) | 26 s | ~24 h |
| Tests | 10 s | por push |
| Analysis tests | 20 s | por push |
| Vigilia latido | 16 s | ~15 min |

**Conclusión: la promesa del README ("cada 15 min") es CIERTA.** No hay pipeline de
~4 h que corregir. Si algo se retrasa, es cola de GitHub Actions (los schedules se
pueden demorar en horas punta), no el trabajo en sí.

## 2. Censo de fallos (últimos 100 runs con `status=failure`)

| Workflow | Fallos | Estado |
|---|---|---|
| Vigilia latido | 73 | **Causa raíz confirmada y ARREGLADA** (2026-10-27): el job `avisar` no tenía `actions/checkout`, así que `gh` no tenía repo del que colgarse (`GH_REPO` explícito lo resolvió). Los 73 son históricos; desde el fix, verde. |
| pages build and deployment | 8 | Transitorios (redeploys de la rama `dashboard`). Reintentar; si persiste, mirar el log del paso *Deploy*. |
| Oyente | 4 | Fallan en *Publicar dashboard (rama dashboard)*: el `force-push` de una rama huérfana cada 5 min es intrínsecamente racista. Mitig cuando aplique P1-2.2 (ver abajo). |
| Lint y tipado / Tests | 3 + 3 | Histórico de mis propios commits en rama (rojos locales que arreglé). En `main`, verde. |
| Vigilante BTC Cloud | 2 | Transitorios (red/Binance). El propio workflow trae `|| echo` en pasos no críticos. |
| OOS refresh (diario) | 2 | Fallan en *Guardar evidencia OOS*: el paso que además hace `rebase origin/main` + `push --force-with-lease`. **Patrón de carrera**: publica a `main` cada 24 h compitiendo con el analista y el self-heal. |
| OOS refresh (semanal) | 2 | Idem, semanal. |

## 3. Patrón común en los que siguen fallando

**Todos los fallos restantes son de escritura git concurrently a una rama
compartida** (`dashboard` por Oyente cada 5 min; `main` por OOS-refresh cada 24 h
frente a pushes del analista cada 15 min). No es un bug de Python: es protocolo.

**Dirección de arreglo (P1-2.2):**
- `dashboard`: una sola dueña (hoy solo Oyente: verificado), mismo `concurrency.group`
  para toda escritura a esa rama, y publicar el árbol completo una vez (el
  `checkout --orphan` + `git rm -rf` ya lo hace; falta agrupar la concurrencia).
- `main` desde OOS-refresh: en vez de `rebase + force-with-lease` sobre `main`,
  publicar la evidencia como artefacto del run (actions/upload-artifact) o dejarla
  en la rama `estado`/`dashboard` que ya son de escritura única.

## 4. Cómo se ve un fallo y qué hacer

1. `Actions → el run rojo → el step que falla` (los nombres de step ya identifican
   la familia: *Publicar dashboard* = carrera de rama; *Guardar evidencia OOS* =
   carrera de rama; *Avisar con issue unica* = gh sin repo).
2. Si el paso es de red (Binance, GitHub API): **re-ejecutar**; el workflow está
   diseñado para no romperse por eso.
3. Si el paso es de rama: no reintir a ciegas; esperar la siguiente ventana o
   aplicar la dirección de §3.

## 5. Alerta automática ( P1-2.3, propuesta )

Añadir a `vigilia.yml` (que ya funciona): un job que consulte los runs de los
workflows críticos (`Vigilante BTC Cloud`, `OOS refresh`, `Oyente`) y abra issue si
2 corridas seguidas fallan. Queda propuesto; no implementado en esta tanda.
