# 🤖 Vigilante BTC Cloud

Vigilante de **BTCUSDT** multi-timeframe (**1H · 4H · 1D · 1S** semana) que corre en la nube
(GitHub Actions) y envía un parte a **Telegram** cada 30 minutos durante las sesiones de Londres y Nueva York.

> Diseñado como herramienta educativa y de análisis. **No** ejecuta órdenes, no toca tu dinero
> y usa **solo la API pública** de Binance (sin API keys).

## 🔍 Qué analiza (v2 PRO)

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
- **Robustez**: reintentos ante fallos de API, degradación elegante y aviso a Telegram si algo falla.

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