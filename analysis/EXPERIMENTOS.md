# ðŸ§ª Cuaderno de experimentos (pre-registro + resultados)

Regla del proyecto: **las hipÃ³tesis se registran ANTES de medir**. Cada fila del
scoreboard (`analysis/experimentos/scoreboard.jsonl`) tiene: id, fecha, hipÃ³tesis,
cambio exacto, mÃ©trica esperada, protocolo de validaciÃ³n, resultado observado y
decisiÃ³n (conservar / revertir). Los resultados negativos se publican igual.

## Protocolo de validaciÃ³n (fijo, no se cambia por resultado)

1. **Replay sin mirada al futuro**: velas 5m, paso = horizonte = 48 (ventanas de
   etiquetado NO solapadas), warm-up 300 velas, contexto solo con velas â‰¤ corte.
   HTF cortado por bisect. Ventana de trabajo acotada a 3000 velas (la EMA200 ya
   estÃ¡ convergida: el efecto de la semeda es <0,0001%; verificado contra el
   replay de ventana completa).
2. **Etiqueta**: `hold_4h_0.5pct` â€” el nivel aguantÃ³ si ningÃºn cierre 5m cae 0,5%
   mÃ¡s allÃ¡ en las 48 velas siguientes. Solo niveles con **3+ toques reales en 6h**
   (el motor no inventa probabilidad sin toques).
3. **Walk-forward con embargo**: entrenar con datos estrictamente anteriores al
   fold de prueba + 24 h de embargo (288 velas 5m). Nunca se ve el futuro.
4. **Muestras efectivas**: cada decisiÃ³n (4 h) es independiente; las etiquetas no
   se solapan. Se cuenta la decisiÃ³n, no la fila nominal.
5. **MÃ©tricas**: Brier, Brier skill vs tasa base, ECE, PSI (vivo vs OOS), y corte
   por lado (soporte/resistencia) y por rÃ©gimen (volatilidad, sesiÃ³n).
6. **Criterio de Ã©xito** (no se negocia): skill > 0 estable (racha en folds),
   PSI < 0,25, ECE â‰¤ 0,08, â‰¥ 100 muestras efectivas.

## HipÃ³tesis registradas (antes de medir) y RESULTADOS

| ID | HipÃ³tesis | Resultado medido | DecisiÃ³n |
|---|---|---|---|
| H1 | El modelo publicado (`toques-v2-l1`) tiene skill â‰ˆ 0 o negativa fuera de muestra | **Confirmada y peor**: negativo en los 11 folds (âˆ’0,035 a âˆ’0,169) y en el holdout de octubre (âˆ’0,054) | revertir el modelo |
| H1b | Una logÃ­stica L1 re entrenada por fold walk-forward tiene skill > 0 | **Confirmada**: 11 folds / 7.757 muestras OOS, skill medio **+0,0168**, 10 de 11 folds positivos, racha de 6. Holdout octubre (nadie entrenado): **+0,0093**, ECE 0,021 | **conservar** â†’ modelo nuevo `toques-wf-1` |
| H2 | Recalibrar SOLO el intercepto sobre el train de cada fold baja el Brier sin colapsar | **Negativa**: idÃ©ntico al H1 en los 11 folds (el fit L1 por fold ya deja el intercepto calibrado) | revertir |
| H3 | El edge estÃ¡ en un lado o rÃ©gimen, no en el global | **Parcialmente**: soporte +0,0162 (n=3.952) y resistencia +0,0122 (n=3.805) sobreviven; **compresiÃ³n +0,031** y **expansiÃ³n âˆ’0,029** (n=1.085) â†’ el modelo falla en alta volatilidad; noche âˆ’0,027 | conservar; la expansiÃ³n queda documentada como lÃ­mite conocido |
| H4 | Un modelo con menos features (solo ATR + dist) generaliza igual o mejor | _pendiente de medir_ | â€” |
| H5 | Horizonte 8 h (etiqueta pre-registrada aquÃ­) aumenta el skill medible | _pendiente de medir_ | â€” |

## Modelo publicado ahora: `toques-wf-1`

- Entrenado con TODO el historial â‰¤ 2026-09-30 (24 h de embargo antes del holdout),
  mismo target y mismas 9 features; L1 C=0.03.
- **Coeficientes sparse**: solo sobreviven `hourc` (+0,098), `dow` (âˆ’0,190) y
  `x_atr288` (âˆ’0,207). Las features de precio (dist, atr, ema200, rng, atr48/144)
  se apagan: el aguante de un nivel con 3+ toques estÃ¡ dominado por la **hora,
  el dÃ­a de la semana y la volatilidad de 24 h**, no por la distancia al nivel.
- **OOS octubre 2026** (132 decisiones, 198 muestras, nadie lo entrenÃ³):
  Brier 0,1239 Â· base 84,85% Â· **skill +0,0364** Â· ECE 0,025 Â· bins monÃ³tonos
  (0,80-1,01: predice 0,85, acierta 0,873) Â· soporte +0,0575 Â· resistencia +0,0065.
- **Deriva**: PSI vivo-vs-OOS **0,157 (watch)** con el modelo nuevo (era 1,20 con
  el viejo: la distribuciÃ³n de probabilidades ya no estÃ¡ desplazada).

## Reproducir

```bash
python analysis/entrenar_hold.py --datadir <velas> --desde 2023-01-01 \
    --hasta 2026-09-30 --test-dias 90 --train-dias 365 --embargo-horas 24
python analysis/entrenar_hold.py --datadir <velas> \
    --holdout-ini 2026-10-01T00:00:00+00:00 --guardar-modelo modelo_final.json
```

Coste orientativo: ~1,3 min por fold de 90 dias con 435k velas cargadas.

## CONGELAMIENTO (toques-wf-1)

**Fecha:** 2026-10-24 Â· **Estado:** CONGELADO

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

## Candidatos al prÃ³ximo modelo (pre-registro 2026-10-26)

Contexto que motiva estos experimentos (observado, no supuesto): ventana viva
del 24-25/10 con el modelo colapsado a un solo bin de probabilidad (0.80-1.01),
skill viva negativa (-4.6% a -6.8%, n=45-54) y calibracion 0.0596 > 0.05,
mientras el OOS congelado seguia positivo (+2.6% a +2.8%, n=225). El modelo
tiene UNA feature sensible al mercado (volatilidad 24h) y por eso, en
compresion de volatilidad, colapsa a la tasa base.

Protocolo comÃºn a TODOS: mismo replay sin mirada al futuro, mismos 11 folds
temporales, mismo embargo de 24 h, mismas features de evento; se compara
contra `toques-wf-1` (coeficientes actuales) en los MISMOS folds. Un
candidato solo es candidato si gana en el MISMO protocolo, no en un corte
elegido a posteriori. Sin datos nuevos hasta E5.

- **E1 Â· Modelo con estado de regimen.** Hipotesis: condicionar por regimen de
  volatilidad (cuantiles de ATR, 3 estados) evita el colapso a la tasa base y
  recupera senal en calma. Cambio exacto: coeficientes por regimen en vez de
  coeficientes globales; estado "sin senal" explicito cuando todos los regimenes
  coinciden con la tasa base. Metrica esperada: Brier >= actual en fold calmo;
  skill_medio WF > 0.0168 (actual) sin empeorar ningun fold mas de 0.005.
- **E2 Â· Target graduado.** Hipotesis: el target binario hold_4h_0.5pct esta
  dominado por la tasa base (85%); predecir recorrido (distancia de ruptura,
  regresion cuantil) o MFE/MAE asimetrico tiene mas informacion por evento.
  Metrica esperada: skill > 0.0168 en el mismo protocolo, con ECE <= 0.05.
- **E3 Â· Recalibracion rodante.** Hipotesis: el Platt-lite estatico envejece
  con el regimen (nuestra calibracion viva 0.0596). Recalibrar intercepto por
  ventana rodante deberia sostener ECE <= 0.05 incluso con deriva.
  Metrica esperada: ECE viva <= 0.05 sostenido; si la skill no mejora, se
  conserva igual por la honestidad de las probabilidades.
- **E4 Â· Logistica con interacciones.** Hipotesis: L1 poda las interacciones
  hora x volatilidad y dia x regimen; anadirlas a mano (mismo modelo lineal)
  deberia capturarlas sin cambiar la clase de modelo. Metrica: idem E1.
- **E5 Â· Datos nuevos (solo si E1-E4 se estancan).** CVD/flujo a 1m, basis de
  funding, skew de opciones. La literatura (OFI, RAML) dice que el edge
  documentado grande vive ahi; pero decae con el horizonte, asi que en 4h se
  espera contexto de defensa de nivel, no senal independiente.

### E2 (corrida 2) Â· triple-barrier + PBO como juez â€” pre-registro 2026-10-27

Base bibliografica: triple-barrier method (Lopez de Prado) con **barreras
calibradas a los datos, no fijas** (arXiv 2504.02249: ajustan barrera/ventana
para balancear etiquetas; arXiv 2411.12753: triple-barrier + frac-diff mejora
retorno ajustado por riesgo en BTC/ETH); validacion de resultados con PBO /
deflated Sharpe (finlab-ml, sommersut/crypto-triple-barrier-lgbm).

- **E2a Â· barrera escalada por ATR.** Hipotesis: la barrera fija de 0.5% es
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

## MISIÃ“N EDGE 2026-10-31 (pre-registro, commit ANTES de resultados)

**HipÃ³tesis H1 â€” funding extremo â†’ reversiÃ³n.** Autor: misiÃ³n externa
(2026-10-31). Estado del gate de datos: `docs/audit/INVESTIGACION_EDGE.md` (H1 PASA con
604 eventos; **H2 DETENIDA por falta de datos**: la API de OI/taker no baja de
30 dÃ­as, no se alcanzan 300 eventos â†’ resultado honesto = no concluyente).

### Regla exacta (fijada antes de mirar retornos)

- SeÃ±al: `fundingRate` en el timestamp *t*; se compara con los percentiles
  **causales** de los 30 dÃ­as trailing (sin look-ahead; mÃ­nimo 30 obs).
  - funding â‰¥ p95 â†’ corto (la punta larga paga y revierte).
  - funding â‰¤ p5 â†’ largo (la punta corta paga y revierte).
- Entrada: **open del bar 5m siguiente** al timestamp de funding.
- Salidas (se prueban las 4): **4 h, 8 h, 12 h, 24 h**.
- Costes (siempre aplicados): fee taker 0,05% Ã— 2 + slippage por lado
  (0,02% base + 0,25 Ã— ATR) **+ funding cobrado/pagado durante el hold**
  (cada 8 h; seÃ±al corta con funding positivo **cobra**).
- Cooldown: variante A 24 h (604 eventos), variante B 8 h (1.155 eventos).
- Direccionalidad: H1 es direccional (no agrega al target del 85%).
- **Variantes probadas: 8 celdas** (2 cooldowns Ã— 4 horizontes) â†’
  correcciÃ³n Bonferroni Î± = 0,05/8 = **0,00625**.

### Criterio de muerte (si falla UNO, no hay edge)

```
[ ] Expectativa neta > 0
[ ] IC95% inferior > 0 (bootstrap 10.000, semilla fija)
[ ] Positivo en ambas mitades temporales
[ ] Positivo en â‰¥2 regÃ­menes de volatilidad
[ ] Sobrevive costes Ã—2
[ ] n_independientes â‰¥ 300
[ ] p_corregido < 0,05 (Bonferroni por 8 celdas)
```

### Expectativa declarada antes de medir (anti-hindsight)

Espero **gross pequeÃ±o o nulo y neto dudoso**: el efecto de extremo de funding
estÃ¡ documentado en cripto, pero a 4-24 h con 0,10-0,20% de coste de ida y
vuelta mÃ¡s slippage, la mayorÃ­a de la literatura lo da como marginal. Mi
predicciÃ³n honesta: *sin_edge* o expectativa que no sobreviva costes Ã—2.

### RESULTADO (2026-10-31, medido despuÃ©s del commit del pre-registro)

**H1: SIN EDGE. No operar.** Informe completo: `docs/audit/INVESTIGACION_EDGE.md`.
Datos: `analysis/data/edge_funding.json`.

| Variante | Horizonte | n | neta | IC95 | hit | veredicto |
|---|---|---:|---:|---|---:|---|
| B8h | 4h | 416 | âˆ’0,2145% | [âˆ’0,3111, âˆ’0,1167] | 0,34 | sin_edge |
| B8h | 8h | 416 | âˆ’0,1877% | [âˆ’0,3290, âˆ’0,0437] | 0,37 | sin_edge |
| B8h | 12h | 416 | âˆ’0,1757% | [âˆ’0,3467, +0,0034] | 0,39 | sin_edge |
| B8h | 24h | 416 | âˆ’0,1205% | [âˆ’0,3767, +0,1321] | 0,45 | sin_edge |
| A24h | 4/8/12/24h | 282 | âˆ’0,2216/âˆ’0,2487/âˆ’0,2632/âˆ’0,1431% | todos cruzan 0 | 0,35-0,45 | **no_concluyente** (n<300) |

- Bruto: de +0,0193% (4h) a +0,1006% (24h). Coste medio: **0,2338%** por viaje.
  El mejor bruto es el 43% del coste: el efecto existe pero no llega a pagar el
  viaje. Funding apenas compensa (+0,0000 a +0,0127%).
- Fallan los 7 criterios de muerte: neta<0, IC95 inferior<0, no positiva en
  ambas mitades (mejor celda 24h: h1 +0,1276 vs h2 âˆ’0,3687), no positiva en â‰¥2
  regÃ­menes, no sobrevive costes Ã—2 (âˆ’0,35 a âˆ’0,49%), p_corregido=1,00000.
- Hit rate 0,34-0,45 (<0,5): sesgo de **signo opuesto** (continuaciÃ³n, no
  reversiÃ³n). Equidad B8h 4h: âˆ’89,2% en 416 ops, max_dd 93,7%.

**CorrecciÃ³n declarada:** los tests destaparon que `>=` en p95 empataba con la
tasa por defecto (+0,0001 = 27,1% de los registros) y disparaba eventos falsos
en el 16,6% de las ventanas. Corregido a comparaciÃ³n estricta: la muestra BAJA
de 603â†’282 (A24h) y 1153â†’416 (B8h), y el veredicto no mejora. MotivaciÃ³n:
fallo de test, no el resultado. Test de regresiÃ³n aÃ±adido.

**H2: no concluyente por falta de datos** (tope de 30 dÃ­as de la API de OI/taker;
no se alcanzan 300 eventos). Ver `docs/audit/INVESTIGACION_EDGE.md`.

---

## H3 â€” expectativa NETA del signal "toques" del modelo congelado (2026-11-01)

Autor: misiÃ³n propia (objetivo del operador: *mejorar el edge*). Pre-registro
commiteado **antes** de medir resultados de expectativa.

### Contexto y por quÃ© este experimento

El modelo solo se ha evaluado en Brier/skill (bien calibrado, skill +0,007 vivo
y +0,0314 OOS). **Nunca en dinero.** El papel da âˆ’28,07 R en 15 operaciones,
dominadas por un solo trade de âˆ’25,67 R. Con 0,23 % de coste por viaje, ningÃºn
nÃºmero de skill dice si el signal gana dinero. Este experimento lo mide.

### Datos

`analysis/data/cache/expr_muestras.jsonl` â€” 11.049 muestras de replay
(2023-01-02 â†’ 2026-09-30) del modelo `toques-wf-1`, con `prob_modelo`, `y`
(target 4 h), `mfe_pct`, `mae_pct`, `nivel`, `lado`, `sesion`, `volatilidad`,
`bias`. Cobertura verificada: **100 %** de las muestras tienen klines 5m
suficientes para medir 4 h y 24 h.

### Regla exacta (fijada antes de medir)

- **Entrada**: open de la vela 5m siguiente al timestamp `t` de la muestra.
  Cero look-ahead. DirecciÃ³n: `lado=resistencia` â†’ corto; `soporte` â†’ largo.
- **Coste**: 0,23 % por viaje (fee 0,05 %Ã—2 + slippage 0,02 %Ã—2 +
  0,25Ã—ATR%Ã—2), igual que H1.
- **Independencia**: simulaciÃ³n secuencial de un operador real: una posiciÃ³n a
  la vez, cooldown de 4 h tras el cierre. Se reporta `n_independientes`.
- **Salidas (3 reglas)**:
  - `E1` â€” cierre a horizonte 4 h (48 velas), sin stop (equivale al target
    `hold_4h` del modelo).
  - `E2` â€” gestionada: TP +0,5 % / SL âˆ’0,3 %, cierre forzoso a 4 h. Si en la
    misma vela se tocan TP y SL, se asume **SL primero** (conservador).
  - `E3` â€” cierre a horizonte 24 h (288 velas), sin stop.
- **Conviction (2 filtros)**: `todas` (sin filtro) y `top` (prob_modelo en el
  cuartil superior, â‰ˆ â‰¥0,858).
- **Variantes probadas: 6 celdas** (3 salidas Ã— 2 convicciones) â†’
  Bonferroni Î± = 0,05/6 = **0,00833**.

### Criterio de muerte (si falla UNO, no hay edge)

```
[ ] Expectativa neta > 0
[ ] IC95% inferior > 0 (bootstrap 10.000, semilla fija)
[ ] Positivo en ambas mitades temporales
[ ] Positivo en >=2 regimenes de volatilidad
[ ] Sobrevive costes x2
[ ] n_independientes >= 300
[ ] p_corregido < 0,05 (Bonferroni por 6 celdas)
```

### Expectativa declarada antes de medir (con sesgo declarado)

**sin_edge**. Y declaro el sesgo honestamente: durante el gate de cobertura vi
las medianas de `mfe_pct` = 0,056 % y `mae_pct` = 0,787 %, es decir el
recorrido favorable tÃ­pico es unas 4Ã— menor que el coste del viaje. Por tanto
mi expectativa ya estÃ¡ contaminada por ese dato: declaro que espero que
**ninguna** de las 6 celdas supere el peaje, y que la manageda (E2) salga peor
aÃºn por el stop contra un mae de 0,79 %.

### QuÃ© se harÃ­a si sale edge

Solo si alguna celda pasa los 7 criterios: replicar el filtro/la salida en
papel (`paper`), sin tocar el modelo. Un edge aquÃ­ **no** autoriza des-congelar
`toques-wf-1`: exigirÃ­a de todas formas los 4 criterios registrados.

### RESULTADO (2026-11-01)

**H3: SIN EDGE. La seÃ±al del modelo congelado no gana dinero, y no es por la
muestra: son 2.513 operaciones independientes reales.** Informe:
`docs/audit/INVESTIGACION_EDGE.md` Â§8. Datos: `analysis/data/edge_toques.json`.

| Salida | ConvicciÃ³n | n | bruto | coste | **neta** | IC95 | hit | veredicto |
|---|---|---:|---:|---:|---:|---|---:|---|
| 4 h | todas | **2.513** | âˆ’0,0252 % | 0,2206 % | **âˆ’0,2458 %** | [âˆ’0,2816, âˆ’0,2089] | 0,31 | sin_edge |
| 4 h | top | 660 | âˆ’0,0215 % | 0,1828 % | âˆ’0,2043 % | [âˆ’0,2441, âˆ’0,1655] | 0,26 | sin_edge |
| gestionada TP0,5/SL0,3 | todas | 2.513 | âˆ’0,0076 % | 0,2206 % | âˆ’0,2282 % | [âˆ’0,2421, âˆ’0,2137] | 0,33 | sin_edge |
| gestionada | top | 660 | +0,0012 % | 0,1828 % | âˆ’0,1816 % | [âˆ’0,2055, âˆ’0,1572] | 0,28 | sin_edge |
| 24 h | todas | 990 | âˆ’0,0048 % | 0,2215 % | âˆ’0,2262 % | [âˆ’0,3776, âˆ’0,0742] | 0,43 | sin_edge |
| 24 h | top | 325 | **+0,0904 %** | 0,1839 % | **âˆ’0,0935 %** | [âˆ’0,2790, +0,0884] | 0,42 | sin_edge |

- **El bruto es ~cero** (âˆ’0,025 % a +0,090 %): la llamada de direcciÃ³n no
  aporta movimiento suficiente ni para acercarse al peaje. La mejor celda
  (24 h + convicciÃ³n alta) tiene bruto +0,09 % frente a 0,18 % de coste.
- El 84 % de acierto del modelo es sobre *"el nivel aguanta 4 h"*, que **no es
  dinero**: el hit rate de la operaciÃ³n es 0,26-0,43.
- Fallan los 7 criterios en las 6 celdas. `p_corregido` = 1,00000.
- **ValidaciÃ³n independiente**: el papel vivo mide âˆ’0,28 % medio por operaciÃ³n
  (n=15); este replay predice âˆ’0,25 %. La maquinaria de mediciÃ³n acierta al
  vivo casi exacto, asÃ­ que este resultado no es un artefacto del backtest.
- ConclusiÃ³n operativa: **no se puede "mejorar" esta seÃ±al afinÃ¡ndola**; su
  bruto es estructuralmente menor que el coste. Mejorar el edge exige otra
  familia de seÃ±ales (con movimiento real) o abaratar el coste por debajo de
  ~0,09 % (imposible: maker dejarÃ­a ~0,16 %).

---

## H4 â€” rediseÃ±o de la ENTRADA (misma direcciÃ³n, mejor momento) (2026-11-01)

Autor: misiÃ³n propia. Objetivo declarado por el operador: *mejorar el edge
rediseÃ±ando la entrada*. Pre-registro commiteado **antes** de medir.

### MotivaciÃ³n medida (no intuiciÃ³n)

En H3 el `mae_pct` mediano fue **0,787 %** frente a un `mfe_pct` mediano de
**0,056 %**: tras el toque, el precio suele profundizar ~0,8 % en contra antes
de rebotar. Entrar en el toque es entrar justo en el lado malo del latigazo.
La direcciÃ³n del modelo (`soporte`â†’largo, `resistencia`â†’corto) se mantiene
intacta; **solo cambia el momento de entrada**. El modelo congelado no se toca:
se reutiliza su direcciÃ³n y su `prob_modelo`.

### Regla exacta

Para cada muestra del replay (`t`, `nivel`, `lado`), con ventana de espera
mÃ¡xima **W = 24 velas (2 h)** y el `nivel` como referencia:

| Variante | Regla de entrada (todo con datos hasta el bar usado) |
|---|---|
| `base` | open de la vela siguiente a `t` (el H3 de referencia) |
| `retardo` | open de la vela siguiente a `t+2` velas (**control de tiempo**: aÃ­sla el retardo del efecto de la informaciÃ³n) |
| `confirm` | entrar cuando el **cierre** de una vela queda â‰¥0,3 % del lado favorable del nivel (largo: cierre â‰¥ nivelÃ—1,003; corto: â‰¤ nivelÃ—0,997); entrada al open de la **siguiente** vela. Si no confirma en W velas â†’ no hay trade |
| `barrido` | entrar cuando (a) una vela **perfora** el nivel â‰¥0,2 % (largo: low â‰¤ nivelÃ—0,998) **y** (b) una vela posterior **recupera** el nivel (cierre â‰¥ nivelÃ—1,0005); entrada al open de la siguiente. Si no ocurre en W velas â†’ no hay trade |

- **Salidas (2)**: `h4` cierre a 48 velas; `gest` TP +0,5 % / SL âˆ’0,3 % con
  cierre forzoso a 48 velas (si TP y SL en la misma vela, manda SL).
- **Coste**: idÃ©ntico a H3 (0,05 %Ã—2 + 0,02 %Ã—2 + 0,25Ã—ATR%Ã—2 â‰ˆ 0,18-0,23 %).
- **Independencia**: un trade a la vez + cooldown 4 h tras el cierre.
- **Variantes probadas: 8 celdas** (4 entradas Ã— 2 salidas) â†’ Bonferroni
  Î± = 0,05/8 = **0,00625**.

### Criterio de muerte (si falla UNO, no hay edge)

```
[ ] Expectativa neta > 0
[ ] IC95% inferior > 0 (bootstrap 10.000, semilla fija)
[ ] Positivo en ambas mitades temporales
[ ] Positivo en >=2 regimenes de volatilidad
[ ] Sobrevive costes x2
[ ] n_independientes >= 300
[ ] p_corregido < 0,05 (Bonferroni por 8 celdas)
```

### Expectativa declarada antes de medir (anti-hindsight)

Espero que `confirm` y `barrido` **reduzcan mucho el mae** (esa es la mecÃ¡nica
de la hipÃ³tesis) pero que **sigan sin pasar el peaje**, porque:

1. entran mÃ¡s caro: se comen el movimiento de confirmaciÃ³n (â‰¥0,3 %) antes de
   abrir, y el rebote total medido en H3 fue de apenas ~0,09 % bruto;
2. descartan las seÃ±ales que no confirman, que podrÃ­an ser justo las buenas;
3. mi predicciÃ³n es que el control `retardo` absorba la mayor parte de
   cualquier mejora, es decir que el efecto serÃ­a de **tiempo**, no de
   **informaciÃ³n**: si D1 mejora y `confirm`/`barrido` no mejoran mÃ¡s que D1,
   la hipÃ³tesis "la confirmaciÃ³n aporta" queda refutada.

PredicciÃ³n honesta: **sin_edge en las 8 celdas**, o como mucho una celda con
media positiva que no sobreviva costes Ã—2 ni el Bonferroni. Lo escribo antes de
mirar para no poder hacer trampa despuÃ©s.

### RESULTADO (2026-11-01)

**H4: SIN EDGE en las 8 celdas. La predicciÃ³n se cumpliÃ³, incluida la parte
fina (el control de tiempo absorbe la mejora).** Informe:
`docs/audit/INVESTIGACION_EDGE.md`. Datos: `analysis/data/edge_entrada.json`.

| Entrada | Salida | n | bruto | coste | neta | IC95 | hit | veredicto |
|---|---|---:|---:|---:|---:|---|---:|---|
| base | h4 | 2.513 | âˆ’0,0252 % | 0,2206 % | âˆ’0,2458 % | [âˆ’0,2816, âˆ’0,2089] | 0,31 | sin_edge |
| retardo | h4 | 2.513 | âˆ’0,0200 % | 0,2221 % | âˆ’0,2421 % | â€” | 0,31 | sin_edge |
| confirm | h4 | 2.396 | âˆ’0,0133 % | 0,2237 % | âˆ’0,2370 % | â€” | 0,32 | sin_edge |
| **barrido** | h4 | 728 | **+0,0240 %** | 0,2466 % | **âˆ’0,2226 %** | â€” | 0,38 | sin_edge |
| base | gest | 2.513 | âˆ’0,0076 % | 0,2206 % | âˆ’0,2282 % | â€” | 0,33 | sin_edge |
| retardo | gest | 2.513 | âˆ’0,0046 % | 0,2221 % | âˆ’0,2267 % | â€” | 0,33 | sin_edge |
| confirm | gest | 2.396 | âˆ’0,0021 % | 0,2237 % | âˆ’0,2259 % | â€” | 0,35 | sin_edge |
| barrido | gest | 728 | âˆ’0,0029 % | 0,2466 % | âˆ’0,2495 % | â€” | 0,36 | sin_edge |

- **La descomposiciÃ³n `base` â†’ `retardo` â†’ `confirm` dicta sentencia**: esperar
  10 minutos ya captura +0,0037 % de mejora, y la confirmaciÃ³n completa aÃ±ade
  solo +0,0051 % mÃ¡s. Es decir, **la mejora es de tiempo, no de informaciÃ³n**,
  exactamente la refutaciÃ³n que predije. La hipÃ³tesis "entrar tras confirmar
  aporta" queda refutada por su propio control.
- `barrido` es la Ãºnica entrada con bruto positivo (+0,024 %) pero **paga el
  coste mÃ¡s alto de las 8 celdas** (0,2466 %: entra mÃ¡s tarde, con ATR mÃ¡s alto)
  y descarta el 71 % de las seÃ±ales. Neto âˆ’0,2226 %: sigue sin edge.
- El rango completo de las 8 celdas es âˆ’0,2226 % a âˆ’0,2495 %: **0,03 % de
  amplitud sobre expectativas de âˆ’0,24 %**. Todas las variantes de entrada son
  la misma mediciÃ³n con distinto ruido.
- `p_corregido` = **1,00000**. Ninguna celda pasa ninguno de los 7 criterios.

### ConclusiÃ³n (tres hipÃ³tesis de edge medidas, tres refutaciones)

| # | HipÃ³tesis | Resultado |
|---|---|---|
| H1 | funding extremo â†’ reversiÃ³n | sin_edge (y de signo opuesto) |
| H3 | la seÃ±al del modelo, afinada | bruto ~0, neta âˆ’0,20 a âˆ’0,25 % |
| H4 | rediseÃ±o de la entrada | sin_edge; la mejora es de tiempo, no de informaciÃ³n |

**El cuello de botella no es la entrada ni la predicciÃ³n: es que esta familia
de seÃ±ales no produce movimiento de precio suficiente para pagar 0,2 % de
viaje.** Buscar edge aquÃ­ es buscar en el sitio equivocado. Las vÃ­as que
quedan honestamente abiertas son otra familia de seÃ±ales (movimiento real,
bruto â‰¥0,5 %) o el control de riesgo/coste. Ambas fuera del modelo congelado.

### Si saliera edge

Solo se replicarÃ­a el filtro de entrada **en papel** (`paper`), sin tocar el
modelo ni el gate. Un edge de entrada **no** autoriza des-congelar
`toques-wf-1`: los 4 criterios registrados siguen vigentes.

---

## H5 â€” RUPTURA del nivel â†’ continuaciÃ³n (familia con movimiento) (2026-11-01)

Autor: misiÃ³n propia. Objetivo del operador: *buscar edge en la familia de
rupturas con expansiÃ³n*. Pre-registro commiteado **antes** de medir.

### MotivaciÃ³n medida

H1, H3 y H4 refutaron la familia "rebote en el nivel": su bruto medido es ~0
(0,000-0,024 %) contra 0,2 % de peaje. Queda una familia con **mecÃ¡nica de
movimiento** en los mismos datos: las **rupturas**. En el replay, 1.778 de las
11.049 muestras (16,1 %) tienen `barras_ruptura` con dato y **las 1.778 tienen
`y=0`**: el nivel se rompiÃ³ siempre. Es decir, el modelo fallÃ³ en el 16 % de los
casos, y esos casos son justo los eventos de movimiento grande.

### Universo y limitaciÃ³n declarada (importante)

Universo = las muestras cuyo nivel se rompe dentro de 48 velas. La ruptura se
detecta **en tiempo real**: primer **cierre** mÃ¡s allÃ¡ del nivel tras `t`, y
entrada al open de la vela siguiente. Detector validado sobre las 1.778:
detecta el 100 % y todas dentro de las 48 velas. Mi definiciÃ³n dispara antes
que la etiqueta `barras_ruptura` del replay (mediana 11 velas antes): uso la mÃ­a
y lo declaro.

**LimitaciÃ³n honesta:** el universo se selecciona sabiendo que el nivel acabÃ³
rompiendo. El experimento mide *"dada una ruptura identificada en el momento en
que ocurre, Â¿paga el lado de la continuaciÃ³n?"*, **no** *"Â¿puedo detectar
rupturas en tiempo real?"*. Lo segundo es un desarrollo aparte y no estÃ¡ probado
aquÃ­.

### Regla exacta

- **DirecciÃ³n `ruptura`** (invertida respecto al modelo): `resistencia` rota â†’
  **largo**; `soporte` roto â†’ **corto**.
- **Control `control`**: la direcciÃ³n del modelo (`resistencia`â†’corto,
  `soporte`â†’largo), **misma vela de entrada**. Control de sustituciÃ³n: mismo
  evento, mismo momento, lado opuesto.
- **Entrada**: open de la vela siguiente al cierre que confirma la ruptura.
- **Filtros (2)**: `todas` (1.778 rupturas) y `extremos`
  (`volatilidad` âˆˆ {`expansion`, `compresion`}).
- **Salidas (2)**: `h4` cierre a 48 velas desde la ruptura; `fallo` salida en el
  primer cierre que vuelve a meterse dentro del nivel (la ruptura falla), o a 48
  velas si no falla.
- **Coste**: 0,05 %Ã—2 + 0,02 %Ã—2 + 0,25Ã—ATR%Ã—2 (â‰ˆ0,2 %).
- **Independencia**: un trade a la vez + cooldown **2 h** (la ruptura es el
  evento; 2 h las separa razonablemente).
- **Variantes probadas: 8 celdas** (2 filtros Ã— 2 direcciones Ã— 2 salidas) â†’
  Bonferroni Î± = 0,05/8 = **0,00625**.
- Adicional **informativo, fuera de las 8 celdas**: salida gestionada
  TP +1,0 % / SL âˆ’0,5 % y el subconjunto `expansion` a solas (~337 eventos).
  Se reporta pero **no** cuenta para el Bonferroni ni para el veredicto.

### Criterio de muerte (si falla UNO, no hay edge)

```
[ ] Expectativa neta > 0
[ ] IC95% inferior > 0 (bootstrap 10.000, semilla fija)
[ ] Positivo en ambas mitades temporales
[ ] Positivo en >=2 regimenes de volatilidad
[ ] Sobrevive costes x2
[ ] n_independientes >= 300
[ ] p_corregido < 0,05 (Bonferroni por 8 celdas)
```

### Expectativa declarada antes de medir (anti-hindsight)

Dos predicciones separadas, para que ninguna se esconda detrÃ¡s de la otra:

1. **PredicciÃ³n fuerte (mecÃ¡nica)**: el bruto del lado `ruptura` serÃ¡
   **claramente mayor** que el del `control` (que arrastra el ~0 medido en H3).
   Es la mecÃ¡nica de la familia: una ruptura mueve el precio mÃ¡s que un rebote.
2. **PredicciÃ³n de veredicto**: **ninguna celda pasa los 7 criterios**. El
   movimiento post-ruptura a 4 h tendrÃ­a que superar 0,25 % neto de forma
   estable en mitades y regÃ­menes, y mi lectura de H1/H3/H4 es que este marco no
   lo da. Si alguna pasa, apuesto a que serÃ­a `todas:ruptura:h4`.

### Si saliera edge

Solo se replicarÃ­a en papel (`paper`) **despuÃ©s** de construir y validar el
detector de ruptura en tiempo real (no probado aquÃ­). Un edge de ruptura **no**
autoriza des-congelar `toques-wf-1`: los 4 criterios siguen vigentes, y esta
familia es ademÃ¡s **independiente del modelo** (ni usa su direcciÃ³n ni su
probabilidad en el lado de ruptura).

### RESULTADO (2026-11-01)

**H5: SIN EDGE en las 8 celdas, y la predicciÃ³n fuerte de mecÃ¡nica tambiÃ©n
fallÃ³: el bruto de `ruptura` NO supera al del `control` (son espejos, Â±0,002 %).**
Informe: `docs/audit/INVESTIGACION_EDGE.md`. Datos:
`analysis/data/edge_ruptura.json`.

| Filtro | DirecciÃ³n | Salida | n | bruto | coste | neta | hit | veredicto |
|---|---|---|---:|---:|---:|---:|---:|---|
| todas | ruptura | h4 | 2.586 | âˆ’0,0010 % | 0,2132 % | âˆ’0,2142 % | 0,32 | sin_edge |
| todas | ruptura | fallo | 2.586 | +0,0115 % | 0,2132 % | âˆ’0,2017 % | 0,12 | sin_edge |
| todas | control | h4 | 2.586 | +0,0010 % | 0,2132 % | âˆ’0,2122 % | 0,36 | sin_edge |
| todas | control | fallo | 2.586 | âˆ’0,0115 % | 0,2132 % | âˆ’0,2247 % | 0,16 | sin_edge |
| extremos | ruptura | h4 | 1.592 | +0,0097 % | 0,2093 % | âˆ’0,1997 % | 0,33 | sin_edge |
| extremos | ruptura | fallo | 1.592 | +0,0116 % | 0,2093 % | âˆ’0,1977 % | 0,13 | sin_edge |
| extremos | control | h4 | 1.592 | âˆ’0,0097 % | 0,2093 % | âˆ’0,2190 % | 0,34 | sin_edge |
| extremos | control | fallo | 1.592 | âˆ’0,0116 % | 0,2093 % | âˆ’0,2209 % | 0,15 | sin_edge |

Informativo (fuera del Bonferroni): `expansion` a solas, `ruptura:h4` â†’
n=503, neta **âˆ’0,2793 %** (la peor celda del experimento); gestionada TP1/SL0,5
en `todas` â†’ âˆ’0,2119 % (ruptura) / âˆ’0,2066 % (control).

- **`ruptura` y `control` son espejos exactos** (+0,0010 vs âˆ’0,0010 a 4 h): el
  movimiento tras la ruptura es **cero en ambas direcciones**. Una ruptura no
  predice nada a 4 h; es un evento de nivel, no de precio.
- **La apuesta especÃ­fica (`expansion`) es la peor** (âˆ’0,2793 %, n=503, IC95
  [âˆ’0,3776, âˆ’0,1793]): el rÃ©gimen de expansiÃ³n tiene el coste mÃ¡s alto (0,2567 %)
  y el bruto mÃ¡s negativo. La hipÃ³tesis del operador queda refutada con su
  propio subconjunto.
- El nivel sÃ­ "aguanta la ruptura" en el sentido de nivel (la salida `fallo`
  solo se dispara el 12-16 % de las veces), pero eso no se traduce en precio.
- `p_corregido` = **1,00000**. Ninguna celda pasa ninguno de los 7 criterios.

### Balance final de la bÃºsqueda de edge (5 hipÃ³tesis, 5 refutaciones)

| # | Familie | n medida | Bruto mÃ¡ximo observado | Veredicto |
|---|---|---:|---:|---|
| H1 | funding extremo â†’ reversiÃ³n | 416 | ~0 | sin_edge (signo opuesto) |
| H3 | rebote en el nivel (afinada) | 2.513 | +0,090 % | sin_edge |
| H4 | rebote, entrada rediseÃ±ada | 2.513 | +0,024 % | sin_edge (mejora de tiempo, no de informaciÃ³n) |
| H5 | ruptura â†’ continuaciÃ³n | 2.586 | +0,012 % | sin_edge (y `expansion` la peor) |

**PatrÃ³n consistente en ~10.000 operaciones independientes: ninguna familia
produce bruto por encima de 0,09 % cuando el peaje es 0,21 %.** El cuello de
botella no es la seÃ±al, es la relaciÃ³n movimiento/coste en este marco (5m de
dato, 4 h de hold). Con este coste, hace falta bruto â‰¥0,5 % para operar; eso
solo aparece en horizontes largos (el bruto de H3 crecÃ­a con el hold) o en
costes mucho menores. Los siguientes pasos honestos son horizontes largos
(12-72 h) y la gestiÃ³n de riesgo/coste, no mÃ¡s variantes de esta familia.

---

## H6 â€” HORIZONTES LARGOS 12/24/48/72 h (Ãºltima palanca del marco) (2026-11-01)

Autor: misiÃ³n propia. Objetivo del operador: *horizontes largos*. Pre-registro
commiteado **antes** de medir.

### MotivaciÃ³n medida

En H3 el Ãºnico bruto positivo apareciÃ³ en **24 h con convicciÃ³n alta**
(+0,0904 %) y el bruto de H1 crecÃ­a con el horizonte (0,02 % a 4 h â†’ 0,10 % a
24 h). El coste de ida y vuelta es fijo, asÃ­ que el horizonte es la Ãºnica
variable con gradiente a favor observado. Queda probarla hasta donde lleguen
los datos: 12, 24, 48 y 72 h.

### Gate de datos (ya verificado)

- Cobertura: **100 %** de las 11.049 muestras son medibles a 12 h, 24 h, 48 h y
  72 h (las velas llegan 30 dÃ­as mÃ¡s allÃ¡ de la Ãºltima muestra).
- **Funding durante el hold** (mediano acumulado, positivo = paga el largo):
  12 h â†’ +0,0117 % Â· 24 h â†’ +0,0186 % Â· 48 h â†’ +0,0354 % Â· 72 h â†’ +0,0519 %.
  En H3 no se modelÃ³ el funding (hold de 4 h â‰¤ 1 pago, despreciable); aquÃ­ es
  obligatorio: un hold de 72 h acumula 9 pagos.

### Regla exacta

- **Entrada**: open de la vela siguiente a `t`. **DirecciÃ³n**: la del modelo
  (`soporte`â†’largo, `resistencia`â†’corto). Nada de H3 cambia: solo el horizonte.
- **Salida**: cierre a 144 / 288 / 576 / 864 velas (12 / 24 / 48 / 72 h).
- **Coste**: fee 0,05 %Ã—2 + slippage 0,02 %Ã—2 + 0,25Ã—ATR%Ã—2 **+ funding
  cobrado/pagado durante el hold** (convenciÃ³n: el largo cobra si funding < 0 y
  paga si > 0; el corto lo contrario).
- **ConvicciÃ³n (2)**: `todas` y `top` (`prob_modelo` â‰¥ 0,858).
- **Independencia**: un trade a la vez + cooldown = horizonte + 4 h (asÃ­ los
  holds nunca se solapan).
- **Variantes probadas: 8 celdas** (4 horizontes Ã— 2 convicciones) â†’
  Bonferroni Î± = 0,05/8 = **0,00625**.

### Criterio de muerte (si falla UNO, no hay edge)

```
[ ] Expectativa neta > 0
[ ] IC95% inferior > 0 (bootstrap 10.000, semilla fija)
[ ] Positivo en ambas mitades temporales
[ ] Positivo en >=2 regimenes de volatilidad
[ ] Sobrevive costes x2
[ ] n_independientes >= 300
[ ] p_corregido < 0,05 (Bonferroni por 8 celdas)
```

### Expectativa declarada antes de medir (anti-hindsight)

PredicciÃ³n: **ninguna celda pasa los 7 criterios**, por tres razones medidas:

1. el bruto de `todas` se ha mantenido en ~0 a 4 h **y** a 24 h (âˆ’0,0252 % y
   âˆ’0,0048 % en H3): no hay gradiente que explotar en ese subconjunto;
2. el bruto positivo de 24 h fue de +0,0904 % **y solo en `top`**; aunque el
   gradiente siguiera, llegarÃ­amos a +0,15-0,20 % a 72 h, justo lo que se come
   el coste ampliado (0,18 % de peaje + hasta 0,05 % de funding);
3. a mayor hold, mayor varianza: el IC95 se ensancha y "positiva en ambas
   mitades" se vuelve mÃ¡s difÃ­cil.

Apuesto a que **`top` seguirÃ¡ siendo mejor que `todas`** (predicciÃ³n de
mecÃ¡nica) y a que la mejor celda serÃ¡ `top:24h` o `top:48h`, pero **por debajo
del umbral**. Si alguna pasa, serÃ­a `top:48h`.

### Si saliera edge

Se replicarÃ­a el horizonte en papel (`paper`). Un edge de horizonte **no**
autoriza des-congelar `toques-wf-1` (los 4 criterios siguen vigentes), pero sÃ­
obligarÃ­a a replantear el target `hold_4h` del modelo: eso serÃ­a un
**candidato nuevo**, con su propio pre-registro, no un retoque del campeÃ³n.

### RESULTADO (2026-11-01)

**H6: SIN EDGE. Y el giro importa mÃ¡s que el veredicto: el bruto crece hasta
24 h y luego se DESPLOMA** (âˆ’0,10 % a 48 h, âˆ’0,33 % a 72 h). La palanca del
horizonte se agota en 24 h; mÃ¡s allÃ¡ perjudica. Informe:
`docs/audit/INVESTIGACION_EDGE.md`. Datos: `analysis/data/edge_horizontes.json`.

| Horizonte | ConvicciÃ³n | n | bruto | funding | coste | **neta** | hit | veredicto |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 12 h | todas | 1.551 | +0,0101 % | âˆ’0,0004 % | 0,2170 % | âˆ’0,2073 % | 0,39 | sin_edge |
| 12 h | top | 486 | âˆ’0,0273 % | âˆ’0,0006 % | 0,1850 % | âˆ’0,2130 % | 0,33 | sin_edge |
| **24 h** | **top** | 325 | **+0,0904 %** | âˆ’0,0033 % | 0,1839 % | **âˆ’0,0968 %** | 0,42 | sin_edge |
| 24 h | todas | 990 | âˆ’0,0048 % | +0,0014 % | 0,2215 % | âˆ’0,2248 % | 0,43 | sin_edge |
| 48 h | todas | 576 | âˆ’0,1027 % | +0,0006 % | 0,2220 % | âˆ’0,3241 % | 0,43 | sin_edge |
| 48 h | top | 219 | +0,0054 % | âˆ’0,0037 % | 0,1854 % | âˆ’0,1836 % | 0,43 | no_concluyente (n<300) |
| 72 h | todas | 406 | âˆ’0,3348 % | +0,0010 % | 0,2201 % | âˆ’0,5539 % | 0,43 | sin_edge |
| 72 h | top | 186 | âˆ’0,2364 % | âˆ’0,0089 % | 0,1887 % | âˆ’0,4340 % | 0,39 | no_concluyente (n<300) |

- **Mejor celda de toda la investigaciÃ³n**: 24 h con alta convicciÃ³n,
  âˆ’0,0968 % neta (bruto +0,0904 %). Sigue siendo negativa: el bruto no llega al
  peaje ni en su mejor momento.
- **El gradiente del horizonte se invierte a partir de 24 h**: a 48 h el bruto
  ya es negativo y a 72 h es âˆ’0,33 %. Mantener la posiciÃ³n mÃ¡s tiempo no espera
  el movimiento: lo devora. La predicciÃ³n "mejor celda top:24h o top:48h" se
  cumpliÃ³ (fue top:24h); la de "ninguna pasa" tambiÃ©n.
- **El funding pesÃ³ mucho menos de lo que temÃ­a** (âˆ’0,0004 % a âˆ’0,0089 %): la
  mayorÃ­a de los holds atraviesan pagos cercanos a la tasa por defecto. No era
  el freno.
- La n cae con el horizonte (el cooldown se estira con el hold): 48 h y 72 h en
  `top` quedan en 219 y 186 â†’ **no_concluyente**, no "sin edge": no hay muestra
  para dictar sentencia.
- `p_corregido` = **1,00000**.

### Veredicto final de la bÃºsqueda de edge (6 hipÃ³tesis, 6 refutaciones)

| # | Familia / palanca | Mejor neta medida | Veredicto |
|---|---|---:|---|
| H1 | funding extremo â†’ reversiÃ³n | âˆ’0,09 % | sin_edge (signo opuesto) |
| H3 | rebote en el nivel, afinada | âˆ’0,0968 % (24 h, top) | sin_edge |
| H4 | rebote, entrada rediseÃ±ada (4 variantes) | âˆ’0,2226 % | sin_edge |
| H5 | ruptura â†’ continuaciÃ³n | âˆ’0,1977 % | sin_edge |
| H6 | horizontes largos 12-72 h | âˆ’0,0968 % (24 h, top) | sin_edge |

**Cierre con evidencia:** en ~10.000 operaciones independientes sobre 3,8 aÃ±os,
ninguna familia ni palana produce una expectativa neta positiva. El mejor bruto
medido en toda la investigaciÃ³n es **+0,0904 %**, contra un peaje de 0,18-0,23 %,
y aparece solo en 24 h con alta convicciÃ³n. El marco (velas 5 m, seÃ±al de nivel,
hold 4-72 h, coste taker) **no contiene edge direccional demostrable**, y las
tres palancas disponibles â€”afinar la seÃ±al, rediseÃ±ar la entrada, estirar el
horizonteâ€” estÃ¡n medidas y agotadas.

Consecuencias honestas para el bot:
1. **No operar con el modelo actual**. Su expectativa medida es âˆ’0,10 a âˆ’0,25 %
   por operaciÃ³n. El papel vivo (âˆ’0,28 % de media) lo confirma de forma
   independiente.
2. **Lo que queda es gestiÃ³n, no bÃºsqueda**: tope de pÃ©rdida por operaciÃ³n
   (el trade de âˆ’25 R), tamaÃ±o, y coste real frente al modelado.
3. **Si se quiere rentabilidad estructural**, la vÃ­a no es otra seÃ±al: es
   invertir la ecuaciÃ³n de coste (ganar el spread en vez de pagarlo), que es
   otro sistema, con su propio pre-registro y sus propios riesgos. Eso **no**
   estÃ¡ probado aquÃ­ y no se afirma que funcione.

---

## Auditoria de la red neuronal (2026-10-27)

Recomendacion externa recibida: "arreglar etiquetas y ventana_vivo antes de
entrenar nada; la NN entra como challenger con el mismo liston; ningun LLM en
el bucle de trading". Primer paso de la auditoria = encontrar que auditar.

**Hallazgo (phantom):** el bloque "RED NEURONAL (OPT-IN)" de `main()` importaba
`nn_infer`, modulo que **nunca existio en el repo** (ni local ni en los 127
archivos de main). Cada ejecucion con `VIGILANTE_NN=1` fallaba con ImportError
y segua por el `except`. No habia etiquetas que auditar, ni ventana_vivo, ni
modelo onnx, ni onnxruntime en requirements: era codigo que prometia una
capacidad inexistente.

**Accion:** bloque retirado de `vigilante_cloud.py` (monolito 1603 -> 1570
lineas) y reemplazado por la nota de auditoria. El fail-safe funciono (el bot
nunca se rompio), pero la honestidad del codigo manda: si una NN vuelve, entra
con (1) pipeline de entrenamiento versionada en el repo, (2) etiquetas y
ventana_vivo auditadas sin fuga de futuro, (3) shadow+gate y el MISMO liston
que toques-wf-1 (mismos folds, embargo, juez PBO).

**Pendiente del asesor, con nuestro veredicto:**
- "empieza por L1 + LightGBM": L1 ya es el modelo campeon; LightGBM puede
  entrar como challenger de laboratorio (equivalente aprox: E4, ya probado,
  +0.004 = ruido segun PBO).
- "MLP 59->32->3 para direccion ALZA/BAJA/LATERAL": es el target SIN senal
  documentada (direction ~ moneda con un instrumento); el edge del bot esta en
  aguante de nivel. Si se hace, se mide en sombra primero.
- "P1 (git, duplicados, LICENSE)": higiene del repo, cero riesgo, proximo.

### Resultados de la corrida 2 (2026-10-27): E2 triple-barrier + juez PBO

| candidato | skill | peor fold | folds+ | gana al campeon | rank OOS medio |
|---|---|---|---|---|---|
| campeon (congelado) | +0.0247 | +0.0038 | 11/11 | â€” | 4.2 |
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

## Corrida 3 (meta-labeling) â€” pre-registro 2026-10-27

Base bibliografica: meta-labeling (Lopez de Prado): un modelo SECUNDARIO no
predice el precio, predice **si el primario va a acertar en este evento**, y
la senal se emite solo cuando el secundario confia. Es la forma estandar de
combinar un modelo base debil con un filtro de confianza sin reentrenar el
base.

- **T2 Â· Secundario sobre el acierto del primario.** Hipotesis: el primario
  (toques-wf-1 congelado) tiene eventos donde su probabilidad es informativa y
  eventos donde es ruido; un secundario entrenado SOLO con datos anteriores al
  fold (mismo embargo) puede distinguirlos y subir el skill efectivo.
  Cambio exacto: target del secundario `y_meta = 1 si (prob_modelo >= 0.5)
  coincide con y`; features = las 9 base + `prob_modelo` + metadatos del evento
  (calidad, toques, confluencia, sweep, quiebre, lado, sesion one-hot);
  logistica L1 con el MISMO C=0.03 y el mismo `eh.entrenar`. Efecto medido:
  skill del primario restringido a los eventos donde el secundario confia
  (p > 0,5).
- **Metricas:** (a) skill del secundario vs siempre-1 (tasa base del acierto
  del primario); (b) skill COMBINADO (primario sobre eventos confiados) vs el
  skill del campeon en los mismos folds; (c) cobertura (fraccion de eventos
  donde confia).
- **Juez:** misma familia ampliada bajo el `_pbo` CSCV completo (C(11,5) = 462
  particiones IS/OOS).
- **Liston de exito PRE-REGISTRADO** (el secundario es candidato solo si cumple
  TODOS): (1) skill del secundario > 0 en >= 80% de los folds; (2) skill
  combinado > skill del campeon + 0.005 absoluto; (3) cobertura >= 50% (un
  filtro que descarta mas de la mitad de los eventos no es operable);
  (4) gana al campeon en >= 80% de los folds; (5) rank medio OOS del juez PBO
  <= 2 dentro de la familia. Si falla cualquiera: **negativo publicado**.
- **Aviso metodologico (pre-registrado a proposito):** comparar el skill
  combinado (sobre un subconjunto de eventos) contra el skill del campeon
  (sobre todos) NO es la misma poblacion; por eso el liston exige cobertura
  >= 50% y victorias por fold, y el PBO rankea a todos sobre la misma matriz.
  Publicar solo si gana en las tres.

Resultados -> `analysis/experimentos/scoreboard.jsonl`.

### Resultados de la corrida 3 (2026-10-27): T2 meta-labeling

Protocolo: mismo replay/folds/embargo; 11.049 muestras; secundario L1 C=0,03
sobre 20 features (9 base + `prob_modelo` + calidad/toques/confluencia/sweep/
quiebre/lado/sesion one-hot); train <= corte, test en el fold.

| candidato | skill medio | peor fold | folds+ | gana al campeon | rank OOS |
|---|---|---|---|---|---|
| campeon (congelado) | +0.0247 | +0.0038 | 11/11 | â€” | 4.26 |
| c0 re-entrenado | +0.0286 | +0.0124 | 11/11 | 6/11 | 2.05 |
| e3 recalibracion | +0.0284 | +0.0108 | 11/11 | 6/11 | 2.34 |
| e4 interacciones | +0.0285 | +0.0123 | 11/11 | 6/11 | 2.24 |
| e1 regimen | +0.0243 | +0.0041 | 11/11 | 6/11 | 4.84 |
| e2 barrera k*ATR | +0.0164 | -0.0098 | 9/11 | 3/11 | 6.67 |
| **T2 combinado (filtro de confianza)** | **+0.0232** | **+0.0038** | **11/11** | **2/11** | **5.6** |

Secundario (skill propio vs siempre-1): **+0,0399**, 11/11 folds > 0, peor
fold +0,0244, ECE medio 0,0248. Cobertura 99,7%: el secundario confia en
practicamente TODOS los eventos, asi que el filtro apenas descarta nada y el
combinado se degenera en "el campeon tal cual" (0,0232 vs 0,0247: los 2 folds
que gana no compensan).

**Conclusiones (negativos publicados, como manda la regla):**

1. **T2 RECHAZADO como filtro**: cobertura 99,7% (no hay eventos "sin senal"
   que filtrar) y el combinado pierde contra el campeon (0,0232 vs 0,0247,
   2/11 folds, rank OOS 5,6/7). El primario practicamente NUNCA predice
   ruptura (solo 5 de 11.049 eventos con `prob_modelo` < 0,5), asi que
   `y_meta` (acierto del primario) es casi igual a `y` (aguante): el
   meta-labeling clasico NO tiene donde apoyar el filtro con este primario.
   La literatura asume un primario que dice ALZA/BAJA; el nuestro es un
   clasificador de una sola clase y por eso el secundario colapsa a confiar
   siempre.
2. **PBO (cambio de escala, se documenta para no comparar peras con manzanas):**
   con el candidato T2 la familia pasa a 7 miembros y el juez CSCV completo
   marca 24% de falls IS->OOS. NO es comparable con el 40% de la corrida 2
   (la definicion de falla cambio: con 7 candidatos falla quien cae al puesto
   5 o peor). Los rangos OOS si son comparables: el filtro T2 rankea 5,6/7,
   es de los peores de la familia.
3. **Hallazgo emergente (NO pre-registrado, se publica como pendiente):** el
   SECUNDARIO como modelo (no como filtro) gana al campeon en 9/11 folds
   (+0,0399 vs +0,0247, peor fold +0,0244, ECE 0,0248). Es decir: los
   METADATOS del evento (calidad, toques, confluencia, sweep, quiebre, lado,
   sesion) anaden senal real sobre las 9 features numericas â€” la logistica L1
   solo ve 3 de esas 9 (hora, dia, ATR24h). Como se midio DESPUES de ver el
   dato (no estaba pre-registrado), se registra ahora como **E6** y se exige
   corrida propia con su liston antes de reclamar nada.
4. **Decision: CONSERVAR toques-wf-1 congelado** (tercera corrida
   independiente). T2 como tal no aporta; E6 queda pre-registrado para la
   corrida 4.

### E6 Â· Metadatos de evento (pre-registro 2026-10-27, corrida 4)

Descubierto dentro de la corrida 3 (T2), por eso se mide en corrida propia:
el liston se registra AHORA, antes de tocar el codigo de E6.

- **Hipotesis**: los metadatos del evento (calidad del nivel, toques_6h,
  confluencia HTF, sweep reciente, quiebre confirmado, lado, sesion) llevan
  senal de aguante que las 9 features numericas del modelo congelado no
  capturan (el L1 solo conserva `hourc`, `dow`, `x_atr288`).
- **Cambio exacto**: misma logistica L1 (C=0,03, `eh.entrenar`), features =
  9 base + los metadatos codificados (numericos como numericos,
  booleanos/lado/sesion como dummies one-hot), entrenada por fold con
  train <= corte y embargo 24 h.
- **Metrica esperada**: skill_medio WF > 0.0168 (el de `toques-wf-1`) con
  consistencia: victorias >= 9/11 folds, peor fold > 0, ECE <= 0,05, y rank
  OOS del juez PBO <= 2 dentro de la familia.
- **Aviso**: el +0,0399 observado dentro de T2 es POST-HOC (se vio despues de
  medir); solo cuenta si una corrida propia lo reproduce con el liston de
  arriba. Si no, se publica el negativo igual.
- **Nada se publica** sin cumplir los 4 criterios de des-congelamiento de
  arriba; el campeon sigue congelado.

