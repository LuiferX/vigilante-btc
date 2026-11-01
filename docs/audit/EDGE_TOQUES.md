# EDGE_TOQUES.md — H3: ¿la señal del modelo congelado gana dinero?

**Fecha:** 2026-11-01 · Pre-registro: `analysis/EXPERIMENTOS.md`, sección
"H3 — expectativa NETA del signal toques" (commiteado **antes** de medir).
Código: `analysis/expr_toques.py` · Tests: `analysis/test_expr_toques.py`
(12 en verde: cero look-ahead, costes, cooldown/independencia, bootstrap).
Datos: `analysis/data/edge_toques.json`

---

## Por qué este experimento

El modelo `toques-wf-1` solo se había evaluado en **calidad de predicción**
(Brier, skill, ECE): está bien calibrado y tiene skill positiva. **Nunca en
dinero.** Como el coste de un viaje es 0,14-0,23 %, un modelo puede tener
skill y aun así perder en cada operación. El papel (−28,07 R en 15 trades) ya
lo sugería; aquí se mide con potencia estadística.

## Método

Replay de **11.049 muestras** (2023-01 → 2026-09, 3,8 años) del modelo
congelado. Entrada al open de la vela siguiente al toque; dirección por
`soporte`/`resistencia`; coste 0,05 % fee ×2 + 0,02 % slippage ×2 +
0,25 × ATR % ×2. **Un trade a la vez con cooldown de 4 h** (independencia
real, no velas solapadas): de 11.049 muestras salen 2.513 operaciones
independientes. 6 celdas pre-registradas (3 salidas × 2 convicciones),
Bonferroni α = 0,00833, bootstrap 10.000 semilla 42.

## Resultado

| Salida | Convicción | n | bruto | coste | neta | IC95 % | hit | Veredicto |
|---|---|---:|---:|---:|---:|---|---:|---|
| cierre 4 h | todas | 2.513 | −0,0252 % | 0,2206 % | **−0,2458 %** | [−0,2816, −0,2089] | 0,31 | **sin_edge** |
| cierre 4 h | top P | 660 | −0,0215 % | 0,1828 % | −0,2043 % | [−0,2441, −0,1655] | 0,26 | sin_edge |
| TP 0,5/SL 0,3 | todas | 2.513 | −0,0076 % | 0,2206 % | −0,2282 % | [−0,2421, −0,2137] | 0,33 | sin_edge |
| TP 0,5/SL 0,3 | top P | 660 | +0,0012 % | 0,1828 % | −0,1816 % | [−0,2055, −0,1572] | 0,28 | sin_edge |
| cierre 24 h | todas | 990 | −0,0048 % | 0,2215 % | −0,2262 % | [−0,3776, −0,0742] | 0,43 | sin_edge |
| cierre 24 h | top P | 325 | +0,0904 % | 0,1839 % | **−0,0935 %** | [−0,2790, +0,0884] | 0,42 | sin_edge |

`p_corregido` = **1,00000**. Negativa en las dos mitades y en los tres
regímenes de volatilidad en las 6 celdas. Con costes ×2, peor. Curva de
equidad de la celda principal: −617 % acumulada sobre 2.513 operaciones.

## Validación independiente (lo que le da valor al número)

El **papel vivo** reporta −2,78 USDT medios por operación sobre banco ≈ 1.000,
es decir **−0,28 %**, y este replay mide **−0,25 %**. Dos sistemas
independientes (histórico 2023-2026 vs vivo de las últimas semanas) coinciden
en la magnitud: **el resultado no es un artefacto del backtest**.

## Diagnóstico honesto

1. **El bruto es aproximadamente cero**, no "pequeño": −0,025 % a +0,090 %.
   La llamada de dirección del modelo no genera movimiento de precio
   suficiente. La mejor celda (24 h, convicción alta) llega a +0,09 % bruto
   frente a 0,18 % de coste: la mitad del peaje.
2. **El 84 % de acierto no es dinero.** El modelo acierta si *el nivel aguanta
   4 h*; la operación resultante acierta solo el 26-43 % de las veces. Son dos
   targets distintos y el monetizable es el segundo.
3. **La entrada es el problema, no la dirección.** El `mae_pct` mediano del
   replay es 0,787 % frente a un `mfe_pct` mediano de 0,056 %: el precio
   normalmente va 0,8 % en contra antes de moverse a favor. Cualquier stop
   razonable (0,3-0,5 %) se come la operación, y por eso la salida gestionada
   sale igual o peor que la de horizonte.
4. **No se puede afinar lo que no tiene bruto.** Subir la convicción mejora
   −0,20 % → −0,18 %; no cambia de signo.

## Qué se desprende para "mejorar el edge"

- **Afinar esta familia de señales no produce edge**: medido, no opinado.
- El edge tendría que venir de una familia con **movimiento real** (rupturas
  con expansión, cascadas, tendencia), donde el bruto sea ≥ 0,5 % por viaje.
- O de **abarajar el coste** por debajo de ~0,09 %: imposible (incluso maker
  deja ~0,16 % en esta modelización).
- **Riesgo**: un modelo de expectativa −0,25 % por operación convierte
  cualquier apalancamiento en ruina; de ahí que el tope de pérdida por
  operación sea prioritario mientras se busque otra familia.

## Declaración

El modelo congelado `toques-wf-1` **solo fue leído**: se usó el
`prob_modelo` ya registrado en el replay. Cero cambios en `vigilante/`, el
gate, `hold_model.py` y los workflows. Este documento no autoriza operar.
