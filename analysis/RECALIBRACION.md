# 🔬 Recalibración — registro honesto (octubre 2026)

Este archivo existe para que **no se autoengañe nadie**. Registra los intentos de
recalibración del modelo de aguante (`hold_model.py`, `toques-v2-l1`) con su
resultado, incluyendo los negativos.

## Qué mide el modelo

Probabilidad de que un nivel con **3+ toques reales en 6 h** **no cierre 0,5% más
allá del nivel** en 4 h. No es win rate, no es señal de entrada, no ejecuta órdenes.

## Intento 1 — Recalibración Platt sobre logit (rechazada)

- **Hipótesis:** en el backtest OOS de octubre todas las bandas quedaron
  *subconfiadas* (predicho 0,85 / real 0,89). Un mapa afín `p' = σ(a·logit(p)+b)`
  entrenado en la primera mitad del OOS podría bajar el Brier.
- **Diseño honesto:** entrenado solo en la mitad A (1–12 oct), **probado** en la
  mitad B (12–22 oct). Sin tocar la otra mitad para elegir.
- **Resultado:** el ajuste óptimo fue `a=0.4, b=2.0`, que **colapsa las
  probabilidades a ~la tasa base** (0,85). El Brier empeoró en ambas mitades y el
  Brier skill se volvió muy negativo.
- **Veredicto: NO se aplica.** La calibración vigente (ECE 0,065, ≤ 0,08) ya está
  dentro del umbral; entrenar un mapa sobre ~100 muestras solo sobreajusta.
- **Consecuencia:** `hold_model.py` no se toca. Si más adelante `validation.json`
  justifique recalibrar (ECE > 0,08 con muestra suficiente), el procedimiento es:
  replays → mitades → ajuste → **reportar en la mitad no usada** → commit conjuntos.

## Intento 2 — Alertas de "rebote del nivel" (rechazada)

- **Hipótesis:** si un nivel aguanta y el precio está pegado a él, el rebote
  (alejarse del nivel) podría ser direccionalmente rentable.
- **Medición (OOS octubre, 116 eventos×nivel, plan 1:1 y 2:1 con 0,5% de riesgo):**
  acierto 25,9% (banda 0,80–0,85, n=27), 10,3% (0,85–0,90, n=29), sin casos
  suficientes por encima de 0,90. La mayoría de los casos **ni toca TP ni SL**:
  el precio se queda en el nivel.
- **Veredicto:** "el nivel aguanta" significa *no rompe*, **no** *rebota*. No se
  emite alerta direccional por rebote. El aviso de precisión publica el aguante
  (hecho medido) y deja la lectura al dueño.

## Qué sí quedó medido y publicado

| Evidencia | Resultado |
|---|---|
| OOS octubre completo (127 decisiones, 189 muestras) | Brier 0,133 · skill **+0,0019** · banda ≥0,80: **88,8% real** (n=89, IC 80,5–93,8%) |
| Mitad A (1–12 oct, 102 muestras) | skill +0,031 · banda alta 90,0% (n=60) |
| Mitad B (12–22 oct, 87 muestras) | skill −0,031 · banda alta 86,2% (n=29) |
| Ventana con datos de un día más (backfill fresco) | skill −0,014 (187 muestras) |
| Precisión direccional del motor (plan 1:1, 0,5%) | **37,3%** (n=75) |
| Precisión direccional 2:1 | 12,0% (n=75) |

**Lectura:** el skill global ronda el 0 y cambia de signo según la ventana: **no
hay edge demostrado**, y la muestra base es altísima (79–85%). Lo que el modelo
sí ofrece es calibración monótona y una banda alta medida sobre 89 casos.

*Regla del proyecto: verdad > ego. Los resultados negativos se publican igual.*
