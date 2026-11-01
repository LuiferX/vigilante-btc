# EDGE_HORIZONTES.md — H6: estirar el horizonte no arregla el edge

**Fecha:** 2026-11-01 · Pre-registro: `analysis/EXPERIMENTOS.md`, sección
"H6 — HORIZONTES LARGOS" (commit `1bdf129353`, **anterior** a medir).
Código: `analysis/expr_horizontes.py` · Tests:
`analysis/test_expr_horizontes.py` (13 en verde, incluye signo del funding).
Datos: `analysis/data/edge_horizontes.json`

---

## La hipótesis

De todo lo medido, el horizonte era la única variable con gradiente a favor: el
bruto de la familia rebote pasaba de +0,02 % (4 h) a +0,09 % (24 h, alta
convicción) y el coste del viaje es fijo. Quedaba probar 12, 24, 48 y 72 h.

Novedad respecto a H3: **el funding durante el hold entra en el coste**. A 4 h
era despreciable (≤1 pago); a 72 h son 9 pagos. El gate lo midió antes:
acumulado mediano de +0,0117 % (12 h), +0,0186 % (24 h), +0,0354 % (48 h) y
+0,0519 % (72 h), positivo = paga el largo.

## Resultado

| Horizonte | Convicción | n | bruto | funding | coste | **neta** | hit | Veredicto |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 12 h | todas | 1.551 | +0,0101 % | −0,0004 % | 0,2170 % | −0,2073 % | 0,39 | **sin_edge** |
| 12 h | top | 486 | −0,0273 % | −0,0006 % | 0,1850 % | −0,2130 % | 0,33 | sin_edge |
| **24 h** | **top** | 325 | **+0,0904 %** | −0,0033 % | 0,1839 % | **−0,0968 %** | 0,42 | sin_edge |
| 24 h | todas | 990 | −0,0048 % | +0,0014 % | 0,2215 % | −0,2248 % | 0,43 | sin_edge |
| 48 h | todas | 576 | −0,1027 % | +0,0006 % | 0,2220 % | −0,3241 % | 0,43 | sin_edge |
| 48 h | top | 219 | +0,0054 % | −0,0037 % | 0,1854 % | −0,1836 % | 0,43 | no_concluyente |
| 72 h | todas | 406 | −0,3348 % | +0,0010 % | 0,2201 % | −0,5539 % | 0,43 | sin_edge |
| 72 h | top | 186 | −0,2364 % | −0,0089 % | 0,1887 % | −0,4340 % | 0,39 | no_concluyente |

`p_corregido` = 1,00000. Negativa en ambas mitades y en los regímenes en todas
las celdas con muestra suficiente. Con costes ×2, peor.

## El hallazgo: el gradiente se invierte

El bruto **crece hasta 24 h y se hunde después**: +0,09 % (24 h, top) → +0,005 %
(48 h, top) → −0,24 % (72 h, top); en `todas` el derrumbe es más temprano
(−0,0048 % a 24 h → −0,10 % a 48 h → −0,33 % a 72 h).

Es decir: **mantener la posición más tiempo no espera el movimiento, lo
devora.** El rebote que la señal predice ocurre y se agota dentro de las
primeras 24 h; a partir de ahí la posición se queda expuesta a la deriva del
mercado sin el Fuel de la señal. La palanca del horizonte no es lineal: tiene
un óptimo en 24 h y ese óptimo sigue por debajo del peaje.

Dos apuntes honestos:
- El **funding pesó mucho menos** de lo que el gate hacía temer (−0,0004 % a
  −0,0089 % de media): la mayoría de los holds atraviesan pagos cercanos a la
  tasa por defecto. No era el freno; el freno es el bruto.
- Las celdas de 48 h y 72 h en `top` se quedan en 219 y 186 operaciones: **no
  concluyente por muestra**, no "sin edge". No hay potaria para dictar sentencia
  allí, y se dice.

## Veredicto final de la búsqueda de edge

Seis hipótesis, seis refutaciones, ~10.000 operaciones independientes sobre
3,8 años:

| # | Familia / palanca | Mejor neta | Veredicto |
|---|---|---:|---|
| H1 | funding extremo → reversión | −0,09 % | sin_edge (signo opuesto) |
| H3 | rebote en el nivel, afinada | −0,0968 % | sin_edge |
| H4 | rebote, entrada rediseñada | −0,2226 % | sin_edge |
| H5 | ruptura → continuación | −0,1977 % | sin_edge |
| H6 | horizontes largos 12-72 h | −0,0968 % | sin_edge |

**El mejor bruto medido en toda la investigación es +0,0904 %, contra un peaje
de 0,18-0,23 %.** Las tres palancas disponibles (afinar la señal, rediseñar la
entrada, estirar el horizonte) están medidas y agotadas. El marco —velas de 5 m,
señal de nivel, hold 4-72 h, ejecución tomadora— **no contiene edge direccional
demostrable**.

## Qué hacer con el bot entonces

1. **No operar.** La expectativa medida es −0,10 a −0,25 % por operación, y el
   papel vivo (−0,28 % de media sobre 15 trades) lo confirma de forma
   independiente. Dos métodos, misma respuesta.
2. **Gestión, no búsqueda.** Con expectativa negativa conocida, lo que decide el
   daño es el tamaño y el tope de pérdida por operación (aquel trade de −25 R no
   debería existir en una cuenta que busque sobrevivir).
3. **Si se busca rentabilidad estructural**, la vía no es otra señal de este
   marco: es **invertir la ecuación de coste**, es decir ganar el spread en vez
   de pagarlo (providencia de liquidez). Eso es otro sistema con otros riesgos
   (inventario, hedge adverso), **no está probado aquí** y no se afirma que
   funcione; solo es la dirección que la aritmética de costes deja abierta.

## Declaración

El modelo congelado `toques-wf-1` **solo fue leído** (dirección y
`prob_modelo` del replay). Cero cambios en `vigilante/`, el gate,
`hold_model.py` y los workflows. Este informe no autoriza operar.
