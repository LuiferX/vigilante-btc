# Informe de inteligencia â€” 2026-11-06 12:31 UTC

> Este informe **no opera**: mide y publica. No contiene objetivos, stops ni planes de entrada.

## 1. Posicionamiento (percentil causal, sin look-ahead)

| Serie | Valor | Percentil | Lectura | Obs | Ventana |
|---|---:|---:|---|---:|---:|
| funding | 0.0001 | 100.0 % | alto | 1201 | 400 d |
| global_cuentas | 2.5398 | 94.0 % | normal | 8641 | 30 d |
| oi | 96791.1 | 80.3 % | normal | 8641 | 30 d |
| oi_valor | 7.5258e+09 | 11.9 % | normal | 8641 | 30 d |
| taker | 8.9457 | 100.0 % | alto | 8625 | 30 d |
| top_cuentas | 2.6887 | 94.0 % | normal | 8641 | 30 d |
| top_posiciones | 1.6986 | 50.3 % | normal | 8641 | 30 d |

> **Caveat honesto:** cuando el Ãºltimo pago de funding es exactamente la tasa por defecto (+0,0001, que agrupa ~27 % de los pagos), el percentil marca 100 % **sin que sea un extremo real**. Es un empate masivo, no una seÃ±al. El motor ya descuenta esto en la investigaciÃ³n (H1); aquÃ­ se declara para que no se lea como 'funding en mÃ¡ximos'.

**Lectura cruzada:** el OI en contratos estÃ¡ en el percentil 80, pero el OI **en dÃ³lares** en el 12. Si el primero es alto y el segundo bajo, hay el mismo interÃ©s abierto sobre un precio menor: apalancamiento mÃ¡s frÃ¡gil, no mÃ¡s grande.

## 2. Integridad de datos (3 exchanges)

| Exchange | Precio | Edad (s) | Estado |
|---|---:|---:|---|
| Binance | None | None | caído (HTTPError: HTTP Error 451: ) |
| OKX | 76309.8 | 0.9 | OK |
| Bybit | None | None | caído (HTTPError: HTTP Error 403: F) |

**Veredicto: `no_concluyente`** — solo 1 exchange(s) respondieron (Binance, Bybit fallo)

> Si dos exchanges discrepan más del 0,5 % o hay un flash crash, el resto de las cifras de este informe deben leerse con reserva: los datos que las alimentan no serían fiables.

## 3. Sesiones (Tokio / Londres / NY, 4 años de velas 5m)

| Sesión (UTC) | Rango med. | Rango p90 | Hace el **máx** del día | Hace el **mín** del día |
|---|---:|---:|---:|---:|
| Asia | 0.108 % | 0.268 % | 34.7 % | 37.2 % |
| Londres | 0.111 % | 0.273 % | 15.9 % | 14.1 % |
| solape | 0.199 % | 0.477 % | 17.4 % | 16.4 % |
| NY | 0.147 % | 0.373 % | 15.5 % | 17.9 % |
| noche | 0.117 % | 0.311 % | 16.4 % | 14.4 % |

**Rango asiático (00-08 UTC):** mediana 1.4092 % (p25 0.9386 %, p75 2.1195 %) sobre 1398 días. La sesión de Londres lo barre el **49 %** de los días; medido en H7, y **ninguno de los dos lados** (reversión ni continuación) paga el peaje de 0,23 %.

## 4. Estructura histÃ³rica (4 aÃ±os de velas 5m)

Historia medida: **402629 velas**, 2023-01-01 â†’ 2026-10-30. Un *toque* es una visita distinta (entra, sale 0,3 % y vuelve â‰¥1 h despuÃ©s); *aguanta* = ningÃºn cierre 0,5 % mÃ¡s allÃ¡ en 4 h (el target del modelo).

### Cerca del precio (los que de verdad importan hoy)

| Nivel | Lado | Toques 4a | Aguanta | Rebote med. | Barrido med. | Distancia |
|---|---|---:|---:|---:|---:|---:|
| 77,459 | soporte | 202 | 19.3 % | 0.449 % | 0.645 % | -4.79 % |
| 84,280 | resistencia | 250 | 17.2 % | 0.474 % | 0.677 % | +3.59 % |
| 84,528 | resistencia | 202 | 16.3 % | 0.468 % | 0.743 % | +3.90 % |

### Los mÃ¡s respetados de la historia

| Nivel | Toques | Aguanta | Rebote | Barrido | Distancia |
|---|---:|---:|---:|---:|---:|
| 29,256 | 109 | 45.9 % | 0.383 % | 0.423 % | -64.0 % |
| 29,428 | 87 | 35.6 % | 0.369 % | 0.473 % | -63.8 % |
| 29,168 | 119 | 34.5 % | 0.437 % | 0.320 % | -64.1 % |
| 26,050 | 119 | 34.5 % | 0.494 % | 0.471 % | -68.0 % |
| 30,239 | 138 | 31.9 % | 0.450 % | 0.413 % | -62.8 % |

**Lectura honesta:** en los niveles mÃ¡s probados, el rebote mediano y el barrido mediano son casi iguales (0.427 % vs 0.420 %). Las excursiones a ambos lados del nivel son simÃ©tricas: el precio no *respeta* estos niveles tanto como los atraviesa. Es la firma matemÃ¡tica de por quÃ© la investigaciÃ³n no encontrÃ³ edge aquÃ­.

## 5. Estado del sistema

| Archivo | Filas |
|---|---:|
| funding | 5068 |
| global_cuentas | 10469 |
| oi | 10468 |
| taker | 9423 |
| top_cuentas | 10469 |
| top_posiciones | 10469 |

- Muestra efectiva: **84**
- Skill OOS: 0.026 Â· ECE 0.0144 Â· PSI 0.2165
- Gate: `oos` Â· estado `muestra_media`

---

Marcador de edge (veredicto de la investigaciÃ³n, no opiniÃ³n): en este marco (velas 5 m, hold 4-72 h, coste ~0,2 % por viaje) **no hay edge direccional demostrado** en ninguna de las seis familias medidas â€” H1 funding, H3 rebote afinado, H4 entrada rediseÃ±ada, H5 ruptura, H6 horizontes largos. Detalle y datos en `analysis/EXPERIMENTOS.md` y `docs/audit/`.
