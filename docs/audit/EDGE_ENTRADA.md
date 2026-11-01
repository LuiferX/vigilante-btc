# EDGE_ENTRADA.md — H4: rediseñar la entrada no arregla el edge

**Fecha:** 2026-11-01 · Pre-registro: `analysis/EXPERIMENTOS.md`, sección
"H4 — rediseño de la ENTRADA" (commit `114e3f5d46`, **anterior** a medir).
Código: `analysis/expr_entrada.py` · Tests: `analysis/test_expr_entrada.py`
(12 en verde: cero look-ahead en las 4 variantes, costes, cooldown, bootstrap).
Datos: `analysis/data/edge_entrada.json`

---

## La hipótesis

En H3 medí que, tras el toque del nivel, el precio se va **0,787 % en contra
(mae)** antes de moverse **0,056 % a favor (mfe)**. Si el latigazo adverso es
el problema, entrar *después* de la confirmación debería mejorar la entrada sin
cambiar la dirección del modelo. La dirección (`soporte`→largo,
`resistencia`→corto) y el modelo congelado se mantienen **intactos**: solo
cambia el momento.

Cuatro entradas, con un **control de tiempo** para no confundir información con
simple retardo:

| Variante | Regla |
|---|---|
| `base` | open de la vela siguiente a `t` (referencia H3) |
| `retardo` | open de la vela siguiente a `t+2` velas (**control**: +10 min, sin condición) |
| `confirm` | cuando un cierre queda ≥0,3 % del lado favorable del nivel; entra al open siguiente |
| `barrido` | cuando una vela perfora el nivel ≥0,2 % **y** otra lo recupera; entra al open siguiente |

Ventana de espera máxima 24 velas. 8 celdas (4 entradas × 2 salidas),
Bonferroni α = 0,00625, bootstrap 10.000 semilla 42.

## Resultado

| Entrada | Salida | n | bruto | coste | **neta** | hit | Veredicto |
|---|---|---:|---:|---:|---:|---:|---|
| base | h4 | 2.513 | −0,0252 % | 0,2206 % | −0,2458 % | 0,31 | **sin_edge** |
| retardo | h4 | 2.513 | −0,0200 % | 0,2221 % | −0,2421 % | 0,31 | sin_edge |
| confirm | h4 | 2.396 | −0,0133 % | 0,2237 % | −0,2370 % | 0,32 | sin_edge |
| **barrido** | h4 | 728 | **+0,0240 %** | **0,2466 %** | **−0,2226 %** | 0,38 | sin_edge |
| base | gest | 2.513 | −0,0076 % | 0,2206 % | −0,2282 % | 0,33 | sin_edge |
| retardo | gest | 2.513 | −0,0046 % | 0,2221 % | −0,2267 % | 0,33 | sin_edge |
| confirm | gest | 2.396 | −0,0021 % | 0,2237 % | −0,2259 % | 0,35 | sin_edge |
| barrido | gest | 728 | −0,0029 % | 0,2466 % | −0,2495 % | 0,36 | sin_edge |

`p_corregido` = 1,00000. Negativa en las dos mitades y en los regímenes de
volatilidad en las 8 celdas. Con costes ×2, peor. Ninguna pasa ninguno de los
7 criterios de muerte.

## Por qué este negativo vale más que un positivo dudoso

1. **El control de tiempo se come la mejora.** De `base` a `retardo` la neta
   mejora +0,0037 %; de `retardo` a `confirm` solo +0,0051 % más. La
   confirmación aporta información marginal sobre *simplemente esperar diez
   minutos*. La hipótesis "entrar tras confirmar" queda refutada por su propio
   control — que es justo para lo que se diseñó.
2. **La amplitud total es ruido.** Las 8 celdas van de −0,2226 % a −0,2495 %:
   0,03 % de dispersión sobre expectativas de −0,24 %. Todas las variantes son
   la misma medición con distinto muestreo.
3. **El `barrido` tiene el mejor bruto (+0,024 %) y el peor coste (0,2466 %)**:
   entra más tarde, con ATR más alto, habiendo descartado el 71 % de las
   señales. Compra bruto con coste. Sigue perdiendo.
4. **La asimetría mae/mfe no era explotable por timing.** Medido: el problema
   no es *cuándo* entras, es que la señal no mueve el precio.

## Consecuencia para el proyecto

Tres hipótesis de edge probadas y las tres refutadas con datos:

| Hipótesis | Resultado |
|---|---|
| H1 — funding extremo → reversión | sin_edge, y de signo opuesto |
| H3 — señal del modelo afinada (convición, horizonte, salida) | bruto ~0; neta −0,20 a −0,25 % |
| H4 — rediseño de la entrada (4 variantes con control) | sin_edge; la mejora es de tiempo, no de información |

El patrón es consistente: **esta familia de señales no genera movimiento
suficiente para pagar 0,2 % de viaje.** Cuando el bruto medido es 0,000-0,024 %
y el peaje 0,18-0,25 %, no hay ajuste de entrada, filtro de convicción ni
horizonte que lo arregle. Buscar edge aquí ha costado tres experimentos y ha
quedado cerrado con evidencia, no con opinión.

Lo que queda abierto, honestamente:
- **Otra familia de señales** donde el bruto sea ≥0,5 % por viaje (rupturas con
  expansión, tendencia, cascadas si se archivan datos).
- **Gestión de riesgo y coste** como única palanca realista a corto plazo: con
  expectativa −0,24 % por operación, la pregunta no es "cómo ganar más" sino
  "cuánto se pierde y a qué velocidad".

## Declaración

El modelo congelado `toques-wf-1` **solo fue leído** (dirección y
`prob_modelo` del replay). Cero cambios en `vigilante/`, el gate,
`hold_model.py` y los workflows. Este informe no autoriza operar.
