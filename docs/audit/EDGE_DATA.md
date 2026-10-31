# docs/audit/EDGE_DATA.md — Fase 0: gate de datos para H1/H2

**Fecha:** 2026-10-31 · Pre-registro de la misión: `analysis/EXPERIMENTOS.md`
(sección "MISIÓN EDGE 2026-10-31").
**Regla aplicada:** ningún resultado de retorno fue observado antes de este
documento. Solo cobertura y conteos de eventos.

## 1. Cobertura medida

| Dataset | Antes | Tras backfill | Muestreo | Veredicto |
|---|---|---|---|---|
| klines 5m | 402.629 filas (2023-01-01 → 2026-10-30, **1.398 días**) | — | 5 min | ✅ PASA |
| funding | 166 filas (**35 días**, ventana del colector) | **4.199 filas (2023-01-01 → 2026-10-31, 1.399 días)** | 8 h | ✅ PASA (tras backfill) |
| open interest | 1.138 filas (**3,9 días**) | **imposible** | 5 min | ❌ **FALLA** |
| taker buy/sell | 1.140 filas (**3,9 días**) | **imposible** | 5 min | ❌ **FALLA** |

## 2. Límites duros descubiertos en la API (verificado, no asumido)

- `GET /fapi/v1/fundingRate` pagina sin límite práctico: 1.000 registros por
  página, cubre 2023-01-01 → 2026-10-31 sin huecos.
- `GET /futures/data/openInterestHist` y `/futures/data/takerlongshortRatio`
  **rechazan con HTTP 400** cualquier `startTime` más antiguo de **30 días**
  exactos (probado: 31d → 400; 30d → OK). No existe backfill público de OI ni
  taker más allá de 30 días.

## 3. Eventos independientes que daría H1 (conteo, sin mirar retornos)

Umbrales causales por percentil de la ventana trailing (sin look-ahead) y
cooldown explícito:

| Variante | Eventos independientes | Por año |
|---|---:|---:|
| p95/p5 · ventana 30d · cooldown 24h | **604** | 158 |
| p90/p10 · ventana 30d · cooldown 24h | 786 | 205 |
| p95/p5 · ventana 30d · cooldown 8h | 1.155 | 302 |
| p90/p10 · ventana 60d · cooldown 24h | 730 | 191 |

Criterio (≥300 eventos por hipótesis): **H1 lo cumple incluso en su variante
más estricta** (604 ≥ 300).

## 4. Eventos que daría H2

El histórico disponible (**30 días** = 720 barras 1h) no permite una ventana
trailing de 30d comparable con productividad de eventos: el producto de "OI en
p5 de la ventana" **y** "taker sell en p95" deja docenas de eventos, muy lejos
de los 300 exigidos.

## 5. Veredicto del gate

| Hipótesis | Veredicto | Razón |
|---|---|---|
| **H1 — funding extremo → reversión** | ✅ **PASA** → procede a Fase 1 | backfill posible, 604 eventos independientes (variante canónica) |
| **H2 — cascada de liquidación → rebote** | ⛔ **DETENIDA** → *test no concluyente por falta de datos* | tope duro de 30 días en la API de OI/taker; imposible alcanzar 300 eventos independientes. No se inventan conclusiones con 720 barras |

## 6. Qué se desestima honestamente

- No se sustituye H2 por otro proxy "porque se parece": la misión fijó la regla.
- No se declara edge de H2 por muestras de 30 días.
- H1 se corre con los parámetros canónicos de la misión y las variantes
  declaradas, con corrección por múltiple testing.
