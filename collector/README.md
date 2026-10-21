# Trading Data Collector

Recolector de datos públicos de trading para GitHub Actions.

## Qué recoge
- Binance Futures (endpoints públicos, sin claves):
  - Funding rate
  - Open interest (5m)
  - Ratios long/short (global, top cuentas, top posiciones)
  - Taker buy/sell
  - Velas 5m (1500), 1h (1000), 4h (500) y 1D (200)
- Noticias RSS: CoinDesk, Cointelegraph, Bitcoin Magazine

## Cómo funciona
- `collector.py` hace append a `data/btcusdt/*.jsonl` con dedup por clave.
- GitHub Actions lo ejecuta cada hora (`cron: 17 * * * *`) y commitea solo si hay datos nuevos.

## Legal / uso
- Solo endpoints públicos y feeds RSS.
- Sin scraping de HTML, sin saltar límites, sin claves.
- Uso personal/investigación. Si vas a monetizar o redistribuir, revisa los términos de cada fuente.

## Uso local
```bash
python collector.py
```

## Estructura
```text
data/btcusdt/
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