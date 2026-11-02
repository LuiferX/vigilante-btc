#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resumen_semanal.py - digest semanal de la maquina de analisis.

REARME 2026-11-02: antes el workflow 'Resumen semanal' resumia la operacion
(pasadas, alertas, papel, banco) y la mandaba a Telegram. Eso ya no existe.
Ahora resume lo que de verdad importa: como se movio el POSICIONAMIENTO medido.

Dos mitades, a proposito:
  A) CORTE (lo que ya habia): percentil de HOY vs el de hace N dias, dentro de
     una ventana causal de 30 d. Es una foto comparada con otra foto.
  B) EVOLUCION (nuevo): cada corte se guarda en `data/percentiles_hist.jsonl`
     (una fila por serie y dia, idempotente) y el digest muestra la serie de
     las ultimas semanas + la tendencia. Asi el informe deja de ser una foto y
     pasa a ser una serie temporal.

Caveat declarado en el propio digest: el archivo de microestructura empezo el
2026-11-01, asi que con pocos cortes guardados la tendencia es un esbozo, no
una conclusion. Y cada percentil se mide dentro de SU ventana rodante de 30 d,
asi que compara posiciones relativas, no valores absolutos.

Uso: python analysis/resumen_semanal.py [--dias 7] [--semanas 8]
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
HIST = os.path.join(AQUI, "data", "percentiles_hist.jsonl")
VENTANA = datetime.timedelta(days=30)


def percentil_en(ts, vs, t_ref, ventana):
    r = pc.percentil_causal(ts, vs, t_ref, ventana)
    return r["percentil"] if r else None


def corte_actual(nombre: str) -> dict | None:
    """Percentil de hoy (ventana rodante de 30 d)."""
    try:
        ts, vs = pc.cargar(nombre)
    except FileNotFoundError:
        return None
    if len(ts) < 30:
        return None
    r = pc.percentil_causal(ts, vs, ts[-1], VENTANA)
    return r


def guardar_corte(nombre: str, r: dict) -> None:
    """Añade el corte de HOY al historial. Idempotente por (fecha, serie)."""
    hoy = datetime.datetime.now(UTC).date().isoformat()
    fila = {
        "fecha": hoy,
        "serie": nombre,
        "percentil": round(r["percentil"], 4),
        "valor": round(r["valor"], 8),
        "n_ventana": r["n_ventana"],
        "cobertura_dias": round((ts_dias(nombre)), 1),
    }
    previas = []
    if os.path.exists(HIST):
        with open(HIST, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    previas.append(json.loads(linea))
                except Exception:
                    continue
    if any(x.get("fecha") == hoy and x.get("serie") == nombre for x in previas):
        return  # ya está: no duplica
    previas.append(fila)
    with open(HIST, "w", encoding="utf-8") as fh:
        for x in sorted(previas, key=lambda y: (y.get("fecha", ""), y.get("serie", ""))):
            fh.write(json.dumps(x, ensure_ascii=False) + "\n")


def ts_dias(nombre: str) -> float:
    try:
        ts, _ = pc.cargar(nombre)
        return (ts[-1] - ts[0]) / 86_400_000
    except Exception:
        return 0.0


def leer_historial() -> list[dict]:
    if not os.path.exists(HIST):
        return []
    out = []
    with open(HIST, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                out.append(json.loads(linea))
            except Exception:
                continue
    return out


def evolucion(nombre: str, semanas: int = 8) -> dict:
    """Serie temporal de los ultimos `semanas` cortes de una serie."""
    h = [x for x in leer_historial() if x.get("serie") == nombre]
    h.sort(key=lambda x: x.get("fecha", ""))
    ult = h[-semanas:]
    if len(ult) < 2:
        return {"n": len(ult), "puntos": ult, "tendencia": None}
    primero, ultimo = ult[0]["percentil"], ult[-1]["percentil"]
    delta = ultimo - primero
    # tendencia: compara la media de la mitad vieja con la nueva
    mitad = max(1, len(ult) // 2)
    vieja = sum(x["percentil"] for x in ult[:mitad]) / mitad
    nueva = sum(x["percentil"] for x in ult[mitad:]) / max(1, len(ult) - mitad)
    if nueva - vieja >= VARIACION_ALTA:
        tendencia = "subiendo"
    elif nueva - vieja <= -VARIACION_ALTA:
        tendencia = "bajando"
    else:
        tendencia = "estable"
    return {
        "n": len(ult),
        "puntos": [{"fecha": x["fecha"], "percentil": x["percentil"]} for x in ult],
        "delta_pp": round(delta * 100, 1),
        "tendencia": tendencia,
    }


def resumen(nombre: str, dias: int = 7) -> dict | None:
    try:
        ts, vs = pc.cargar(nombre)
    except FileNotFoundError:
        return None
    if len(ts) < 30:
        return None
    ventana = VENTANA
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


def redactar(filas: list[dict], evol: dict, dias: int = 7) -> str:
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
    L.append("## A) Corte: hoy vs hace {} días".format(dias))
    L.append("")
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
    L.append(
        "> Cada percentil se mide dentro de **su** ventana rodante de 30 d "
        "(compara posiciones relativas, no valores absolutos). El archivo "
        "de microestructura empezó el 2026-11-01: los cortes con pocas "
        "semanas de historia detrás son más ruidosos."
    )
    L.append("")
    L.append("## B) Evolución (cortes guardados)")
    L.append("")
    con_hist = {k: v for k, v in evol.items() if v["n"] >= 2}
    if not con_hist:
        L.append(
            "Todavía no hay 2 cortes guardados: la tendencia arranca "
            "cuando el digest haya corrido al menos dos semanas. Cada "
            "corrida guarda una fila por serie en "
            "`analysis/data/percentiles_hist.jsonl`."
        )
    else:
        L.append("| Serie | Cortes | Tendencia | Δ (pp) | Últimos valores |")
        L.append("|---|---:|---|---:|---|")
        for nombre, v in con_hist.items():
            puntos = ", ".join("{:.0f}".format(p["percentil"] * 100) for p in v["puntos"])
            L.append(
                "| {} | {} | {} | {} | {} |".format(
                    nombre, v["n"], v["tendencia"], v.get("delta_pp", "—"), puntos
                )
            )
        L.append("")
        L.append(
            "> Cada percentil se mide dentro de **su** ventana rodante de "
            "30 días: comparan posiciones relativas, no valores absolutos. "
            "Con el archivo empezado el 2026-11-01, los primeros cortes "
            "tienen menos historia detrás y son más ruidosos."
        )
    L.append("")
    L.append("---")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=7)
    ap.add_argument("--semanas", type=int, default=8)
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

    evol = {}
    for nombre in sorted(pc.SERIES):
        try:
            corte = corte_actual(nombre)
        except Exception:
            corte = None
        if corte:
            guardar_corte(nombre, corte)
        try:
            evol[nombre] = evolucion(nombre, a.semanas)
        except Exception:
            evol[nombre] = {"n": 0, "puntos": [], "tendencia": None}

    md = redactar(filas, evol, a.dias)
    out = {
        "generado": datetime.datetime.now(UTC).isoformat(),
        "dias": a.dias,
        "series": filas,
        "evolucion": evol,
    }
    pj = os.path.join(AQUI, "data", "resumen_semanal.json")
    with open(pj, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    pm = os.path.join(AQUI, "data", "resumen_semanal.md")
    with open(pm, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"OK -> {pj}, {pm} y {HIST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
