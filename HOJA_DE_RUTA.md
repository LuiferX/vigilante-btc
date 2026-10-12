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
- Ajuste noche: DIR 28.6% <33% → noche exigente 1.1 (UMBRAL_CONF_SENAL 45→50 no gana: 38.6 vs 38.7, ER≥0.25 tampoco: 36.8)

## 🏋️ Entrenamiento 3 (12/10, replay 2 años 2024-10→2026-10, 2582 pasos)
- DIR 34.2% EV +0.03R · LIQ 26.8%→33.3% confluencia · TOQUE 33.2%→40.0% (EV +0.20R) · zonas reaccionan 55–65%
- Sesiones INESTABLES entre periodos (Londres 52.8→32.8, Asia 36.8→40.5) → semilla NEUTRA 1.0;
  solo los datos vivos (10+ evals) podrán sesgar. No sobreajustar es también entrenar.
## 🏋️ Entrenamiento 4 (12/10, walk-forward 4 años 2022-10→2026-10, 5500 pasos)
- TRAIN 2023-24 vs TEST 2024-26: DIR 29.6→30.0% (bajo break-even 33%, EV −0.10R) · DIR50 igual (no subir)
- LIQc 34.3→31.9% · TOQc 26.4→38.9% (inestable pero con confluencia sobrevive) · zonas 52–65% roca
- Ritmo-continuación pierde (17–22%): el ritmo avisa, no predice dirección sostenida
- Veredicto: el replay no tiene vetos institucionales (funding/taker/noticias/régimen) que sí
  tiene el vivo → el vivo debe batir al replay. Mandan las evals en vivo (siguen en 0).
