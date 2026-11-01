# Archivo de microestructura — qué es y por qué existe

**Resumen:** la API pública de Binance solo sirve **~30 días** de histórico de
Open Interest, taker buy/sell y ratios de ballenas (probado: `startTime` de 31
días → HTTP 400). Todo lo que no se archive **se pierde para siempre**. Este
directorio es el archivo durable: crece solo, todos los días.

## Qué contiene

| Archivo | Series (5 m) | Cobertura inicial (2026-11-01) |
|---|---|---|
| `oi.jsonl` | `sumOpenInterest`, `sumOpenInterestValue` | 30 días |
| `taker.jsonl` | `buySellRatio`, `buyVol`, `sellVol` | 30 días |
| `top_cuentas.jsonl` | ratio de cuentas top largo/corto | 30 días |
| `top_posiciones.jsonl` | ratio de posiciones top largo/corto | 30 días |
| `global_cuentas.jsonl` | ratio global de cuentas | 30 días |
| `funding.jsonl` | `fundingRate` cada 8 h | **1.666 días (4,6 años)** |

Nota de tipos: la API devuelve los valores numéricos como **cadenas**
(`"sumOpenInterest": "96960.331"`). El archivo guarda el valor tal cual para no
perder precisión: **cualquier consumidor debe hacer `float(...)`** (el mismo
bug de tipos que ya rompió un script de diagnóstico).

## Cómo se usa

```bash
python analysis/archivo_micro.py --estado        # cobertura actual
python analysis/archivo_micro.py --diario        # lo que corre el workflow
python analysis/archivo_micro.py --todo          # backfill completo (30d / 4y)
python analysis/archivo_micro.py --serie o       # una sola serie
python analysis/archivo_micro.py --recompactar   # reordena/dedup sin red
```

## Invariantes (con tests en `analysis/test_archivo_micro.py`)

1. **Idempotente**: correrlo dos veces no duplica ni borra nada.
2. **Orden canónico**: el archivo queda **ordenado por timestamp y sin
   duplicados**. No es cosmético: los consumidores hacen `bisect` y un archivo
   desordenado da resultados silenciosamente falsos.
3. **Escritura atómica**: se escribe a `.tmp` y se renombra; un corte a mitad no
   corrompe el archivo.
4. **Líneas corruptas se conservan**: nunca se pierde información.
5. **La paginación respeta el contrato real de la API** (filas ascendentes: el
   más viejo es `raw[0]`). Usar `raw[-1]` provocaba un bucle infinito real, ya
   corregido y fijado con test.

## Automatización

`.github/workflows/archivo.yml` corre una vez al día, baja el corte, lo ordena
y lo commitea en `main` (con reintentos de push). El archivo se versiona a
propósito: es un activo irrecuperable si se pierde.

## Crecimiento

~720 filas por serie y día (a 5 m) ≈ 45 KB/serie/día ≈ 1,3 MB/mes por serie.
Si en el futuro hace falta compactar: mantener 5 m los últimos 90 días y
agregar a 1 h lo anterior, con el mismo formato y una nota de procedencia.

## Para qué servirá

Con 30 días de microestructura no se puede investigar; con 12 meses sí. Este
archivo es la condición previa para testear hipótesis de posicionamiento
(cascadas de liquidación, crowding, absorción) que hoy son imposibles — la
familia H2 de la investigación quedó *no concluyente* precisamente por falta de
estos datos.
