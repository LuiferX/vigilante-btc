# 🤖 Vigilante BTC Cloud

Vigilante de **BTCUSDT** multi-timeframe (**1H · 4H · 1D · 1S** semana) que corre en la nube
(GitHub Actions) y envía un parte a **Telegram** cada 30 minutos durante las sesiones de Londres y Nueva York.

> Diseñado como herramienta educativa y de análisis. **No** ejecuta órdenes, no toca tu dinero
> y usa **solo la API pública** de Binance (sin API keys).

## 🔍 Qué analiza (v3)

| Marco | Señales |
|---|---|
| **1H** | EMA20/50, pendiente, RSI, **MACD**, **estructura HH/HL-LH/LL**, volumen relativo, compresión, ATR |
| **4H** | Ídem + cierre de vela y momento |
| **1D** | Ídem + pivotes diarios (S2/S1/P/R1/R2) |
| **1S** | Tendencia macro semanal + pivotes semanales |

- **Dirección probable** con % de confianza (>25% de señal = sesgo definido).
- **Soportes y resistencias reales**: fractales de 14 velas por marco + pivotes diario y semanal.
- **Sentimiento de futuros**: funding rate, open interest y ratio taker long/short.
- **Régimen de volatilidad**: percentil de ATR (vivo/dormido).
- **Momento probable**: distancia en horas por ATR, próxima apertura de sesión, cierre 4H, compresión.
- **🚨 Alertas inteligentes**: solo escribe si hay señal (cambio de dirección, confianza alta,
  toque de nivel) + resumen en aperturas de Londres/NY. Sin ruido.
- **😨🤑 Miedo/Codicia 0-100**: RSI 1D, funding, taker L/S, volatilidad, tendencia, 24h.
- **📰 Noticias con peso**: prensa crypto filtrada por impacto real en BTC, cada una explicada
  en simple + impacto estimado (rango histórico de referencia, **no** predicción).
- **🗓 Eventos futuros**: calendario macro EE.UU. (FOMC, CPI, empleo...) con cuenta regresiva.
- **🎯 Precisión calibrada**: sin señales duplicadas (1 por dirección cada 4 h), umbral de acierto
  relativo al ATR y % visible solo con muestra mínima (5 señales).
- **📐 Evaluación MFE/MAE**: cada señal se juzga por excursión (¿tocó el 2R antes que el stop?,
  el stop manda en la misma vela) con vectores mfe/mae guardados para futura correlación.
- **🎯 Plan de entrada**: gatillo + stop + objetivo 2R + guardia de eventos + regla del 1%.
- **⚠️ Funding extremo** cuando un lado va recargado (lectura contrarian).
## ⏰ Ritmo por sesiones (NY manda)

| Sesión | Ritmo | Qué manda |
|---|---|---|
| 📊 Pre-NY 13:00 UTC | 1 reporte | Detallado completo, 30 min antes de la apertura |
| ⚡ NY 13–20 UTC (hasta las 3pm Col) | cada 15 min | Solo eventos: cambio, brusco, liquidez, día ±2%, tu precio |
| 🌇 Cierre 21 UTC + madrugada | 21 + cada 2 h | Alertas + resumen nocturno 02:00 tu hora |
| 🌙 Madrugada | cada 2 h | Solo si hay alerta |
| 🌙 07:00 UTC (= 02:00 Colombia) | 1 | Resumen nocturno: cómo le fue a la noche |
- **💬 Compañero que conversa**: tono cercano con narrativa del "qué está pasando", memoria
  ("tercera vez que toca ese nivel hoy", "vs ayer +1.2%", "el funding se calentó"),
  buenos días / pre-NY / nocturnos.
- **⌨️ Chat en 2 vías (con retardo)**: `/precio /direccion /niveles /miedo /noticias /eventos
  /precision /manos /calidad /detalle /papel /alerta /opere /voy /diario /cerrar`.
  Responde en la siguiente pasada. Solo obedece a tu chat.
- **📡 Oyente cada 5 min**: los comandos se responden en ≤5 min día y noche con la última
  foto del mercado + precio en vivo. `/detalle` pide el parte completo en la próxima pasada.
- **📓 Diario de trading + 🎯 alertas de precio + 🌊 detector de bruscos + 💵 DXY/SPX +
  🔢 psicológicos con re-test + 📉 divergencias RSI**.
- **💵 `/papel` invisible**: el bot opera solo con $10,000 virtuales (riesgo 1%,
  penalizado a 0.5% tras 3 pérdidas seguidas). Solo visible con `/papel`.
- **🏛️🆚🧍 Instituciones vs minoristas + 🏦 análisis Coinbase** (premium USA, peso de su
  volumen y muros del libro): quién quiere qué, con veredicto.
- **📰 Noticias direccionales**: presión neta (-100..+100), viento a favor/en contra
  de la técnica y escenarios por evento (ALTO=baja/BAJO=sube cuando hay pronóstico).
- **📊 Dashboard web**: página gratis (GitHub Pages, rama `dashboard`) con precio+alertas,
  confianza, banco papel y precisión. Se regenera sola cada pasada. Requiere activarla
  1 vez en Settings → Pages (rama `dashboard`).
- **⚠️ EYY PILAS**: vigila zonas mayores de largo plazo (semanales, psicológicos, imanes)
  y avisa corto cuando el precio llega: lado del rebote + anulación (1 vez por zona al día).
- **🔄 Modo DELTA**: el mercado muestra solo lo que cambió desde tu último parte.
- **🐋 Cinta de ballenas + 🧲 imanes Deribit + 🥇 oro vs BTC + 📊 long/short global +
  🌊 CVD con divergencias + 🧠 auto-aprendizaje por sesión**.
- **🏛️ Institucional**: score A/B/C + filtro de régimen (ADX, MACD neutralizado en rango),
  veto premium USA/DXY (degrada), blackout en eventos High, guardia de datos viejos,
  auditoría (motivo+grado por señal) y `backtest.py` (in-sample vs out-of-sample).
- **Robustez**: reintentos ante fallos de API, espejo de datos si Binance bloquea la red,
  degradación elegante y aviso a Telegram si algo falla.

## 📦 Componentes

```
vigilante_cloud.py               # análisis + envío a Telegram (Python stdlib, 0 dependencias)
.github/workflows/vigilante.yml  # cron cada 30 min (07:00-21:00 UTC) + disparo manual
```

## 🛡️ Seguridad

- Solo lectura de `fapi.binance.com` (velas y ticker, endpoints públicos sin autenticación).
- El **token del bot** y el **chat ID** viven en *Secrets* del repositorio (GitHub Actions),
  **nunca** en el código.
- Sin API keys de Binance → no hay nada que robar; el bot no puede operar.

## ⚠️ Aviso

Análisis **probabilístico** basado en precio y volumen. No es asesoramiento financiero.
El trading con apalancamiento conlleva riesgo de pérdida del capital.

---
*Proyecto educativo construido paso a paso. 🎓*

## Licencia y uso

(C) 2026 LuiferX - **uso personal y privado unicamente** (ver \LICENSE\).
Prohibida la copia, redistribucion o uso comercial. Ver el codigo no otorga derecho de uso.
