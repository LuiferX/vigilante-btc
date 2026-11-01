#!/usr/bin/env python3
"""
expr_ruptura.py - H5: familia de RUPTURA del nivel -> continuacion.

Pre-registro: analysis/EXPERIMENTOS.md, seccion "H5 - RUPTURA del nivel"
(commiteado ANTES de correr esto).

Universo: muestras cuyo nivel se rompe dentro de 48 velas. Deteccion en
tiempo real: primer CIERRE mas alla del nivel tras t; entrada al open de la
vela siguiente. Direccion `ruptura` = invertida respecto al modelo (la
continuacion); `control` = la direccion del modelo (misma vela de entrada).

LIMITACION declarada en el pre-registro: el universo se selecciona sabiendo
que el nivel rompio. Se mide si la continuacion paga, no si se puede detectar
la ruptura en vivo.

stdlib puro. Uso: python analysis/expr_ruptura.py
"""

from __future__ import annotations

import argparse
import bisect
import datetime
import json
import os
import random
import sys

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(AQUI, "data", "cache")

FEE_PCT = 0.05
SLIP_BASE = 0.02
SLIP_K = 0.25
BOOT = 10000
SEMILLA = 42
COOLDOWN_H = 2
H4 = 48
TP_G, SL_G = 1.0, 0.5        # salida gestionada (informativa, fuera del Bonferroni)
VENTANA_ROT = 48             # velas para detectar la ruptura
P_TOP = 0.858

FILTROS = ["todas", "extremos"]
DIRECCIONES = ["ruptura", "control"]
SALIDAS = ["h4", "fallo"]


# ------------------------------------------------------------------ datos --
def cargar_muestras():
    filas = []
    with open(os.path.join(CACHE, "expr_muestras.jsonl"), encoding="utf-8") as fh:
        for linea in fh:
            r = json.loads(linea)
            if r.get("_meta"):
                continue
            filas.append(r)
    return filas


def cargar_klines():
    sys.path.insert(0, AQUI)
    import hold_model as hm  # noqa: E402
    kl = hm.load_klines_jsonl(os.path.join(CACHE, "klines_5m.jsonl"))
    kl.sort(key=lambda v: v["t"])
    return kl


def atr_pct(kl, idx, n=14):
    i0 = max(0, idx - n)
    trs = []
    prev = kl[i0]
    for v in kl[i0:idx + 1]:
        tr = max(v["h"] - v["l"], abs(v["h"] - prev["c"]), abs(v["l"] - prev["c"]))
        trs.append(tr)
        prev = v
    if not trs:
        return None
    return (sum(trs) / len(trs)) / kl[idx]["c"] * 100.0


# ---------------------------------------------------- deteccion de ruptura --
def detectar_ruptura(muestra, kl, tiempos):
    """Primer cierre mas alla del nivel dentro de 48 velas -> (idx_confirma,).

    Devuelve el indice de la vela cuyo cierre confirma la ruptura, o None.
    """
    t = datetime.datetime.fromisoformat(muestra["t"].replace("Z", "+00:00"))
    j0 = bisect.bisect_right(tiempos, t)
    if j0 >= len(kl):
        return None
    nivel = muestra["nivel"]
    arriba = muestra["lado"] == "resistencia"     # rompe hacia arriba
    lim = min(j0 + VENTANA_ROT, len(kl))
    for i in range(j0, lim):
        c = kl[i]["c"]
        if (c > nivel) if arriba else (c < nivel):
            return i
    return None


def resolver(muestra, kl, tiempos, direccion, salida):
    ic = detectar_ruptura(muestra, kl, tiempos)
    if ic is None:
        return None
    j = ic + 1                                   # entrada: open de la siguiente
    if j >= len(kl):
        return None
    entrada = kl[j]["o"]
    # direccion: ruptura = continuacion (invertida respecto al modelo)
    rompe_arriba = muestra["lado"] == "resistencia"
    if direccion == "ruptura":
        largo = rompe_arriba
    else:                                        # control = la direccion del modelo
        largo = not rompe_arriba
    nivel = muestra["nivel"]
    atrp = atr_pct(kl, j) or 0.05
    coste = FEE_PCT * 2 + SLIP_BASE * 2 + SLIP_K * atrp * 2
    t_ent = kl[j]["t"]

    if salida == "h4":
        k = j + H4
        if k >= len(kl):
            return None
        salida_px = kl[k]["c"]
    elif salida == "fallo":
        # primer cierre que vuelve dentro del nivel => la ruptura falla
        fin = min(j + H4, len(kl) - 1)
        salida_px = None
        for i in range(j + 1, fin + 1):
            c = kl[i]["c"]
            dentro = (c < nivel) if rompe_arriba else (c > nivel)
            if dentro:
                salida_px = c
                break
        if salida_px is None:
            salida_px = kl[fin]["c"]
    elif salida == "gest":
        fin = min(j + H4, len(kl) - 1)
        tp = entrada * (1 + TP_G / 100) if largo else entrada * (1 - TP_G / 100)
        sl = entrada * (1 - SL_G / 100) if largo else entrada * (1 + SL_G / 100)
        salida_px = None
        for i in range(j + 1, fin + 1):
            v = kl[i]
            if (v["l"] <= sl) if largo else (v["h"] >= sl):
                salida_px = sl
                break
            if (v["h"] >= tp) if largo else (v["l"] <= tp):
                salida_px = tp
                break
        if salida_px is None:
            salida_px = kl[fin]["c"]
    else:
        raise ValueError(salida)

    if largo:
        bruto = (salida_px - entrada) / entrada * 100.0
    else:
        bruto = (entrada - salida_px) / entrada * 100.0
    return {"neto": bruto - coste, "bruto": bruto, "coste": coste, "t": t_ent,
            "atr_pct": atrp, "vol": muestra.get("volatilidad"),
            "prob": muestra.get("prob_modelo")}


def secuencia_independiente(muestras, kl, tiempos, filtro, direccion, salida):
    if filtro == "extremos":
        sel = [m for m in muestras if m.get("volatilidad") in ("expansion", "compresion")]
    else:
        sel = list(muestras)
    sel = sorted(sel, key=lambda m: m["t"])
    rets, detalle = [], []
    libre = None
    for m in sel:
        t = datetime.datetime.fromisoformat(m["t"].replace("Z", "+00:00"))
        if libre is not None and t < libre:
            continue
        r = resolver(m, kl, tiempos, direccion, salida)
        if r is None:
            continue
        fin = r["t"] + datetime.timedelta(minutes=5 * H4)
        libre = fin + datetime.timedelta(hours=COOLDOWN_H)
        rets.append(r["neto"])
        detalle.append(r)
    return rets, detalle


def bootstrap_ci(vals, alpha=0.05, boot=BOOT, semilla=SEMILLA):
    rnd = random.Random(semilla)
    n = len(vals)
    if n == 0:
        return (0.0, 0.0, 1.0)
    medias = []
    for _ in range(boot):
        s = 0.0
        for _ in range(n):
            s += vals[rnd.randrange(n)]
        medias.append(s / n)
    medias.sort()
    lo = medias[int(boot * alpha / 2)]
    hi = medias[int(boot * (1 - alpha / 2))]
    p = sum(1 for m in medias if m <= 0) / boot
    return (lo, hi, p)


def evaluar(rets, detalle):
    if not rets:
        return None
    n = len(rets)
    media = sum(rets) / n
    lo, hi, p = bootstrap_ci(rets)
    wins = sum(1 for r in rets if r > 0)
    gp = sum(r for r in rets if r > 0)
    gl = -sum(r for r in rets if r <= 0)
    var = sum((r - media) ** 2 for r in rets) / (n - 1) if n > 1 else 0.0
    eq, pico, mdd = 0.0, 0.0, 0.0
    for r in rets:
        eq += r
        pico = max(pico, eq)
        mdd = max(mdd, pico - eq)

    def md(sel):
        return round(sum(sel) / len(sel), 4) if sel else None

    corte = detalle[len(detalle) // 2]["t"]
    m1 = [d["neto"] for d in detalle if d["t"] < corte]
    m2 = [d["neto"] for d in detalle if d["t"] >= corte]
    regs = {k: {"n": len([d for d in detalle if d["vol"] == k]),
                "media": md([d["neto"] for d in detalle if d["vol"] == k] or [])}
            for k in ("compresion", "normal", "expansion")}
    return {"n": n, "media": round(media, 4),
            "bruto_medio": round(sum(d["bruto"] for d in detalle) / n, 4),
            "coste_medio": round(sum(d["coste"] for d in detalle) / n, 4),
            "ic95": [round(lo, 4), round(hi, 4)], "p_boot": round(p, 5),
            "hit_rate": round(wins / n, 4),
            "profit_factor": round(gp / gl, 3) if gl > 0 else None,
            "equidad": round(eq, 2), "max_dd": round(mdd, 2),
            "mitades": {"h1": {"n": len(m1), "media": md(m1)},
                        "h2": {"n": len(m2), "media": md(m2)}},
            "regimenes": regs}


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()

    muestras = cargar_muestras()
    kl = cargar_klines()
    tiempos = [v["t"] for v in kl]
    print(f"muestras: {len(muestras)} | klines: {len(kl)}")

    celdas = {}
    for filtro in FILTROS:
        for direccion in DIRECCIONES:
            for salida in SALIDAS:
                rets, detalle = secuencia_independiente(muestras, kl, tiempos,
                                                        filtro, direccion, salida)
                if not rets:
                    continue
                c = evaluar(rets, detalle)
                rets2 = [d["neto"] - d["coste"] for d in detalle]
                celdas[f"{filtro}:{direccion}:{salida}"] = {
                    "resumen": c,
                    "costes_x2_media": round(sum(rets2) / len(rets2), 4) if rets2 else None,
                }
                cc = celdas[f"{filtro}:{direccion}:{salida}"]
                print(f"  {filtro:9s} {direccion:8s} {salida:5s} n={c['n']:5d} "
                      f"neta={c['media']:+.4f}% bruto={c['bruto_medio']:+.4f}% "
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

    # informativo (fuera de las 8 celdas): gestionada y expansion a solas
    info = {}
    for direccion in DIRECCIONES:
        rets, detalle = secuencia_independiente(muestras, kl, tiempos,
                                                "todas", direccion, "gest")
        if rets:
            info[f"todas:{direccion}:gest"] = evaluar(rets, detalle)
    solo_exp = [m for m in muestras if m.get("volatilidad") == "expansion"]
    rets, detalle = secuencia_independiente(solo_exp, kl, tiempos, "todas",
                                            "ruptura", "h4")
    if rets:
        info["expansion:ruptura:h4"] = evaluar(rets, detalle)

    out = {"hipotesis": "H5", "fecha": datetime.datetime.now(UTC).isoformat(),
           "parametros": {"fee_pct": FEE_PCT, "slip_base_pct": SLIP_BASE,
                          "atr_k": SLIP_K, "cooldown_h": COOLDOWN_H,
                          "ventana_ruptura": VENTANA_ROT, "tp_gest": TP_G,
                          "sl_gest": SL_G, "bootstrap": BOOT, "semilla": SEMILLA,
                          "muestras_replay": len(muestras),
                          "nota_universo": "seleccionado sabiendo que rompio; "
                                           "mide continuacion, no deteccion"},
           "variantes_probadas": n_celdas, "p_corregido": round(p_corr, 5),
           "celdas": {k: dict(v["resumen"], costes_x2_media=v["costes_x2_media"],
                              veredicto=veredictos[k]) for k, v in celdas.items()},
           "informativo_fuera_bonferroni": info}
    p = os.path.join(AQUI, "data", "edge_ruptura.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\np_corregido (Bonferroni {n_celdas} celdas): {p_corr:.5f}")
    print("veredictos:", veredictos)
    print(f"OK -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
