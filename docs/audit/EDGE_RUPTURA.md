# EDGE_RUPTURA.md — H5: la familia de rupturas tampoco tiene edge

**Fecha:** 2026-11-01 · Pre-registro: `analysis/EXPERIMENTOS.md`, sección
"H5 — RUPTURA del nivel" (commit `2b077cdc94`, **anterior** a medir).
Código: `analysis/expr_ruptura.py` · Tests: `analysis/test_expr_ruptura.py`
(14 en verde). Datos: `analysis/data/edge_ruptura.json`

---

## La hipótesis

Tras refutar la familia "rebote" (H1/H3/H4), quedaba una con **mecánica de
movimiento**: la ruptura del nivel. En el replay, 1.778 de 11.049 muestras
(16,1 %) rompen el nivel dentro de 48 velas, y **las 1.778 tienen `y=0`**: el
modelo falló justo en esos casos. Si las rupturas son eventos de movimiento,
el lado de la continuación debería pagar el peaje.

Diseño: dirección `ruptura` = continuación (invertida respecto al modelo),
dirección `control` = la del modelo, **misma vela de entrada**, mismo universo.
Eso convierte el experimento en una comparación de sustitución limpia: mismo
evento, mismo momento, lado opuesto.

Detector validado sobre las 1.778 rupturas: primer **cierre** más allá del
nivel en 48 velas. Detecta el 100 % y todas dentro de la ventana. (Mi
definición dispara 11 velas antes que la etiqueta `barras_ruptura` del replay:
declarado y usado el mío.)

**Limitación honesta:** el universo se selecciona sabiendo que el nivel rompió.
Mide *"¿paga la continuación de una ruptura identificada al ocurrir?"*, no
*"¿puedo detectar rupturas en vivo?"*.

## Resultado

| Filtro | Dirección | Salida | n | bruto | coste | neta | hit | Veredicto |
|---|---|---|---:|---:|---:|---:|---:|---|
| todas | ruptura | h4 | 2.586 | −0,0010 % | 0,2132 % | −0,2142 % | 0,32 | **sin_edge** |
| todas | ruptura | fallo | 2.586 | +0,0115 % | 0,2132 % | −0,2017 % | 0,12 | sin_edge |
| todas | control | h4 | 2.586 | +0,0010 % | 0,2132 % | −0,2122 % | 0,36 | sin_edge |
| todas | control | fallo | 2.586 | −0,0115 % | 0,2132 % | −0,2247 % | 0,16 | sin_edge |
| extremos | ruptura | h4 | 1.592 | +0,0097 % | 0,2093 % | −0,1997 % | 0,33 | sin_edge |
| extremos | ruptura | fallo | 1.592 | +0,0116 % | 0,2093 % | −0,1977 % | 0,13 | sin_edge |
| extremos | control | h4 | 1.592 | −0,0097 % | 0,2093 % | −0,2190 % | 0,34 | sin_edge |
| extremos | control | fallo | 1.592 | −0,0116 % | 0,2093 % | −0,2209 % | 0,15 | sin_edge |

Informativo (fuera de las 8 celdas, sin Bonferroni):

| Celda | n | neta | bruto | IC95 |
|---|---:|---:|---:|---|
| `expansion` sola · ruptura · h4 | 503 | **−0,2793 %** | −0,0226 % | [−0,3776, −0,1793] |
| todas · ruptura · TP1/SL0,5 | 2.586 | −0,2119 % | +0,0013 % | [−0,2330, −0,1910] |
| todas · control · TP1/SL0,5 | 2.586 | −0,2066 % | +0,0066 % | [−0,2272, −0,1857] |

`p_corregido` = 1,00000. Negativa en ambas mitades y en los regímenes en las 8
celdas. Con costes ×2, peor.

## Los dos hallazgos que importan

1. **`ruptura` y `control` son espejos exactos** (+0,0010 % frente a −0,0010 %
   a 4 h). El movimiento de precio tras la ruptura es cero en ambas
   direcciones: la ruptura es un evento **de nivel**, no de precio. Romper una
   línea no empuja el mercado en las siguientes 4 horas.
2. **La apuesta específica (`expansion`) es la peor celda del experimento**:
   −0,2793 % con el coste más alto (0,2567 %, porque entra con ATR más alto) y
   el bruto más negativo. No es que no ayude: el régimen de expansión empeora
   la ecuación porque sube el peaje más de lo que sube el movimiento.

## Balance de la búsqueda (5 hipótesis, 5 refutaciones)

| # | Familia | n medida | Mejor bruto | Veredicto |
|---|---|---:|---:|---|
| H1 | funding extremo → reversión | 416 | ~0 | sin_edge, y de signo opuesto |
| H3 | rebote en el nivel, afinada | 2.513 | +0,090 % | sin_edge |
| H4 | rebote, entrada rediseñada (4 variantes) | 2.513 | +0,024 % | sin_edge; la mejora es de tiempo |
| H5 | ruptura → continuación | 2.586 | +0,012 % | sin_edge; `expansion` la peor |

**~10.000 operaciones independientes medidas y ninguna familia produce bruto
por encima de 0,09 % con un peaje de 0,21 %.** El patrón es demasiado
consistente para ser ruido: el cuello de botella es la relación
movimiento/coste de este marco (velas de 5 min, hold de 4 h), no la elección de
señal.

## Qué implica para el bot

Con este coste, operar exige bruto ≥0,5 % por viaje. De las mediciones, solo el
**horizonte largo** empuja en esa dirección (el bruto de H3 crecía con el hold:
+0,02 % a 4 h → +0,10 % a 24 h, y la mejor celda global fue 24 h con alta
convicción). Aun así, insuficiente. Los siguientes pasos honestos son:

1. **Horizontes largos (12-72 h)** con el coste fijo: es la única variable que
   ha mostrado gradiente a favor en los datos medidos.
2. **Gestión de riesgo y coste** como palanca realista: con expectativa
   −0,20 % por operación, decidir *cuánto* se arriesga es la diferencia entre
   perder despacio y quebrar.
3. **No invertir más en variantes de esta familia**: los datos la han cerrado.

## Declaración

El modelo congelado `toques-wf-1` **no se tocó**: se usó únicamente para
definir el universo y como dirección del `control`. Cero cambios en
`vigilante/`, el gate, `hold_model.py` y los workflows. Este informe no
autoriza operar.
