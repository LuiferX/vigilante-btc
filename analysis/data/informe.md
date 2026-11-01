# Informe de inteligencia — 2026-11-01 07:03 UTC

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

**Lectura cruzada:** el OI en contratos está en el percentil 80, pero el OI **en dólares** en el 12. Si el primero es alto y el segundo bajo, hay el mismo interés abierto sobre un precio menor: apalancamiento más frágil, no más grande.

## 5. Estado del sistema

| Archivo | Filas |
|---|---:|
| funding | 5000 |
| global_cuentas | 8931 |
| oi | 8931 |
| taker | 8915 |
| top_cuentas | 8931 |
| top_posiciones | 8931 |

- Muestra efectiva: **84**
- Skill OOS: 0.026 · ECE 0.0144 · PSI 0.2165
- Gate: `oos` · estado `muestra_media`

---

Marcador de edge (veredicto de la investigación, no opinión): en este marco (velas 5 m, hold 4-72 h, coste ~0,2 % por viaje) **no hay edge direccional demostrado** en ninguna de las seis familias medidas — H1 funding, H3 rebote afinado, H4 entrada rediseñada, H5 ruptura, H6 horizontes largos. Detalle y datos en `analysis/EXPERIMENTOS.md` y `docs/audit/`.
