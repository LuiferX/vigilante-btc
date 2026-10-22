# Scorecard del repo

Esta es una **auditoria interna con rubrica**, no una certificacion externa. Mide calidad de ingenieria, medicion y operacion. No mide ganancia ni promete edge predictivo.

Objetivo: **8,5/10**. Resultado de esta iteracion: **8,9/10** (ponderado 8,875). Iteracion previa: 8,7.

## Rubrica

| Dimension | Peso | Antes | Ahora | Evidencia |
|---|---:|---:|---:|---|
| Confiabilidad y cobertura de datos | 15% | 8,6 | 8,8 | fallback Bybit **etiquetado** para top-traders (Binance bloquea con 451 desde IP de EE.UU.); el validador solo se rompe por las velas (lo que usa el motor), los derivados bloqueados quedan en warnings |
| Calidad del motor de decision | 15% | 8,9 | 8,9 | sin cambios: zonas, HTF, POC, sweep, aguante, guardrail de frescura |
| Medicion y calibracion | 15% | 8,7 | 9,0 | OOS octubre completo: **189 muestras** (antes 39), ECE por bins, intervalo Wilson, banda alta separada, corte por lado, `backfill.py` (replay auditable con descarga propia) y **canal OOS** en `validation.json` |
| Tests y CI | 10% | 8,8 | 9,2 | 692 pruebas del bot (+25), +2 colector (fallback Bybit), +3 validacion (canal OOS, auxiliar bloqueado); `tools/secret_scan.py` enganchado a 2 workflows |
| Confiabilidad operativa | 10% | 8,3 | 8,7 | nuevo `oos-refresh.yml` semanal: refresca backtest OOS + validation (drift automatizado); pipeline intacto |
| Seguridad y guardrails | 10% | 9,2 | 9,3 | **guardian anti-secretos** (`tools/secret_scan.py`, falla el push con patrones de token/chat-id/API key); puerta de alertas sin cambios |
| Dashboard y UX | 10% | 8,7 | 8,7 | `/motor.html` intacto y enlazado; sin tocarlo |
| Documentacion y runbook | 5% | 9,0 | 9,0 | `analysis/RECALIBRACION.md` (intentos Positivos y negativos), `analysis/backfill.py`, corte OOS de octubre en `analysis/README.md` |
| Reproducibilidad y code quality | 5% | 8,6 | 8,6 | stdlib, sin red en tests, model card, rutas por `paths.py` |
| Validacion del modelo | 5% | 7,5 | 8,0 | 189 muestras OOS medidas con disciplina de mitades; skill **marginal e inestable** (+0,0019 mes, +0,031 / −0,031 mitades, −0,014 al sumar un dia). Sin edge demostrado; 2 experimentos negativos publicados (rebote del nivel, recalibracion Platt) |
| Señal/ruido de alertas | — | — | — | medido: 18,8 -> **5,9 alertas/dia** con la config actual (puerta + umbrales 1,5% + zonas 24h + sin footprint + movimiento unificado), sobre 9 dias reales |

## Calculo

```text
0.15*8.8 + 0.15*8.9 + 0.15*9.0 + 0.10*9.2 + 0.10*8.7
+ 0.10*9.3 + 0.10*8.7 + 0.05*9.0 + 0.05*8.6 + 0.05*8.0
= 8.875 -> 8.9/10
```

Iteracion anterior: 8,7. Original: ~7,2.

## Que se transformo en esta iteracion (noche del 21/22-10)

- **OOS de octubre completo medido de verdad**: 127 decisiones, **189 muestras**
  (antes 39). Brier 0,133, skill +0,0019, banda >=0,80 con 88,8% real (n=89).
- **Disciplina de mitades publicada**: A (1-12 oct) skill +0,031 / banda alta 90,0%;
  B (12-22 oct) skill -0,031 / banda alta 86,2%. El skill global es **inestable**:
  suma un dia mas y da -0,014. No hay edge demostrado y se dice.
- **Intento de recalibracion Platt, rechazado**: colapsa a la tasa base; ECE ya
  cumple (0,065). Documentado en `analysis/RECALIBRACION.md`.
- **Intento de alerta por rebote del nivel, rechazado**: acierto 10-26% (n=27-29).
  "Aguanta" significa *no rompe*, no *rebota*. Publicado como resultado negativo.
- **Canal OOS en `validation.json`**: el backtest purgado puede servir de evidencia
  alternativa (100+ muestras, skill>0, ECE<=0.08) pero el canal vivo puede vetar y
  la deriva debe estar controlada. Hoy la deriva esta en alerta -> la puerta sigue
  cerrada, que es lo correcto.
- **Modo PRECISION (nivel defendido)**: aviso nuevo, corto, sin plan, que publica
  la probabilidad medida y su muestra. Auto-censurado si hay deriva o no hay
  evidencia OOS; no ejecuta nada. Detras de `VIGILANTE_PRECISION` (default activo).
- **Guardian anti-secretos** (`tools/secret_scan.py`) enganchado a 2 workflows.
- **Colector**: fallback Bybit para los dos jobs de top-traders (Binance da 451 en
  IP de EE.UU.), etiquetado con su propio `source`; la validacion ya no se rompe
  por un derivado bloqueado (solo las velas son criticas).
- **`analysis/backfill.py`**: replay historico que **baja solo** el historial
  publico y construye el canal OOS; mas workflow semanal `oos-refresh.yml`.
- **Tests**: 699 del bot (+32), +2 colector, +3 validacion.
- **Depuracion de ruido**: un movimiento = un aviso (`VIGILANTE_RUIDO_UNIFICADO`).

## Por que el modelo no llega a 9

El OOS ya tiene 100+ muestras, pero el **skill no es estable**: +0,031 / -0,031
en mitades y -0,014 al mover la ventana un dia. La tasa base es 79-85%: la
calibracion es razonable y monótona, pero **no hay evidencia de edge** frente a
predecir la tasa base. La dimension Validacion del modelo se queda en 8,0 y el
repo no se autopuntua 9.

El Validation bot agrega infraestructura para no autoengañarse: descuenta el
solapamiento, mide muestras efectivas, PSI contra el backtest y estados
explicitos (`muestra_chica`/`muestra_media`/`vigilar`/`degradado`/`roto`).

## Criterio para subir a 9,0 (lo que falta, en orden)

1. **Skill positivo y estable**: skill > 0 en dos mitades consecutivas y en el
   refresco semanal, con >= 100 muestras. Requiere acumular semanas de OOS, no
   rushear el modelo (todo intento de forzarlo empeoro: ver RECALIBRACION.md).
2. **Deriva resuelta**: PSI vivo-vs-OOS por debajo de 0,25 sin bajar el umbral
   (hoy 1,20 en produccion).
3. **Top-traders: 451+403** sin fuente publica desde IPs de EEUU (documentado
   en collector/README.md); falta red no estadounidense o fuente de pago.
   Hoy esta en 0,75 (el regimen de los ultimos dias no se parece al de octubre).
3. **Cobertura real de top traders**: una fuente publica equivalente al ratio de
   top-traders (hoy solo hay proxy de Bybit, etiquetado).
4. Revision externa de la rubrica.
