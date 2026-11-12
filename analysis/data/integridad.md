# Integridad de datos — corte multi-exchange

Generado: 2026-11-12 13:18:32 UTC

| Exchange | Precio | Edad (s) | Estado |
|---|---:|---:|---|
| Binance | None | None | caído (HTTPError: HTTP Error 451: ) |
| OKX | 72532.4 | 0.8 | OK |
| Bybit | None | None | caído (HTTPError: HTTP Error 403: Forbi) |

**Veredicto: `no_concluyente`** — solo 1 exchange(s) respondieron (Binance, Bybit fallo)

> Esto no opera: mide si los datos que alimentan el informe son coherentes. Si dos exchanges discrepan más del 0,5 % o hay un flash crash (≥2 % en 5 min), el informe marca sus datos como no fiables en lugar de publicar cifras tranquilas.
