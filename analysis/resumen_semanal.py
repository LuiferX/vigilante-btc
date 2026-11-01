#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resumen_semanal.py - digest semanal de la maquina de analisis.

REARME 2026-11-01: antes el workflow 'Resumen semanal' resumia la operacion
(pasadas, alertas, papel, banco) y la mandaba a Telegram. Eso ya no existe.
Ahora resume lo que de verdad importa: como se movio el POSICIONAMIENTO medido
durante la semana, para ver la tendencia sin abrir el archivo.

Para cada serie del archivo compara el percentil de HOY con el de hace N dias
(dentro de una ventana causal de 30 d) y dice si esta subiendo o bajando.

Uso: python analysis/resumen_semanal.py [--dias 7]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import percentiles as pc  # noqa: E402

VARIACION_ALTA = 0.20  # 20 puntos de percentil = cambio notable


def percentil_en(ts, vs, t_ref, ventana):
    r = pc.percentil_causal(ts, vs, t_ref, ventana)
    return r["percentil"] if r else None


def resumen(nombre: str, dias: int = 7) -> dict | None:
    try:
        ts, vs = pc.cargar(nombre)
    except FileNotFoundError:
        return None
    if len(ts) < 30:
        return None
    ventana = datetime.timedelta(days=30)
    ahora = ts[-1]
    antes = ahora - int(datetime.timedelta(days=dias).total_seconds() * 1000)
    p_hoy = percentil_en(ts, vs, ahora, ventana)
    p_antes = percentil_en(ts, vs, antes, ventana)
    if p_hoy is None or p_antes is None:
        return None
    delta = p_hoy - p_antes
    sentido = (
        "subiendo"
        if delta >= VARIACION_ALTA
        else "bajando" if delta <= -VARIACION_ALTA else "estable"
    )
    return {
        "serie": nombre,
        "percentil_hoy": round(p_hoy, 4),
        f"percentil_hace_{dias}d": round(p_antes, 4),
        "delta_pp": round(delta * 100, 1),
        "sentido": sentido,
        "cobertura_dias": round((ts[-1] - ts[0]) / 86_400_000, 1),
    }


def redactar(filas: list[dict], dias: int = 7) -> str:
    L = []
    L.append(
        "# Digest semanal de posicionamiento — " f"{datetime.datetime.now(UTC):%Y-%m-%d %H:%M} UTC"
    )
    L.append("")
    L.append(
        f"> Cambio del percentil causal (ventana 30 d) en {dias} días. " "Esto no opera: informa."
    )
    L.append("")
    if not filas:
        L.append("Sin datos suficientes todavía (el archivo necesita tiempo).")
        return "\n".join(L)
    L.append("| Serie | Percentil hoy | Hace {} d | Δ (pp) | Sentido |".format(dias))
    L.append("|---|---:|---:|---:|---|")
    clave = f"percentil_hace_{dias}d"
    for f in filas:
        L.append(
            "| {} | {:.1f} % | {:.1f} % | {:+.1f} | {} |".format(
                f["serie"], f["percentil_hoy"] * 100, f[clave] * 100, f["delta_pp"], f["sentido"]
            )
        )
    L.append("")
    movidos = [f for f in filas if f["sentido"] != "estable"]
    if movidos:
        L.append(
            "**Lo que se movió:** "
            + ", ".join("{} ({})".format(f["serie"], f["sentido"]) for f in movidos)
            + "."
        )
    else:
        L.append("**Nada se movió de forma notable**: el posicionamiento medido " "está estable.")
    L.append("")
    L.append("---")
    L.append("")
    L.append(
        "Caveat honesto: el archivo de microestructura se empezó a "
        "guardar el 2026-11-01 (la API de Binance solo servía 30 días). "
        "Con pocas semanas de historia, un 'subiendo' de una semana es "
        "una foto, no una tendencia. Se reevalúa cada semana."
    )
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=7)
    a = ap.parse_args()
    filas = []
    for nombre in sorted(pc.SERIES):
        try:
            r = resumen(nombre, a.dias)
        except Exception:
            r = None
        if r:
            filas.append(r)
            print("  {:18s} {:5.1f}% -> {}".format(nombre, r["percentil_hoy"] * 100, r["sentido"]))
    md = redactar(filas, a.dias)
    out = {"generado": datetime.datetime.now(UTC).isoformat(), "dias": a.dias, "series": filas}
    pj = os.path.join(AQUI, "data", "resumen_semanal.json")
    with open(pj, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    pm = os.path.join(AQUI, "data", "resumen_semanal.md")
    with open(pm, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"OK -> {pj} y {pm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
