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

## Candidatos al próximo modelo (pre-registro 2026-10-26)

Contexto que motiva estos experimentos (observado, no supuesto): ventana viva
del 24-25/10 con el modelo colapsado a un solo bin de probabilidad (0.80-1.01),
skill viva negativa (-4.6% a -6.8%, n=45-54) y calibracion 0.0596 > 0.05,
mientras el OOS congelado seguia positivo (+2.6% a +2.8%, n=225). El modelo
tiene UNA feature sensible al mercado (volatilidad 24h) y por eso, en
compresion de volatilidad, colapsa a la tasa base.

Protocolo común a TODOS: mismo replay sin mirada al futuro, mismos 11 folds
temporales, mismo embargo de 24 h, mismas features de evento; se compara
contra `toques-wf-1` (coeficientes actuales) en los MISMOS folds. Un
candidato solo es candidato si gana en el MISMO protocolo, no en un corte
elegido a posteriori. Sin datos nuevos hasta E5.

- **E1 · Modelo con estado de regimen.** Hipotesis: condicionar por regimen de
  volatilidad (cuantiles de ATR, 3 estados) evita el colapso a la tasa base y
  recupera senal en calma. Cambio exacto: coeficientes por regimen en vez de
  coeficientes globales; estado "sin senal" explicito cuando todos los regimenes
  coinciden con la tasa base. Metrica esperada: Brier >= actual en fold calmo;
  skill_medio WF > 0.0168 (actual) sin empeorar ningun fold mas de 0.005.
- **E2 · Target graduado.** Hipotesis: el target binario hold_4h_0.5pct esta
  dominado por la tasa base (85%); predecir recorrido (distancia de ruptura,
  regresion cuantil) o MFE/MAE asimetrico tiene mas informacion por evento.
  Metrica esperada: skill > 0.0168 en el mismo protocolo, con ECE <= 0.05.
- **E3 · Recalibracion rodante.** Hipotesis: el Platt-lite estatico envejece
  con el regimen (nuestra calibracion viva 0.0596). Recalibrar intercepto por
  ventana rodante deberia sostener ECE <= 0.05 incluso con deriva.
  Metrica esperada: ECE viva <= 0.05 sostenido; si la skill no mejora, se
  conserva igual por la honestidad de las probabilidades.
- **E4 · Logistica con interacciones.** Hipotesis: L1 poda las interacciones
  hora x volatilidad y dia x regimen; anadirlas a mano (mismo modelo lineal)
  deberia capturarlas sin cambiar la clase de modelo. Metrica: idem E1.
- **E5 · Datos nuevos (solo si E1-E4 se estancan).** CVD/flujo a 1m, basis de
  funding, skew de opciones. La literatura (OFI, RAML) dice que el edge
  documentado grande vive ahi; pero decae con el horizonte, asi que en 4h se
  espera contexto de defensa de nivel, no senal independiente.

### E2 (corrida 2) · triple-barrier + PBO como juez — pre-registro 2026-10-27

Base bibliografica: triple-barrier method (Lopez de Prado) con **barreras
calibradas a los datos, no fijas** (arXiv 2504.02249: ajustan barrera/ventana
para balancear etiquetas; arXiv 2411.12753: triple-barrier + frac-diff mejora
retorno ajustado por riesgo en BTC/ETH); validacion de resultados con PBO /
deflated Sharpe (finlab-ml, sommersut/crypto-triple-barrier-lgbm).

- **E2a · barrera escalada por ATR.** Hipotesis: la barrera fija de 0.5% es
  arbitraria para un mercado cuya volatilidad cambia de regimen; recalibrarla
  como k*ATR (k ajustado sobre train) deberia dar mas informacion por evento.
  Cambio exacto: y_atr = 1 si el precio NO cierra k*ATR mas alla del nivel
  (lado perdedor) dentro de las 48 velas. Metrica: skill del modelo sobre su
  PROPIO target (base rate propia), mas frecuencia de eventos informativos
  (timeouts excluidos del ruido).
- **Juez PBO / degradacion de ranking.** Con la matriz fold x candidato,
  enumerar TODAS las particiones C(11,5) de los folds en mitades IS/OOS
  (CSCV): registrar cuan a menudo el mejor IS no es el mejor OOS. Un
  candidato "gana" solo si su skill supera al campeon en IS **y** OOS de
  forma consistente; si no, se publica el negativo.
- **Aviso metodologico (pre-registrado a proposito):** comparar skill entre
  targets distintos NO es directo; E2 se juzga por (a) su propia skill vs su
  propia base, (b) la degradacion IS->OOS vs el campeon, (c) la tasa de
  timeouts (eventos sin respuesta = ruido que el binario actual contaba como
  acierto). Publicar solo si gana en las tres.

Resultados -> `analysis/experimentos/scoreboard.jsonl` (una fila por
experimento, con resultado observado y decision conservar/revertir, incluyendo
los negativos). Ningun candidato se publica hasta cumplir los 4 criterios de
des-congelamiento de arriba.

### Resultados de la corrida 1 (2026-10-26, pre-registro cumplido)

Protocolo: replay extendido sin mirada al futuro (selftest verificado contra
`entrenar_hold.replay`: etiquetas/features/probs identicas), 11.049 muestras
2023-01->2026-09, 11 folds WF (test 90d, train 365d, embargo 24h).

| candidato | skill medio | peor fold | folds+ | ECE |
|---|---|---|---|---|
| baseline (toques-wf-1 congelado) | +0.0247 | +0.0038 | 11/11 | 0.028 |
| C0 re-entrenado (control) | +0.0286 | +0.0124 | 11/11 | 0.026 |
| E1 regimen de volatilidad | +0.0243 | +0.0041 | 11/11 | 0.025 |
| E3 recalibracion rodante | +0.0284 | +0.0108 | 11/11 | 0.028 |
| E4 interacciones | +0.0285 | +0.0123 | 11/11 | 0.025 |

Skill por regimen (OOS agrupado): el congelado gana en COMPRESION
(+0.0416 vs +0.0314 de E1), que era justo el modo de fallo que motivaba E1.

**Conclusiones (negativas publicadas, como manda la regla):**

1. **E1 RECHAZADO**: condicionar por regimen no mejora; el colapso de
   octubre NO existia en el historico 2023-2026 (skill en compresion era la
   mas alta). La degradacion viva de octubre viene de un cambio de regimen
   que el backtest no reproduce, no de un defecto del modelo.
2. **C0/E3/E4 ganan +0.004 absoluto** (0.0247 -> 0.0286): dentro del ruido
   para 11 folds; no justifica reemplazar un modelo congelado y validado.
3. **Decision: CONSERVAR toques-wf-1 congelado.** La precision de skill
   buscada no estaba en estos candidatos; E2 (target graduado) queda pendiente
   como la unica palanca con informacion nueva por evento.

### Resultados de la corrida 2 (2026-10-27): E2 triple-barrier + juez PBO

| candidato | skill | peor fold | folds+ | gana al campeon | rank OOS medio |
|---|---|---|---|---|---|
| campeon (congelado) | +0.0247 | +0.0038 | 11/11 | — | 4.2 |
| c0 re-entrenado | +0.0286 | +0.0124 | 11/11 | 6/11 | 2.03 |
| e3 recalibracion | +0.0284 | +0.0108 | 11/11 | 6/11 | 2.29 |
| e4 interacciones | +0.0285 | +0.0123 | 11/11 | 6/11 | 2.22 |
| e1 regimen | +0.0243 | +0.0041 | 11/11 | 6/11 | 4.46 |
| **E2 barrera k*ATR** | **+0.0164** | **-0.0098** | **9/11** | **3/11** | **5.8** |

Juez PBO (CSCV completo, 462 particiones IS/OOS de los 11 folds): **en el 40% de
las particiones el mejor IS no mantiene rango en OOS** = la familia entera
tiene overfitting de backtest por encima de lo comodo.

**Conclusiones (negativas publicadas, como manda la regla):**

1. **E2 RECHAZADO**: la barrera escalada por ATR (k calibrado a 0.15*ATR por
   igualacion de tasas) EMPEORA: +0.0164 vs +0.0247 del campeon, rank OOS
   ultimo (5.8/6), gana solo 3/11 folds. La barrera fija de 0.5% NO era
   arbitraria: funcionaba. Timeouts 6.1% (eventos sin respuesta clara).
2. **PBO confirma el veredicto de la corrida 1**: el hueco de +0.004 entre
   c0/e3/e4 y el campeon cae dentro de la zona de ruido que el propio juez
   marca (40% de falls IS->OOS). Ninguno gana de forma CONSISTENTE (6/11 no
   es consistencia; se exigiria >=9/11).
3. **Senal debil pero real**: c0/e3/e4 rankean 2.0-2.3 de 6 en OOS de forma
   sistematica. Es un candidato a vigilar, no a publicar: si en la corrida de
   noviembre (con datos nuevos) el patron se repite Y el PSI/deriva deja de
   sisear, ahi se conversa de toques-wf-2.
4. **Decision: CONSERVAR toques-wf-1 congelado** (por segunda corrida
   independiente). El congelamiento ya no es solo disciplina: es el resultado
   de dos experimentos con juez.
