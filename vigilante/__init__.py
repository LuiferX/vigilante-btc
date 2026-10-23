#!/usr/bin/env python3
"""
vigilante/ - paquete del bot (Fase 1 de modularizacion).

Objetivo: sacar la matematica pura y los modulos independientes del monolito
`vigilante_cloud.py` (5.820 lineas) sin romper la API publica que usan
`test_vigilante.py`, `comandos.py` y los workflows: esos nombres siguen
viviendo en `vigilante_cloud.py` via re-export.

Modulos:
  indicadores.py  matematica pura (indicadores,迟culos, utilidades). Sin red,
                 sin estado, sin I/O.

Reglas del refactor (ver SCORECARD.md):
  - extraer de hoja a raiz: primero lo puro, luego lo que depende de red.
  - `fetch`, `klines`, `ticker24`, `sentiment`, `send_telegram` y
    `coinbase_premium` se quedan en la raiz: los tests los parchean por nombre
    (`v.fetch = ...`) y dos aserciones leen su texto fuente.
  - imports absolutos (`from vigilante.indicadores import ...`), nunca relativos.
  - el esquema de estado.json es API publica: no se renombra.
"""

from vigilante.indicadores import *  # noqa: F401,F403
