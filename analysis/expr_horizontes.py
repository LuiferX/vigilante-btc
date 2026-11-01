#!/usr/bin/env python3
"""
expr_horizontes.py - H6: horizontes largos 12/24/48/72 h.

Pre-registro: analysis/EXPERIMENTOS.md, seccion "H6 - HORIZONTES LARGOS"
(commiteado ANTES de correr esto).

Misma entrada y direccion que H3 (open de la vela siguiente a t; soporte->
largo, resistencia->corto). Lo unico que cambia es el horizonte de salida
(144/288/576/864 velas) y el coste, que ahora incluye el FUNDING cobrado o
pagado durante el hold (en H3, con hold de 4h, era despreciable; a 72h
acumula 9 pagos y +0,05%).

std燎lib puro. Uso: python analysis/expr_horizontes.py
"""

from __future__ import annotations

import argparse
import bisect
import datetime
import json
import os
import sys

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

COOLDOWN_EXTRA_H = 4

HORIZONTES = {"12h": 144, "24h": 288, "48h": 576, "72h": 864}
CONVICCIONES = ["todas", "top"]

_FTS = []       # timestamps de funding indexados
_FRATES = []    # rates alineados


from laboratorio import (  # noqa: E402,F401
    BOOT,
    CACHE,
    FEE_PCT,
    P_TOP,
    SEMILLA,
    SLIP_BASE,
    SLIP_K,
    atr_pct,
    bootstrap_ci,
    cargar_klines,
    cargar_muestras,
    coste_viaje,
    evaluar,
    motor_secuencia,
    veredicto,
)

# ------------------------------------------------------------------ datos --

def cargar_funding():
    filas = []
    with open(os.path.join(CACHE, "funding.jsonl"), encoding="utf-8") as fh:
        for linea in fh:
            r = json.loads(linea)
            filas.append((datetime.datetime.fromtimestamp(r["fundingTime"] / 1000, UTC),
                          float(r["fundingRate"])))
    _FTS[:] = [t for t, _ in filas]
    _FRATES[:] = [v for _, v in filas]


def funding_en_rango(ini, fin, largo):
    """Funding (fraccion) cobrado/pagado entre ini y fin.

    Convencion del PnL: el LARGO cobra si rate<0 (aporte -rate) y paga si >0;
    el CORTO cobra si rate>0 (aporte +rate) y paga si <0.
    """
    i = bisect.bisect_left(_FTS, ini)
    total = 0.0
    while i < len(_FTS) and _FTS[i] < fin:
        total += -_FRATES[i] if largo else _FRATES[i]
        i += 1
    return total


# -------------------------------------------------------------- operación --
def resolver(muestra, kl, tiempos, barras):
    t = datetime.datetime.fromisoformat(muestra["t"].replace("Z", "+00:00"))
    j = bisect.bisect_right(tiempos, t)          # entrada: open de la siguiente
    if j + barras >= len(kl):
        return None
    largo = muestra["lado"] == "soporte"
    entrada = kl[j]["o"]
    salida = kl[j + barras]["c"]
    atrp = atr_pct(kl, j) or 0.05
    coste = FEE_PCT * 2 + SLIP_BASE * 2 + SLIP_K * atrp * 2
    fund = funding_en_rango(kl[j]["t"], kl[j + barras]["t"], largo) * 100.0
    if largo:
        bruto = (salida - entrada) / entrada * 100.0
    else:
        bruto = (entrada - salida) / entrada * 100.0
    return {"neto": bruto - coste + fund, "bruto": bruto, "coste": coste,
            "funding_pct": fund, "t": kl[j]["t"], "atr_pct": atrp,
            "prob": muestra.get("prob_modelo"), "vol": muestra.get("volatilidad")}


def secuencia_independiente(muestras, kl, tiempos, barras, conviccion):
    """Una operacion a la vez + cooldown (motor compartido).

    El hold ES el horizonte que se esta probando."""
    return motor_secuencia(
        muestras,
        lambda m: resolver(m, kl, tiempos, barras),
        conviccion=conviccion, p_top=P_TOP,
        cooldown_h=COOLDOWN_EXTRA_H,     # sin solapes
        hold_fn=lambda r: barras)


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()

    muestras = cargar_muestras()
    kl = cargar_klines()
    tiempos = [v["t"] for v in kl]
    cargar_funding()
    print(f"muestras: {len(muestras)} | klines: {len(kl)}")

    celdas = {}
    for hnombre, barras in HORIZONTES.items():
        for conv in CONVICCIONES:
            rets, detalle = secuencia_independiente(muestras, kl, tiempos,
                                                    barras, conv)
            if not rets:
                continue
            c = evaluar(rets, detalle)
            rets2 = [d["neto"] - d["coste"] for d in detalle]   # costes x2
            celdas[f"{hnombre}:{conv}"] = {
                "resumen": c,
                "costes_x2_media": round(sum(rets2) / len(rets2), 4) if rets2 else None,
            }
            cc = celdas[f"{hnombre}:{conv}"]
            print(f"  {hnombre:4s} {conv:6s} n={c['n']:5d} neta={c['media']:+.4f}% "
                  f"bruto={c['bruto_medio']:+.4f}% fund={c['funding_medio']:+.4f}% "
                  f"coste={c['coste_medio']:.4f}% hit={c['hit_rate']:.2f} "
                  f"x2={cc['costes_x2_media']:+.4f}")

    ps = [c["resumen"]["p_boot"] for c in celdas.values()]
    n_celdas = len(ps)
    p_corr = min(1.0, min(ps) * n_celdas) if ps else 1.0

    veredictos = {}
    for clave, c in celdas.items():
        r = c["resumen"]
        if r["n"] < 300:
            veredictos[clave] = "no_concluyente"
            continue
        ok = (r["media"] > 0 and r["ic95"][0] > 0
              and (r["mitades"]["h1"]["media"] or 0) > 0
              and (r["mitades"]["h2"]["media"] or 0) > 0
              and sum(1 for k in r["regimenes"]
                      if (r["regimenes"][k]["media"] or 0) > 0) >= 2
              and (c["costes_x2_media"] or -1) > 0)
        veredictos[clave] = "edge" if ok else "sin_edge"

    out = {"hipotesis": "H6", "fecha": datetime.datetime.now(UTC).isoformat(),
           "parametros": {"fee_pct": FEE_PCT, "slip_base_pct": SLIP_BASE,
                          "atr_k": SLIP_K, "cooldown_extra_h": COOLDOWN_EXTRA_H,
                          "p_top": P_TOP, "bootstrap": BOOT, "semilla": SEMILLA,
                          "muestras_replay": len(muestras),
                          "horizontes_velas": HORIZONTES,
                          "funding_incluido": True},
           "variantes_probadas": n_celdas, "p_corregido": round(p_corr, 5),
           "celdas": {k: dict(v["resumen"], costes_x2_media=v["costes_x2_media"],
                              veredicto=veredictos[k]) for k, v in celdas.items()}}
    p = os.path.join(AQUI, "data", "edge_horizontes.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\np_corregido (Bonferroni {n_celdas} celdas): {p_corr:.5f}")
    print("veredictos:", veredictos)
    print(f"OK -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
