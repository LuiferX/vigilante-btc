# 🗺️ HOJA DE RUTA — Vigilante BTC (proyecto personal de LuiferX)

## ✅ Versiones construidas (resumen corto; detalle en README.md)
- v1 local, v2 PRO cloud, v3 Compañero, v4 Máquina, v5 Institucional
  (score A/B/C, ADX+régimen, blackout, datos sanos, CVD, auditoría, backtest.py).

## 📝 Pendiente (ideas anotadas)
1. **🧠 Auto-calibración (PRIORITARIA)**: el bot ajusta SOLO sus umbrales según su precisión
   medida por sesión. Ej: NY con 75% de acierto → avisa desde 45% confianza; Asia con 30% →
   exige 70%. ML honesto y simple, con límites de seguridad (nunca relaja el plan 2R ni el 1%).
2. **🔍 "Por qué" en cada alerta**: top-3 motivos que dispararon la señal (confluencia explicada).
3. **🎲 Simulador paper** (`/simula LONG 83000`): plan hipotético + seguimiento sin dinero real.
4. **📉 Backtest de señales pasadas**: qué habría pasado operando las últimas 20 (con 2R).
5. **💤 Modo fin de semana**: umbrales más anchos + aviso de trampas de domingo.
6. **📊 Score de calidad A/B/C** por señal según confluencia.
7. **🌊 Mapa de liquidaciones estimado** (dónde están los stops = imán de precio).
8. **👑 Dominancia BTC / temporada alts** (BTCDOM).
9. **📅 Resumen semanal + modo exámenes** (`/pausa`).
10. **⚡ Respuesta instantánea real** (servidor 24/7 dedicado — proyecto aparte).
11. **⏱️ Ritmo 5-min 24/7** (decisión pendiente: espera máxima 5 min siempre).

*Regla del proyecto: uso personal, sin vender señales. La precisión publicada manda.*

## 📊 Dashboard (página, v7→v25, 12/10)
- v7 plegables + sonido por sesgo · v8 sparklines TF en vivo · v9 tema negro + fondo vivo
- v10 feed alertas + porqué + macro · v11 arena 🐋vs🐂 (bot guarda cinta en snapshot)
- v12 fondo según sesgo + vibración grado A + cuenta atrás · v13 niveles con glow + canal
- v14 melodía loop + beat · v15 fade + flash · v16 detector relativo · v17 warmup
- v18 overlay + testigo motor · v19 marcos + héroe glow · v20 blanco neutral · v21-v22 pulso solo con música
- v23 recarga 2 min · v24 ticker BTC 10s · v25 edad de datos en vivo
- Bot: PILAS en idioma techo/piso 🧱🛡 · anti-doble 90s (cadencia 2 min) · test hora fija (flake 02-03 UTC)

## 🧪 Entrenamiento 11/10 (3 semanas reales, 500x1H+200x4H)
- Volatilidad: mediana 0.144% · p90 0.51% · p99 1.34% → brusco 1.0% validado (p97)
- 2R disponible en 8h el 93% de las horas → plan factible
- Sesiones: NY 0.26% > Londres 0.25% > Asia 0.20% > noche 0.15% (ritmo NY confirmado)
- ADX4H: 52% tendencia / 36% chop
- Compresión NO adelanta expansión en 8h (0.61% vs 1.40% normal) → se reporta como "quieto"
- Veredicto: parámetros se mantienen; recalibración por datos en vivo (auto-calibración)

## 🏋️ Entrenamiento 2 (12/10, replay 8 meses, 832 pasos, funciones propias)
- Ritmo sweep: 0.4%→32.6% / 0.5%→29.5% / 0.6%→26.6% / 0.8%→28.0% → se queda 0.6 (menos ruido, igual filo)
- PILAS reacciona ≥0.3%/4h: psicológico 60% · S1 54% · R1 52% · NY 65% > Londres 63% > noche 61% > Asia 51%
- Castigo aplicado: LIQ/TOQUE solo a favor del sesgo (28→39% y 30→41%, sobre break-even 33%)
- Semilla de calibración medida en `SEMILLA_SESION` (los datos vivos la pisan al llegar)
- Peso semanal 2.0→1.0: +52% señales BAJA con igual filo (41.7→39.7%, n=48→58, 2.5 meses)
- Ajuste noche: DIR 28.6% <33% → noche exigente 1.1 (UMBRAL_CONF_SENAL 45→50 no gana: 38.6 vs 38.7, ER≥0.25 tampoco: 36.8)

## 🏋️ Entrenamiento 3 (12/10, replay 2 años 2024-10→2026-10, 2582 pasos)
- DIR 34.2% EV +0.03R · LIQ 26.8%→33.3% confluencia · TOQUE 33.2%→40.0% (EV +0.20R) · zonas reaccionan 55–65%
- Sesiones INESTABLES entre periodos (Londres 52.8→32.8, Asia 36.8→40.5) → semilla NEUTRA 1.0;
  solo los datos vivos (10+ evals) podrán sesgar. No sobreajustar es también entrenar.
## 🏋️ Entrenamiento 4 (12/10, walk-forward 4 años 2022-10→2026-10, 5500 pasos)
## 🏋️ Entrenamiento 5 (13/10, gates PILAS en 8 meses: momentum y régimen NO sirven)
## 🏋️ Entrenamiento 6 (13/10, intensivo walk-forward 4 años, 11.000 pasos c/3h)
## 🏋️ Entrenamiento 7 (13/10, mini-IA Naive-Bayes 4894 muestras, validada fuera de muestra)
## 🏋️ Entrenador local indeterminado (13/10, `entrenamiento/entrenador.py`)
- Rondas cada 30 min con datos frescos (DIR/LIQ/TOQUE/ZON/ER), panel `panel.html`, log `progreso.jsonl`
- Independiente del bot (solo importa funciones), sin secretos, sin Telegram/GitHub, UA genérico, STOP para parar
- Train 70% / test 30% temporales: top10% por score 25.3% vs base 29.3%, top33% 28.5% vs 29.3%
- Ningún contexto supera el ruido (mejor: h4t ALCISTA 34.7%)
- Veredicto: la mini-IA con solo-precio NO gana su lugar — rechazada, no se cablea. Forzar sin filo sería humo.
- 2R vs 1.5R: EV −0.07/−0.09 vs −0.15/−0.16 en ambas mitades → se queda 2R
- Conf 45–55 (n=20) y días de semana: sin filo estable (Sat flojo y Sun mejor, se contradicen)
- Sesiones×lado y zonas 2R: nada que adopte sin sobreajustar
- Veredicto: la config actual sobrevive al intensivo; no hay cambio que los datos pidan.
- Techo sin 1H alcista: 28.6% · piso sin 1H bajista: 29.6% (peor/igual que sin gate)
- Por régimen ADX: rango 27.8% vs tendencia 30.5% (sin diferencia útil)
- Veredicto: el fade PILAS vale por marcar niveles (reacción 60%), no por 2R. Sin cambios.
- TRAIN 2023-24 vs TEST 2024-26: DIR 29.6→30.0% (bajo break-even 33%, EV −0.10R) · DIR50 igual (no subir)
- LIQc 34.3→31.9% · TOQc 26.4→38.9% (inestable pero con confluencia sobrevive) · zonas 52–65% roca
- Ritmo-continuación pierde (17–22%): el ritmo avisa, no predice dirección sostenida
- Veredicto: el replay no tiene vetos institucionales (funding/taker/noticias/régimen) que sí
  tiene el vivo → el vivo debe batir al replay. Mandan las evals en vivo (siguen en 0).

## Noche del 21/22-10 (objetivo: precision de alertas + scorecard 9,0)
- **OOS de TODO octubre medido**: 127 decisiones / 189 muestras (analysis/backfill.py,
  baja solo el historico publico). Skill +0,0019 (marginal), banda >=0,80 = 88,8% real (n=89).
- **Disciplina de mitades**: A +0,031 / B -0,031; al mover la ventana un dia: -0,014
  -> el skill NO es estable -> no hay edge demostrado. Publicado tal cual.
- **Recalibracion Platt: rechazada** (colapsa a la tasa base; ECE 0,065 ya <= 0,08). Ver RECALIBRACION.md.
- **Alerta por rebote del nivel: rechazada** (10-26% de acierto). Aguanta = no rompe, no rebota.
- **Canal OOS en validation.json** (gate.canal vivo/oos/ninguno): el OOS purgado puede abrir
  la puerta con 100+ muestras, skill>0, ECE<=0,08; el vivo veta; la deriva debe estar ok.
  Hoy deriva 0,75 (alerta) -> la puerta sigue cerrada, correctamente.
- **Modo PRECISION** (VIGILANTE_PRECISION=1): aviso nivel defendido corto, sin plan, con
  precision medida; se autocensura con deriva o sin evidencia OOS. Ejecuta: nada.
- **Precision direccional medida** (1:1, 0,5% de riesgo): 37,3% (n=75) - la meta 60-70%
  no existe en los datos; mejor subconjunto 44% (n=9). Lo honesto manda.
- **Colector**: fallback Bybit etiquetado para top-traders (451 en IP de EE.UU.); la
  validacion solo se rompe por velas. Guardian anti-secretos en CI (tools/secret_scan.py).
- **Scorecard: 8,7 -> 8,9/10** (ponderado 8,875). Para 9,0 falta: skill estable en mitades
  consecutivas, deriva resuelta y cobertura real de top traders. Detalle en SCORECARD.md.

## 🧹 Depuracion de ruido (22/10, madrugada)
- **Medido sobre 9 dias reales de produccion** (historial de la rama estado, 175 alertas):
  la config actual (puerta + umbrales 1,5% + zones 24h + sin footprint) habria
  mandado **55 alertas: 18,8 -> 5,9 por dia** (-69%).
- Lo que mas ruido hacia: footprint (32 avisos repitiendo niveles, ya eliminado en
  produccion hoy), brusco+ritmo duplicando el mismo movimiento (16 de 36), zonas sin
  espera por nivel (30 -> 23 con 24h).
- **Nuevo: un movimiento = un aviso** (`VIGILANTE_RUIDO_UNIFICADO=1` por defecto):
  brusco y ritmo comparten ventana de 4h por direccion; el que dispara primero
  consume el enfriamiento del otro. Con flag=0 vuelve al independiente.
- Tests: +7 (699 en total). Proyeccion del ahorro real: ~0,1-1,5 alertas/dia segun
  la volatilidad del dia; el valor esta en que nunca se repite el mismo movimiento.

## Modelo re entrado y validado (23/10, `analysis/entrenar_hold.py`)
- **Walk-forward honesto, hecho dentro del repo** (stdlib puro, L1 C=0.03):
  11 folds de 90 dias con 365 de train y 24h de embargo -> **7.757 muestras OOS**,
  skill medio **+0,0168**, 10 de 11 folds positivos (racha 6).
- **Holdout octubre 2026** (nadie lo entreno): 198 muestras, **skill +0,0364**,
  ECE 0,025, PSI vivo-vs-OOS **0,157** (el modelo viejo daba -0,015 skill y 1,20 PSI).
- **Publicado `toques-wf-1`** en las 3 copias del modelo (hold_model.py,
  vigilante_cloud.py MODELO_TOQUES, modelo_toques.json). Coeficientes sparse:
  manda la hora/dia/volatilidad de 24h, no el precio.
- Recalibracion de intercepto (H2): **no aporto nada** -> revertida y documentada.
- Por lado: soporte +0,0575 · resistencia +0,0065 (holdout). Por regimen:
  compresion +0,031 · **expansion -0,029** (limite conocido: en alta volatilidad
  el modelo no sirve; queda documentado, no se oculta).

- [x] Modelo toques-wf-1 congelado (2026-10-24)