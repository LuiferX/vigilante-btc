#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_health.py -> check_salud.py: Â¿sigue viva la maquina de analisis?

REARME 2026-11-01: antes comprobaba "que exista una decision reciente", cosa
del bot que operaba. Ahora la maquina NO opera: mide y publica. Lo critico ya
no es una decision, es que los DATOS sigan llegando y el informe este al dia.

Comprueba, con umbrales explicados:
  - cada serie del archivo de microestructura tenga un registro reciente
    (las series son de 5 min; se permite 1 dia de margen porque el workflow
    corre a diario, y 2 dias ya es fracaso)
  - analysis/data/informe.json se haya regenerado en las ultimas 26 h
  - analysis/data/percentiles_hoy.json Ã­dem

Salida: JSON por stdout con ok/detalle. Codigo 1 si algo critico falla.

Uso: python analysis/check_health.py
"""

from __future__ import annotations

import datetime
import json
import os

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(AQUI, "data", "archivo")

# serie -> (archivo, clave de tiempo, horas maximas permitidas)
SERIES = {
    "funding": ("funding.jsonl", "fundingTime", 26),
    "oi": ("oi.jsonl", "timestamp", 26),
    "taker": ("taker.jsonl", "timestamp", 26),
    "top_cuentas": ("top_cuentas.jsonl", "timestamp", 26),
    "top_posiciones": ("top_posiciones.jsonl", "timestamp", 26),
    "global_cuentas": ("global_cuentas.jsonl", "timestamp", 26),
}
SALIDAS = {
    "informe": (os.path.join(AQUI, "data", "informe.json"), 26),
    "percentiles": (os.path.join(AQUI, "data", "percentiles_hoy.json"), 26),
}


def edad_horas(path: str, campo: str):
    """Horas desde el ultimo registro del archivo. None si no existe."""
    if not os.path.exists(path):
        return None
    ultimo = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                r = json.loads(linea)
            except Exception:
                continue
            t = r.get(campo)
            if t is None:
                continue
            try:
                t = int(t)
            except (TypeError, ValueError):
                continue
            if ultimo is None or t > ultimo:
                ultimo = t
    if ultimo is None:
        return None
    return (datetime.datetime.now(UTC).timestamp() * 1000 - ultimo) / 3_600_000


def main() -> int:
    ahora = datetime.datetime.now(UTC)
    fallos = []
    detalle = {}

    for nombre, (archivo, campo, max_h) in SERIES.items():
        p = os.path.join(ARCHIVO, archivo)
        if not os.path.exists(p):
            detalle[nombre] = {"ok": False, "motivo": "sin archivo"}
            fallos.append(f"{nombre}: no existe el archivo")
            continue
        try:
            h = edad_horas(p, campo)
        except Exception as e:
            detalle[nombre] = {"ok": False, "motivo": f"error: {e}"}
            fallos.append(f"{nombre}: {e}")
            continue
        if h is None:
            detalle[nombre] = {"ok": False, "motivo": "archivo vacio"}
            fallos.append(f"{nombre}: vacio")
            continue
        ok = h <= max_h
        detalle[nombre] = {"ok": ok, "edad_h": round(h, 1), "limite_h": max_h}
        if not ok:
            fallos.append(f"{nombre}: {h:.1f}h sin datos (limite {max_h}h)")

    for nombre, (p, max_h) in SALIDAS.items():
        if not os.path.exists(p):
            detalle[nombre] = {"ok": False, "motivo": "no generado"}
            fallos.append(f"{nombre}: no existe (ejecuta analysis/informe.py)")
            continue
        h = (ahora - datetime.datetime.fromtimestamp(os.path.getmtime(p), UTC)
             ).total_seconds() / 3600
        ok = h <= max_h
        detalle[nombre] = {"ok": ok, "edad_h": round(h, 1), "limite_h": max_h}
        if not ok:
            fallos.append(f"{nombre}: {h:.1f}h sin regenerar (limite {max_h}h)")

    salida = {"ok": not fallos, "chequeo_en": ahora.isoformat(),
              "detalle": detalle, "fallos": fallos}
    print(json.dumps(salida, ensure_ascii=False, indent=2))
    return 0 if not fallos else 1


if __name__ == "__main__":
    raise SystemExit(main())

