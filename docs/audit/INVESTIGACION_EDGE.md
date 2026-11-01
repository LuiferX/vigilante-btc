# Investigación de edge — veredicto consolidado

**REARME 2026-11-01.** Este archivo sustituye a los seis informes por experimento
(`EDGE_DATA`, `EDGE_REPORT`, `EDGE_TOQUES`, `EDGE_ENTRADA`, `EDGE_RUPTURA`,
`EDGE_HORIZONTES`), que quedaron en el historial de git. Todo lo que importa está
aquí y en `analysis/EXPERIMENTOS.md`; los datos crudos en `analysis/data/`.

## La pregunta que se hizo

¿Tiene esta familia de señales (niveles 5 m, hold 4-72 h) una expectativa **neta
de coste** positiva? El coste de referencia medido: **0,14-0,23 % por viaje**
(fee taker 0,05 %×2 + slippage). Si el bruto no lo supera, no hay edge.

## Cómo se midió

Mismo protocolo en los seis experimentos: pre-registro **antes** de mirar
resultados, entrada al open de la vela siguiente (cero look-ahead), costes
siempre, un trade a la vez con cooldown (independencia real), bootstrap 10.000
con semilla fija, corrección Bonferroni por número de celdas, y **criterio de
muerte de 7 puntos** que hay que pasar entero.

## Veredicto: seis hipótesis, seis refutaciones

| # | Familia / palanca | Muestra | Mejor bruto | Mejor neta | Veredicto |
|---|---|---:|---:|---:|---|
| H1 | funding extremo → reversión | 416 | ~0 | −0,09 % | sin_edge (sesgo de signo opuesto) |
| H3 | rebote en el nivel, afinada | 2.513 | +0,090 % | −0,0968 % | sin_edge |
| H4 | rebote, entrada rediseñada (4 variantes) | 2.513 | +0,024 % | −0,2226 % | sin_edge |
| H5 | ruptura → continuación | 2.586 | +0,012 % | −0,1977 % | sin_edge |
| H6 | horizontes largos 12-72 h | 990 | +0,090 % | −0,0968 % | sin_edge |
| — | **H2 cascadas de liquidación** | — | — | — | **no concluyente** |

Detalle completo por celda (n, IC95, hit rate, mitades, regímenes, costes ×2) en
`analysis/EXPERIMENTOS.md`, secciones H1 a H6.

## Lo que se aprendió (y por qué esto vale)

1. **El mejor bruto medido en toda la investigación es +0,0904 %**, contra un
   peaje de 0,18-0,23 %. Aparece una sola vez: 24 h de hold con alta convicción.
   El bruto no llega a pagar el viaje ni en su mejor momento.
2. **El gradiente del horizonte se invierte a partir de 24 h.** Estirar la
   posición más tiempo no espera el movimiento: lo devora (−0,10 % a 48 h,
   −0,33 % a 72 h).
3. **La mejora por rediseñar la entrada fue de tiempo, no de información.** El
   control de retardo absorbe +0,0037 % de la +0,0088 % total: la confirmación
   no aporta lo que no dé simplemente esperar.
4. **Una ruptura no empuja el precio.** El lado continuación y el lado rebote
   dieron espejos exactos (±0,002 % a 4 h): la ruptura es un evento de nivel,
   no de precio.
5. **El régimen de expansión fue la peor celda**, no la mejor: el ATR alto sube
   el peaje más de lo que sube el movimiento.
6. **Validación independiente:** el papel vivo midió −0,28 % por operación y el
   replay histórico −0,25 %. Dos caminos distintos, la misma respuesta.

## H2, el que no se pudo medir

Las cascadas de liquidación necesitan histórico de OI y taker, y la API pública
de Binance **solo sirve 30 días** (probado: `startTime` de 31 días → HTTP 400).
Con 720 barras no se alcanzan las 300 muestras que exige el criterio. Veredicto
honesto: **no concluyente por falta de datos**, y desde 2026-11-01 el repo
archiva esa microestructura a diario (`analysis/archivo_micro.py`), así que en
12 meses la pregunta se puede volver a hacer con datos.

## Consecuencia

La capa de operación se retiró del sistema (ver `ARCHITECTURE.md`). El valor del
repo está en el análisis: percentiles causales, estructura, excursion medida y
este registro honesto de lo que **no** funciona.

## Dónde están los datos

| Hipótesis | Datos | Código |
|---|---|---|
| H1 | `analysis/data/edge_funding.json` | `analysis/expr_edge.py` |
| H3 | `analysis/data/edge_toques.json` | `analysis/test_expr_toques.py` |
| H4 | `analysis/data/edge_entrada.json` | `analysis/expr_entrada.py` |
| H5 | `analysis/data/edge_ruptura.json` | `analysis/expr_ruptura.py` |
| H6 | `analysis/data/edge_horizontes.json` | `analysis/expr_horizontes.py` |

Declaración final: en ningún experimento se modificó el modelo de producción ni
el gate; la familia H1/H5 es además independiente del modelo.
