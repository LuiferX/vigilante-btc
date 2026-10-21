# Trading Data Collector

Recolector de datos publicos de trading para GitHub Actions. No usa claves ni ejecuta ordenes.

## Que recoge

- Binance Futures (endpoints publicos, sin claves):
  - Funding rate.
  - Open interest (5m).
  - Ratios long/short (global, top cuentas, top posiciones).
  - Taker buy/sell.
  - Velas 5m (1500), 1h (1000), 4h (500) y 1D (200).
- Noticias RSS: CoinDesk, Cointelegraph, Bitcoin Magazine.

## Como funciona

- `collector.py` hace append a `data/btcusdt/*.jsonl` con dedup por clave.
- GitHub Actions lo ejecuta cada hora (`cron: 17 * * * *`) y commitea solo si hay datos nuevos.
- Si Binance Futures responde 451/403 desde la IP del runner, las velas usan fallback en cadena:
  Binance Vision (spot), Bybit linear y Kraken XBTUSD.
- Funding, open interest, long/short global y taker usan fallback oficial de OKX cuando Binance falla.
  Los ratios de top traders siguen siendo Binance-only y pueden quedar atrasados; el health lo muestra.
- Solo se guardan velas cerradas: la vela en curso se descarta hasta que cierre.
- `data/health.json` registra por job: fuente, filas traidas, filas nuevas, error y ultima clave.
- Retencion: `klines_5m.jsonl` se recorta a 200.000 lineas y `news.jsonl` a 5.000 para que el repo no crezca sin limite.
- El job falla solo si no pudo traer ninguna vela; los fallos parciales quedan visibles en `health.json`.

## Legal / uso

- Solo endpoints publicos y feeds RSS.
- Sin scraping de HTML, sin saltar limites, sin claves.
- Uso personal/investigacion. Si vas a monetizar o redistribuir, revisa los terminos de cada fuente.

## Uso local

```bash
python collector.py
```

## Estructura

```text
data/
  health.json
  btcusdt/
    funding.jsonl
    open_interest.jsonl
    global_ls.jsonl
    top_ls_account.jsonl
    top_ls_position.jsonl
    taker_ls.jsonl
    klines_5m.jsonl
    klines_1h.jsonl
    klines_4h.jsonl
    klines_1d.jsonl
    news.jsonl
```

## Caveat de fuentes

Si se activa el fallback, las velas nuevas pueden ser spot (Binance Vision/Kraken) y las historicas
futures. Sirve para niveles y contexto; no para basis exacto ni para arbitraje. Cada registro trae
`source` para auditar la mezcla.
