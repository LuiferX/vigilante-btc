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
- **🎯 Plan de entrada**: gatillo + stop + objetivo 2R + guardia de eventos + regla del 1%.
- **⛽ Combustible del día, ⚠️ funding extremo y 📈 mini-gráfico 24h** en cada parte.

## ⏰ Ritmo por sesiones (NY manda)

| Sesión | Ritmo | Qué manda |
|---|---|---|
| 📊 Pre-NY 13:00 UTC | 1 reporte | Detallado completo, 30 min antes de la apertura |
| ⚡ NY caliente 13–17 UTC | cada 5 min | Compacto en vivo; completo si hay alerta |
| 🌇 NY tarde 17–21 UTC | cada 15 min | Alertas + resumen de cierre 21:00 |
| 🌙 Madrugada | cada 2 h | Solo si hay alerta |
| 🌙 07:00 UTC (= 02:00 Colombia) | 1 | Resumen nocturno: cómo le fue a la noche |
- **💬 Compañero que conversa**: tono cercano con narrativa del "qué está pasando", memoria
  ("tercera vez que toca ese nivel hoy", "vs ayer +1.2%", "el funding se calentó"),
  mini-lecciones en cada parte, buenos días / mediodía / buenas noches.
- **⌨️ Chat en 2 vías (con retardo)**: escríbele `/precio`, `/direccion`, `/niveles`,
  `/miedo`, `/noticias`, `/eventos`, `/precision`, `/alerta 85000`, `/opere LONG entrada stop tp`,
  `/voy`, `/diario`, `/cerrar` y te responde en la siguiente pasada (máx ~30 min). Solo obedece a tu chat.
- **📓 Diario de trading + 🎯 alertas de precio + 🌊 detector de bruscos + 💵 DXY/SPX +
  🔢 psicológicos con re-test + 📉 divergencias RSI**.
- **🏛️🆚🧍 Instituciones vs minoristas + 🏦 análisis Coinbase** (premium USA, peso de su
  volumen y muros del libro): quién quiere qué, con veredicto.
- **🐋 Cinta de ballenas + 🧲 imanes Deribit + 🥇 oro vs BTC + 📊 long/short global +
  😨😊 pulso de titulares + 🌙 rango asiático + 🧠 auto-aprendizaje por sesión**.
- **🏛️ Institucional**: score A/B/C + filtro de régimen (ADX), blackout en eventos High,
  guardia de datos viejos, CVD con divergencias, auditoría (motivo+grado por señal) y
  `backtest.py` (repite tu historial con la regla actual: in-sample vs out-of-sample).
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