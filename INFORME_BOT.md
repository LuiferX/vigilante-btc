# 🤖 INFORME COMPLETO — Vigilante BTC (12/10/2026)

> Bot personal de LuiferX. BTCUSDT, estilo swing, multi-temporalidad 1H·4H·1D·1S.
> **No opera dinero real.** Todo verificado contra el código (`vigilante_cloud.py` v6).

---

## 1. Qué es y qué no es

- **Es:** un analista autónomo en la nube que vigila BTCUSDT 24/7, avisa solo lo importante
  por Telegram y publica una página de estado. Aprende midiendo su propia precisión.
- **No es:** un ejecutor (no compra/vende), un asesor financiero, un vendedor de señales.
- **Su jefe:** tú. Él propone con evidencia; tú decides y operas manual (ej. tus $10 en BingX).

## 2. Arquitectura (dónde vive cada cosa)

| Pieza | Dónde | Qué hace |
|---|---|---|
| `vigilante_cloud.py` (v6) | Rama `main` | Cerebro: análisis + Telegram + memoria |
| `comandos.py` + `oyente.yml` | Rama `main` | Oye tus comandos de Telegram cada 1 min (24/7) |
| `dashboard.py` + `dashboard` (rama) | GitHub Pages | Página pública auto-generada (v26) |
| `estado` (rama) | Reescritura limpia | Memoria: `estado.json` + `historial.jsonl` |
| cron-job.org (3 jobs) | Tu cuenta | Dispara: NY c/5 min (13–20 UTC), resto c/15, oyente c/1 min |
| `test_vigilante.py` (185 tests) + `test.yml` | CI | Calidad en cada push |

## 3. Fuentes de datos (todas públicas, solo lectura)

- **Binance futuros** (`fapi.binance.com`): velas 1H/4H/1D/1S, funding, OI, taker long/short, cinta aggTrades (ballenas ≥5 BTC).
- **Espejo** (`data-api.binance.vision`): respaldo si bloquean + sparklines/ticker en vivo de la página.
- **Coinbase** (spot + libro): premium USA = demanda institucional.
- **Deribit**: strikes con más Open Interest = imanes de precio + put/call.
- **Noticias RSS** (7 medios: Cointelegraph, Cryptoslate, Decrypt, Bitcoin Magazine, Bitcoinist, Watcher.Guru, TheBlock): presión −100…+100.
- **Dominancia** (CoinGecko global, gratis): % BTC/ETH + temporada.
- **Macro** (ForexFactory): eventos High/Medium con cuenta atrás.
- **Yahoo**: DXY, SPX, oro.

## 4. Qué evalúa en cada pasada (orden real)

1. Velas 1H/4H/1D/1S → tendencia, RSI, MACD, ADX/régimen, ATR, compresión.
   Modelos: Efficiency Ratio (>0.5 tendencia real, <0.25 chop — medido p90 0.44 en 1000 velas),
   z-score ±2σ (estiramiento: consejo, no señal — revierte 30% vs continúa 22%), ritmo 30 min,
   Hurst descartado en ventana corta (sesgo probado, no se publica humo).
2. Niveles (soportes/resistencias: mínimos/máximos 14v + pivotes) y zonas PILAS (semanales, diarias, psicológicos, imanes).
3. Dirección + confianza, score A/B/C, veto premium/DXY, blackout ±30 min de eventos High.
4. Sentimiento: funding, taker, miedo/codicia 0–100, smart money (instituciones vs minoristas), ballenas, CVD/divergencias, long/short, mapa de liquidez.
5. Evalúa pendientes vencidas (MFE/MAE a 8h), revisa papel y diario, decide si avisa, guarda estado.

## 5. Motor de alertas (anti-spam por capas)

| Alerta | Condición | Cooldown |
|---|---|---|
| Cambio de dirección | sesgo nuevo ALZA/BAJA, conf ≥40 | inherente (edge) |
| Señal fuerte | conf ≥55 | 4 h por sesgo |
| Movimiento brusco | ±1%/1h | 2 h por dirección |
| Toma de liquidez | barrido máx/mín 24h con devolución, solo a favor del sesgo | 4 h por lado |
| Día NY | mueve ≥2% | 1/día |
| EYY PILAS 🧱🛡 | a ≤0.35% de zona mayor | 1/día por zona |
| Toque nivel | ≤0.25%, solo a favor del sesgo | 4 h por nivel |
| Ruptura confirmada | cierre 1H más allá de soporte/resistencia | 12 h por nivel |
| Pre-evento | aviso único 15–60 min antes de High (con historial medido) | 1/día por evento |
| Señales (precisión/paper) | conf ≥45 / papel ≥35 | dedup 4 h por sesgo |
| Briefs | madrugada 07 · mañana 08 · pre-NY 13–13:30 · noche 2–3 UTC | 1/día c/u |
| Anti-doble | pasada <90 s de la anterior | se omite el parte |

**Invalidación EYY:** la dice el propio mensaje — se anula SOLO con cierre 1H más allá del nivel
(🧱 techo: sobre la resistencia · 🛡 piso: bajo el soporte). La mecha que pincha y vuelve no anula.

## 6. Reporte de mensajes (lo que te llega)

**Parte (ejemplo de estructura):** motivo 🚨 + intro + `VEREDICTO` (sesgo, conf, calidad, precio, objetivo)
+ marcos 1H/4H/1D/1S + narrativa + soportes/resistencias + memoria (toques que debilitan, vs ayer,
divergencias, funding) + `MERCADO` (solo lo que cambió: miedo, futuros, dólar, instituciones,
Coinbase, ballenas, imanes, oro, cuentas, CVD, liquidez, noticias) + `CONTEXTO` (noticias nuevas,
próximos eventos con escenarios) + `PLAN` (gatillo = cierre 1H, stop, objetivo 2R, guardia de evento, riesgo 1%).

**Comandos (2 vías, responde el oyente):**
`/precio /direccion /niveles /miedo /noticias /eventos /precision /manos /alerta /alertas /borrar`
`/opere /voy /diario /cerrar /calidad /detalle /papel /simula` (+ `/pausa` según hoja de ruta).

**Lo que NUNCA hace:** operar, pedir claves, prometer ganancias, avisar sin cambio real.

## 7. Paper trading + diario (invisible, sin avisos)

- Banco virtual $10.000 · abre con señales 35%+ · riesgo 1% (0.5% tras 3 pérdidas seguidas,
  Half-Kelly acotado [0.25%, 2%] cuando haya 10+ cerradas) · Sharpe por operación en la página (n≥5).
- Frenos: −10% desde pico · −3% en el día. Cierres por SL/TP en 1H.
- Tu diario (`/opere…/cerrar`) va aparte: tus operaciones reales, tu responsabilidad.
- **Estado hoy:** sin estrenar (mercado lateral, conf máx ~31 < 35). Cuando opere, sale en la página.

## 8. Precisión (cómo aprende)

- Cada señal ALZA/BAJA ≥45% se evalúa a 8h: gana si el objetivo 2R se toca antes que el stop (empate → stop).
- Muestra % con mínimo 5 evaluadas; sin datos dice `s/d` (no inventa).
- **Estado hoy:** 0 evaluadas, 0 pendientes. Calibración automática dormida hasta 10+ por sesión (regla: no ajustar con chop).

## 9. Página (v26, pública, sin secretos)

14 tarjetas plegables: precio+sesgo, curva con niveles, confianza, temporalidades en vivo,
miedo+reloj NY, contexto, porqué, duelo 🐋vs🐂, macro, alertas, operaciones, banco, precisión,
actividad + banner de última alerta. Ticker BTC cada 10 s, recarga 2 min, melodía opcional al beat,
fondo negro vivo. No expone tokens, chats ni tus operaciones reales.

## 10. Seguridad

Solo lectura pública · secretos en GitHub Actions Secrets · nada en código (verificado) ·
tokens revocables · sin ejecución de dinero · uso personal.
Protocolos: `guardia_lectura()` (fail-closed: se niega a arrancar si detecta claves de trading),
comandos solo del dueño (verifica chat), tope 20 alertas + rango sensato, cero rutas de órdenes en código.

## 11. Umbrales clave

`CONF 45 registra / 55 fuerte / 40 cambio · papel 35 · TOQUE 0.25% · BRUSCO 1%/1h · NY 2% ·`
`PILAS 0.35% · EVAL 8h · blackout ±30 min High · anti-doble 90 s · papel 1% / frenos −10% pico, −3% día`
