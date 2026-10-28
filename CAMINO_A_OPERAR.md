# CAMINO_A_OPERAR.md — de la medición al dinero, con las cuentas a la vista

Este documento existe para responder **una** pregunta sin adornos: ¿qué tiene
que ser cierto antes de arriesgar dinero real con este bot? Nada de fe: cada
línea tiene su medidor y su test.

## Dónde está el bot hoy (medido, no prometido)

| Indicador | Valor | Qué significa |
|---|---|---|
| Skill OOS validada | +2.7% (n=235 efectivas) | el modelo reduce el error un 2.7% vs la tasa base |
| Calibración OOS | ECE 0.012 | cuando dice 85%, pasa el ~85%: no miente |
| Ventana viva | n≈67, skill −1.9%, **calibración 0.029** | aún corta; la calibración ya es sana |
| Deriva (PSI) | 0.057 ok | el régimen volvió a la normalidad tras el finde |
| Gate de alertas | ABIERTO (canal OOS) | las direccionales salen con evidencia |
| Paper trading | corre **con comisiones** desde hoy | su equity ya es comparable con dinero real |

## La cuenta que decide todo (analysis/cost_model.py)

Marco del trade = el movimiento que define la operación. Con comisión taker de
ida y vuelta (0.10%) y slippage 0.02%/lado:

| Marco | Coste en R | Acierto mínimo para no perder | Con colchón x2 |
|---|---|---|---|
| 0.25% | 0.56R | 78% | **106% → inviable** |
| 0.50% (target del bot) | 0.28R | 64% | 78% |
| 1.00% | 0.14R | 57% | 64% |
| 2.00% | 0.07R | 54% | 57% |

Y el dato que cambia decisiones: **en una operación típica (1% de riesgo), la
comisión se come el 10% del riesgo** — una quinta parte del marco de 0.5%.
Una ventaja marginal no sobrevive a eso; una ventaja medida, sí.

## Las 5 puertas antes de dinero real (en orden)

1. **Evidencia viva suficiente** — n ≥ 100-300 operaciones efectivas, skill
   positiva y estable, confirmada por el juez PBO (no por una racha).
   *Hoy: n≈67. Faltan ~2-5 semanas de calendario, no de código.*
2. **Edge neto de costos** — la curva del papel (ya con comisiones) positiva
   sobre ≥50 operaciones, con R-medio y drawdown medidos
   (`analysis/paper_report.py`).
3. **Calibración que aguanta regímenes** — ECE ≤ 0.05 sostenido, con el PSI en
   ok/watch; si el gate se cierra, el bot se calla (así funciona).
4. **Metodología validada, no anécdota** — entrada/salida/tamaño definidos por
   regla, medidos en papel con estadística (Sharpe por operación, R-total),
   no por "estuvo buena la semana".
5. **Factor humano** — el bot es solo-lectura por diseño (`guardia_lectura`
   fail-closed). Quien ejecuta sos vos; la primera escala es micro-tamaño y
   crece solo si 1-4 siguen verdes.

## Lo que jamás cambia (el porqué de este proyecto)

- **El bot no ejecuta órdenes**: si le configurás claves de trading, se niega
  a arrancar. No es una limitación accidental.
- **El modelo campeón está congelado** hasta cumplir 4 criterios
  (analysis/EXPERIMENTOS.md): nadie lo mueve por corazonada.
- **Los negativos se publican**: las corridas que no ganaron están en el
  scoreboard. Por eso los positivos significan algo.

## La escala, completa

```
hoy:     papel neto (sin dinero) ──────────────► n crece ~6/día
puerta 1-4 verdes (~5-6 semanas si el régimen colabora)
después: micro-tamaño real ── si 1-4 siguen verdes 90 días ──► escala
```

*Este archivo se actualiza con los medidores reales. Si una puerta se cierra,
se dice. La honestidad es la única ventaja que no se puede copiar.*
