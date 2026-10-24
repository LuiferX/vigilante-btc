# 🧪 Cuaderno de experimentos (pre-registro + resultados)

Regla del proyecto: **las hipótesis se registran ANTES de medir**. Cada fila del
scoreboard (`analysis/experimentos/scoreboard.jsonl`) tiene: id, fecha, hipótesis,
cambio exacto, métrica esperada, protocolo de validación, resultado observado y
decisión (conservar / revertir). Los resultados negativos se publican igual.

## Protocolo de validación (fijo, no se cambia por resultado)

1. **Replay sin mirada al futuro**: velas 5m, paso = horizonte = 48 (ventanas de
   etiquetado NO solapadas), warm-up 300 velas, contexto solo con velas ≤ corte.
   HTF cortado por bisect. Ventana de trabajo acotada a 3000 velas (la EMA200 ya
   está convergida: el efecto de la semeda es <0,0001%; verificado contra el
   replay de ventana completa).
2. **Etiqueta**: `hold_4h_0.5pct` — el nivel aguantó si ningún cierre 5m cae 0,5%
   más allá en las 48 velas siguientes. Solo niveles con **3+ toques reales en 6h**
   (el motor no inventa probabilidad sin toques).
3. **Walk-forward con embargo**: entrenar con datos estrictamente anteriores al
   fold de prueba + 24 h de embargo (288 velas 5m). Nunca se ve el futuro.
4. **Muestras efectivas**: cada decisión (4 h) es independiente; las etiquetas no
   se solapan. Se cuenta la decisión, no la fila nominal.
5. **Métricas**: Brier, Brier skill vs tasa base, ECE, PSI (vivo vs OOS), y corte
   por lado (soporte/resistencia) y por régimen (volatilidad, sesión).
6. **Criterio de éxito** (no se negocia): skill > 0 estable (racha en folds),
   PSI < 0,25, ECE ≤ 0,08, ≥ 100 muestras efectivas.

## Hipótesis registradas (antes de medir) y RESULTADOS

| ID | Hipótesis | Resultado medido | Decisión |
|---|---|---|---|
| H1 | El modelo publicado (`toques-v2-l1`) tiene skill ≈ 0 o negativa fuera de muestra | **Confirmada y peor**: negativo en los 11 folds (−0,035 a −0,169) y en el holdout de octubre (−0,054) | revertir el modelo |
| H1b | Una logística L1 re entrenada por fold walk-forward tiene skill > 0 | **Confirmada**: 11 folds / 7.757 muestras OOS, skill medio **+0,0168**, 10 de 11 folds positivos, racha de 6. Holdout octubre (nadie entrenado): **+0,0093**, ECE 0,021 | **conservar** → modelo nuevo `toques-wf-1` |
| H2 | Recalibrar SOLO el intercepto sobre el train de cada fold baja el Brier sin colapsar | **Negativa**: idéntico al H1 en los 11 folds (el fit L1 por fold ya deja el intercepto calibrado) | revertir |
| H3 | El edge está en un lado o régimen, no en el global | **Parcialmente**: soporte +0,0162 (n=3.952) y resistencia +0,0122 (n=3.805) sobreviven; **compresión +0,031** y **expansión −0,029** (n=1.085) → el modelo falla en alta volatilidad; noche −0,027 | conservar; la expansión queda documentada como límite conocido |
| H4 | Un modelo con menos features (solo ATR + dist) generaliza igual o mejor | _pendiente de medir_ | — |
| H5 | Horizonte 8 h (etiqueta pre-registrada aquí) aumenta el skill medible | _pendiente de medir_ | — |

## Modelo publicado ahora: `toques-wf-1`

- Entrenado con TODO el historial ≤ 2026-09-30 (24 h de embargo antes del holdout),
  mismo target y mismas 9 features; L1 C=0.03.
- **Coeficientes sparse**: solo sobreviven `hourc` (+0,098), `dow` (−0,190) y
  `x_atr288` (−0,207). Las features de precio (dist, atr, ema200, rng, atr48/144)
  se apagan: el aguante de un nivel con 3+ toques está dominado por la **hora,
  el día de la semana y la volatilidad de 24 h**, no por la distancia al nivel.
- **OOS octubre 2026** (132 decisiones, 198 muestras, nadie lo entrenó):
  Brier 0,1239 · base 84,85% · **skill +0,0364** · ECE 0,025 · bins monótonos
  (0,80-1,01: predice 0,85, acierta 0,873) · soporte +0,0575 · resistencia +0,0065.
- **Deriva**: PSI vivo-vs-OOS **0,157 (watch)** con el modelo nuevo (era 1,20 con
  el viejo: la distribución de probabilidades ya no está desplazada).

## Reproducir

```bash
python analysis/entrenar_hold.py --datadir <velas> --desde 2023-01-01 \
    --hasta 2026-09-30 --test-dias 90 --train-dias 365 --embargo-horas 24
python analysis/entrenar_hold.py --datadir <velas> \
    --holdout-ini 2026-10-01T00:00:00+00:00 --guardar-modelo modelo_final.json
```

Coste orientativo: ~1,3 min por fold de 90 dias con 435k velas cargadas.

## CONGELAMIENTO (toques-wf-1)

**Fecha:** 2026-10-24 · **Estado:** CONGELADO

El modelo `toques-wf-1` y su entrenador `analysis/entrenar_hold.py` quedan
congelados para que las metricas de produccion (PSI, Brier skill, ECE) tengan
una **referencia fija**: sin modelo congelado, cada metrica se resetea y deja de
ser comparable periodo a periodo. Sello: clave `congelado` en las 3 copias del
modelo (`vigilante/toques.py`, `analysis/hold_model.py`, `modelo_toques.json`).

### Des-congelar SOLO si se cumplen TODAS:

1. PSI estable < 0.25 durante 1 semana completa con este modelo en produccion.
2. >= 300 muestras efectivas nuevas posteriores a la congelacion (~5-6 semanas).
3. Hipotesis registrada en este archivo ANTES de entrenar.
4. El candidato supera a toques-wf-1 en el MISMO walk-forward (mismos folds,
   mismo embargo). No en un corte elegido a posteriori.

### Excepciones inmediatas (fuera de ese proceso):

- Bug en features o scoring (correccion > congelamiento).
- Cambio estructural en la fuente de datos que altere la semantica de features.

### Lo que "congelar" NO significa:

- NO parar de medir: el refresco OOS diario y el control WF semanal siguen
  corriendo (son el detector de decaimiento).
- NO es para siempre: los criterios de arriba se pre-registran hoy.
- Si el regimen cambia y el modelo se degrada, el gate + PSI lo silencian:
  el costo de un modelo congelado y obsoleto es "callarse", nunca "mentir".
