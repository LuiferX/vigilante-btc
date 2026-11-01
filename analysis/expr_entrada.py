#!/usr/bin/env python3
"""
expr_entrada.py - H4: rediseno de la ENTRADA del signal "toques".

Pre-registro: analysis/EXPERIMENTOS.md, seccion "H4 - rediseno de la ENTRADA"
(commiteado ANTES de correr esto).

La direccion del modelo congelado se mantiene (soporte->largo,
resistencia->corto); solo cambia el momento de entrada. El modelo NO se toca:
se reutilizan `lado` y `prob_modelo` ya registrados en el replay.

Variantes de entrada (pre-registradas):
  base     - open de la vela siguiente a t
  retardo  - open de la vela siguiente a t+2 velas (control de tiempo)
  confirm  - cierre >= 0,3% del lado favorable del nivel; entra al open siguiente
  barrido  - perfora el nivel >= 0,2% y lo recupera; entra al open siguiente
Ventana de espera maxima W = 24 velas. Salidas: h4 (48 velas) y gest
(TP 0,5/SL 0,3, cierre forzoso 48 velas, SL primero si coinciden).

stdlib puro. Uso: python analysis/expr_entrada.py
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
COOLDOWN_H = 4
TP_PCT = 0.5
SL_PCT = 0.3
H4 = 48
W_ESPERA = 24          # velas maximas esperando la entrada
D_CONFIRM = 0.3        # % de movimiento favorable para confirmar
D_PERFO = 0.2          # % de perforacion del nivel para el barrido
D_RECUP = 0.05         # % de recuperacion del nivel tras el barrido
P_TOP = 0.858

ENTRADAS = ["base", "retardo", "confirm", "barrido"]
SALIDAS = ["h4", "gest"]


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


# ------------------------------------------------------------- la entrada --
def buscar_entrada(muestra, kl, tiempos, variante):
    """Devuelve (idx_entrada, precio) o None.

    Cero look-ahead: las condiciones se evaluan con datos hasta el bar
    comprobado, y el precio de entrada es el OPEN de la vela siguiente.
    """
    t = datetime.datetime.fromisoformat(muestra["t"].replace("Z", "+00:00"))
    j0 = bisect.bisect_right(tiempos, t)
    if j0 >= len(kl):
        return None
    nivel = muestra["nivel"]
    largo = muestra["lado"] == "soporte"
    lim = min(j0 + W_ESPERA + 1, len(kl) - 1)

    if variante == "base":
        return (j0, kl[j0]["o"])
    if variante == "retardo":
        j = j0 + 2
        return (j, kl[j]["o"]) if j < len(kl) else None

    if variante == "confirm":
        # cierre >= D_CONFIRM% del lado favorable del nivel
        for i in range(j0, lim):
            c = kl[i]["c"]
            ok = (c >= nivel * (1 + D_CONFIRM / 100)) if largo \
                else (c <= nivel * (1 - D_CONFIRM / 100))
            if ok:
                j = i + 1
                return (j, kl[j]["o"]) if j < len(kl) else None
        return None

    if variante == "barrido":
        perforado = False
        for i in range(j0, lim):
            if not perforado:
                low, high = kl[i]["l"], kl[i]["h"]
                perforado = (low <= nivel * (1 - D_PERFO / 100)) if largo \
                    else (high >= nivel * (1 + D_PERFO / 100))
                continue
            c = kl[i]["c"]
            recup = (c >= nivel * (1 + D_RECUP / 100)) if largo \
                else (c <= nivel * (1 - D_RECUP / 100))
            if recup:
                j = i + 1
                return (j, kl[j]["o"]) if j < len(kl) else None
        return None

    raise ValueError(variante)


def resolver(muestra, kl, tiempos, variante, salida):
    ent = buscar_entrada(muestra, kl, tiempos, variante)
    if ent is None:
        return None
    j, entrada = ent
    largo = muestra["lado"] == "soporte"
    atrp = atr_pct(kl, j) or 0.05
    coste = FEE_PCT * 2 + SLIP_BASE * 2 + SLIP_K * atrp * 2
    t_ent = kl[j]["t"]

    if salida == "h4":
        k = j + H4
        if k >= len(kl):
            return None
        salida_px = kl[k]["c"]
        kfin = k
    elif salida == "gest":
        fin = min(j + H4, len(kl) - 1)
        tp = entrada * (1 + TP_PCT / 100) if largo else entrada * (1 - TP_PCT / 100)
        sl = entrada * (1 - SL_PCT / 100) if largo else entrada * (1 + SL_PCT / 100)
        salida_px = None
        kfin = fin
        for i in range(j + 1, fin + 1):
            v = kl[i]
            toco_sl = v["l"] <= sl if largo else v["h"] >= sl
            if toco_sl:
                salida_px = sl
                break
            toco_tp = v["h"] >= tp if largo else v["l"] <= tp
            if toco_tp:
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
            "atr_pct": atrp, "prob": muestra.get("prob_modelo"),
            "vol": muestra.get("volatilidad"), "espera_barras": j - (bisect.bisect_right(
                tiempos, datetime.datetime.fromisoformat(muestra["t"].replace("Z", "+00:00"))))}


def secuencia_independiente(muestras, kl, tiempos, variante, salida):
    sel = sorted(muestras, key=lambda m: m["t"])
    rets, detalle = [], []
    libre = None
    for m in sel:
        t = datetime.datetime.fromisoformat(m["t"].replace("Z", "+00:00"))
        if libre is not None and t < libre:
            continue
        r = resolver(m, kl, tiempos, variante, salida)
        if r is None:
            continue
        espera = r.pop("espera_barras")
        horizonte = H4
        fin = r["t"] + datetime.timedelta(minutes=5 * (espera + horizonte))
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
    for entrada in ENTRADAS:
        for salida in SALIDAS:
            rets, detalle = secuencia_independiente(muestras, kl, tiempos,
                                                    entrada, salida)
            if not rets:
                continue
            c = evaluar(rets, detalle)
            rets2 = [d["neto"] - d["coste"] for d in detalle]
            celdas[f"{entrada}:{salida}"] = {
                "resumen": c,
                "costes_x2_media": round(sum(rets2) / len(rets2), 4) if rets2 else None,
            }
            print(f"  {entrada:8s} {salida:4s} n={c['n']:5d} neta={c['media']:+.4f}% "
                  f"bruto={c['bruto_medio']:+.4f}% coste={c['coste_medio']:.4f}% "
                  f"hit={c['hit_rate']:.2f} x2={celdas[f'{entrada}:{salida}']['costes_x2_media']:+.4f}")

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

    out = {"hipotesis": "H4",
           "fecha": datetime.datetime.now(UTC).isoformat(),
           "parametros": {"fee_pct": FEE_PCT, "slip_base_pct": SLIP_BASE,
                          "atr_k": SLIP_K, "tp_pct": TP_PCT, "sl_pct": SL_PCT,
                          "cooldown_h": COOLDOWN_H, "espera_velas": W_ESPERA,
                          "d_confirm_pct": D_CONFIRM, "d_perforacion_pct": D_PERFO,
                          "d_recuperacion_pct": D_RECUP, "bootstrap": BOOT,
                          "semilla": SEMILLA, "muestras_replay": len(muestras)},
           "variantes_probadas": n_celdas, "p_corregido": round(p_corr, 5),
           "celdas": {k: dict(v["resumen"], costes_x2_media=v["costes_x2_media"],
                              veredicto=veredictos[k]) for k, v in celdas.items()}}
    p = os.path.join(AQUI, "data", "edge_entrada.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\np_corregido (Bonferroni {n_celdas} celdas): {p_corr:.5f}")
    print("veredictos:", veredictos)
    print(f"OK -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
