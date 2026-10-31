# EDGE_REPORT.md — Resultado de H1 (funding extremo → reversión)

**Fecha:** 2026-10-31 · Pre-registro: `analysis/EXPERIMENTOS.md` (commit
`94d9689a78`, **anterior** a cualquier resultado) · Gate: `EDGE_DATA.md`
Implementación: `analysis/expr_edge.py` · Tests: `analysis/test_expr_edge.py`
Datos: `analysis/data/edge_funding.json`, `edge_liq.json`

---

## 1. Tabla resumen

| Variante | Horizonte | n indep. | Expectativa neta | IC95% | Hit rate | Veredicto |
|---|---|---:|---:|---|---:|---|
| A24h (603ª) | 4h | 282 | −0,2216 % | [−0,3283, −0,1105] | 0,35 | **no concluyente** (n<300) |
| A24h | 8h | 282 | −0,2487 % | [−0,4142, −0,0862] | 0,35 | no concluyente (n<300) |
| A24h | 12h | 282 | −0,2632 % | [−0,4522, −0,0676] | 0,38 | no concluyente (n<300) |
| A24h | 24h | 282 | −0,1431 % | [−0,4473, +0,1690] | 0,45 | no concluyente (n<300) |
| **B8h** | 4h | **416** | **−0,2145 %** | **[−0,3111, −0,1167]** | 0,34 | **sin_edge** |
| **B8h** | 8h | **416** | **−0,1877 %** | **[−0,3290, −0,0437]** | 0,37 | **sin_edge** |
| **B8h** | 12h | **416** | −0,1757 % | [−0,3467, +0,0034] | 0,39 | **sin_edge** |
| **B8h** | 24h | **416** | −0,1205 % | [−0,3767, +0,1321] | 0,45 | **sin_edge** |

Unidades: % por operación (no se definió stop; 1 operación = 1 unidad de R).
`p_corregido` (Bonferroni, 8 celdas) = **1,00000**. Todas las celdas evaluables
tienen expectativa negativa; ninguna tiene el IC95 inferior > 0; **ninguna es
positiva en las dos mitades**; **ninguna es positiva en los dos regímenes de
volatilidad**; con costes ×2 todas empeoran (−0,35 % a −0,49 %).

## 2. Por qué falló (desglose bruto / funding / coste)

| Celda (B8h) | Bruto | Funding | Coste | Neto |
|---|---:|---:|---:|---:|
| 4h | +0,0193 % | +0,0000 % | 0,2338 % | −0,2145 % |
| 8h | +0,0413 % | +0,0048 % | 0,2338 % | −0,1877 % |
| 12h | +0,0532 % | +0,0048 % | 0,2338 % | −0,1757 % |
| 24h | +0,1006 % | +0,0127 % | 0,2338 % | −0,1205 % |

El diagnóstico es limpio y no deja espacio a interpretaciones benévolas:

- **El efecto bruto existe pero es pequeño y crece con el horizonte**: de
  +0,02 % a 4 h a +0,10 % a 24 h. No es ruido puro, pero tampoco es dinero.
- **El coste es 2,3× el mejor bruto observado** (0,2338 % frente a +0,1006 %).
  El edge desaparece con costes; de hecho nunca llega a alcanzarlos.
- **El funding apenas compensa** (+0,0000 a +0,0127 %): los regímenes extremos
  duran poco y la posición solo cobra 0-3 pagos.
- **El hit rate (0,34-0,45) está por debajo de 0,5**: la operación de reversión
  pierde más veces de las que gana. El signo del sesgo indica que, tras un
  funding extremo, el precio tiende a **continuar** en la dirección del lado
  cargado, no a revertir. Es decir, la hipótesis no solo no tiene edge: el
  efecto parece de signo opuesto al propuesto.
- **Estabilidad temporal nula**: la única celda con primera mitad positiva
  (24 h: +0,1276 %) tiene la segunda mitad en −0,3687 %.
- Curva de equidad de referencia (B8h, 4 h): −89,2 % acumulado sobre 416
  operaciones, drawdown máximo 93,7 %. Como sanity check, es una ruina.

## 3. Corrección declarada (y por qué no es pesca de resultados)

El primer corte dió 603 eventos en A24h y 1.153 en B8h. **Los tests
unitarios destaparon un error de implementación**: la comparación era
`funding >= p95`, y el **27,1 % de los registros de funding de BTCUSDT son
exactamente +0,0001** (la tasa por defecto de Binance), de modo que el p95 de
la ventana trailing empataba con el default y la señal disparaba en el
**16,6 % de las 4.169 ventanas** sobre eventos que no eran extremos en absoluto.

Corregido a comparación **estricta** (un valor que está *en* el percentil no
está *fuera* de él). Declaro explícitamente:

- Es un cambio **posterior** a ver el primer número.
- Su motivación fue un **fallo de test**, no el resultado.
- El cambio vuelve la prueba **más estricta**, no más laxa: baja la muestra de
  603 → 282 eventos en A24h y **deja la variante canónica por debajo del gate
  de 300 eventos** (de ahí los `no_concluyente` de la tabla, no unos
  `sin_edge` cómodos). El veredicto final no mejora por el cambio: empeora la
  capacidad de demostrar edge.
- Queda fijado con test de regresión
  (`test_empate_con_el_default_no_dispara`).

## 4. H2 — cascada de liquidación

**No concluyente por falta de datos.** La API de Binance limita el histórico de
`openInterestHist` y `takerlongshortRatio` a **exactamente 30 días** (probado:
`startTime` de 31 días → HTTP 400; de 30 días → OK). Con 720 barras de 1 h y una
regla que exige OI en p5 de ventana trailing **y** taker sell en p95, los eventos
independientes no llegan a 300. No se sustituyó el proxy por otro "parecido":
la misión fijó la regla. Detalle en `EDGE_DATA.md`.

## 5. Veredicto final

**H1 (funding extremo → reversión): no hay edge en estos datos; no operar.**

Celebro la predicción del pre-registro ("espero sin_edge o neto dudoso"): se
cumplió. Las 4 celdas con muestra suficiente dan expectativa negativa, IC95 que
no supera cero por abajo, inestabilidad entre mitades y regímenes, y fracaso
con costes ×2.

## 6. Qué probaría después (propuestas, NO medidas aquí)

1. **Continuación en vez de reversión** — el hit rate < 0,5 sugiere signo
   opuesto. Sería una hipótesis nueva, con su propio pre-registro; **no** es un
   resultado de este informe. Aviso: por simetría aproximada de retornos, si la
   reversión bruta a 24 h fue +0,10 %, la continuación bruta andaría cerca de
   −0,10 %, así que tampoco canta.
2. **Horizontes más largos** (48-72 h): el bruto crece con el horizonte
   (+0,10 % a 24 h) y el coste es fijo; el punto de cruce estaría lejos, pero es
   la única dirección donde el bruto se mueve a favor.
3. **Condicionar por régimen de OI real** (no por ATR): imposible con el tope de
   30 días de la API, salvo acumulando datos desde hoy y re-testando en ≥ 6 meses.
4. **Costes menores**: pasar a maker (0,02 %) abarataría el viaje a ~0,17 %; aun
   así seguiría por encima del mejor bruto (+0,10 %).

## 7. Declaración

**El modelo de producción no se tocó.** Cero cambios en `vigilante/`,
`precision.py`, `decision_engine.py`, `hold_model.py`, el gate y los workflows.
Todo el trabajo vive en `analysis/` (investigación aislada y auditable) y en
`docs/audit/`. `expr_edge.py` solo **lee** la cache de klines/funding; no
ejecuta órdenes ni escribe en los caminos de producción.
