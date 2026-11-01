#!/usr/bin/env python3
"""
expr_toques.py - H3: expectativa NETA (dinero) del signal "toques" del modelo
congelado toques-wf-1, sobre el replay historico 2023-2026.

Pre-registro: analysis/EXPERIMENTOS.md, seccion "H3 - expectativa NETA del
signal toques" (commiteado ANTES de correr esto).

Reglas duras:
  - Entrada al OPEN de la vela siguiente al timestamp de la muestra.
  - Coste SIEMPRE: 0,23% por viaje (fee + slippage + 0,25*ATR).
  - Independencia: un trade a la vez, cooldown de 4h tras el cierre.
  - Bootstrap 10.000 con semilla fija. Resultado negativo se publica igual.
  - NO toca el modelo: solo lee prob_modelo ya registrado en el replay.

stdlib puro. Uso: python analysis/expr_toques.py
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
TP_PCT = 0.5        # salida gestionada
SL_PCT = 0.3
H4, H24 = 48, 288   # barras 5m

# salidas x convicciones = 6 celdas (pre-registradas)
SALIDAS = ["E1_h4", "E2_gest", "E3_h24"]
CONVICCIONES = ["todas", "top"]
P_TOP = 0.858       # cuartil superior de prob_modelo (medido en el gate de cobertura)


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


# -------------------------------------------------------------- operación --
def operar(muestra, kl, tiempos, salida):
    """Retorno NETO de una muestra, o None si no hay datos suficientes."""
    t = datetime.datetime.fromisoformat(muestra["t"].replace("Z", "+00:00"))
    j = bisect.bisect_right(tiempos, t)          # open de la vela siguiente
    if j >= len(kl):
        return None
    corto = muestra["lado"] == "resistencia"
    entrada = kl[j]["o"]
    atrp = atr_pct(kl, j) or 0.05
    coste = FEE_PCT * 2 + SLIP_BASE * 2 + SLIP_K * atrp * 2
    t_ent = kl[j]["t"]

    if salida == "E1_h4":
        k = j + H4
        if k >= len(kl):
            return None
        salida_px = kl[k]["c"]
    elif salida == "E3_h24":
        k = j + H24
        if k >= len(kl):
            return None
        salida_px = kl[k]["c"]
    elif salida == "E2_gest":
        # gestionada: TP 0,5% / SL 0,3%, cierre forzoso a 4h.
        # corto: TP si low <= entrada*(1-0,005); SL si high >= entrada*(1+0,003)
        # si ambas en la misma vela -> se asume SL primero (conservador)
        fin = min(j + H4, len(kl) - 1)
        tp = entrada * (1 - TP_PCT / 100) if corto else entrada * (1 + TP_PCT / 100)
        sl = entrada * (1 + SL_PCT / 100) if corto else entrada * (1 - SL_PCT / 100)
        salida_px = None
        for i in range(j + 1, fin + 1):
            v = kl[i]
            toco_sl = v["h"] >= sl if corto else v["l"] <= sl
            if toco_sl:
                salida_px = sl
                break
            toco_tp = v["l"] <= tp if corto else v["h"] >= tp
            if toco_tp:
                salida_px = tp
                break
        if salida_px is None:
            salida_px = kl[fin]["c"]
    else:
        raise ValueError(salida)

    if corto:
        bruto = (entrada - salida_px) / entrada * 100.0
    else:
        bruto = (salida_px - entrada) / entrada * 100.0
    return {"neto": bruto - coste, "bruto": bruto, "coste": coste,
            "t": t_ent, "atr_pct": atrp, "prob": muestra.get("prob_modelo"),
            "vol": muestra.get("volatilidad"), "sesion": muestra.get("sesion")}


def secuencia_independiente(muestras, kl, tiempos, salida, conviccion):
    """Un trade a la vez + cooldown: devuelve los retornos netos independientes."""
    sel = [m for m in muestras if conviccion == "todas" or m.get("prob_modelo", 0) >= P_TOP]
    sel.sort(key=lambda m: m["t"])
    rets, detalle = [], []
    libre = None                      # datetime hasta el que no se puede entrar
    for m in sel:
        t = datetime.datetime.fromisoformat(m["t"].replace("Z", "+00:00"))
        if libre is not None and t < libre:
            continue
        r = operar(m, kl, tiempos, salida)
        if r is None:
            continue
        horizonte = H4 if salida != "E3_h24" else H24
        fin = r["t"] + datetime.timedelta(minutes=5 * horizonte)
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

    def media_de(sel):
        return round(sum(sel) / len(sel), 4) if sel else None

    corte = detalle[len(detalle) // 2]["t"]
    m1 = [d["neto"] for d in detalle if d["t"] < corte]
    m2 = [d["neto"] for d in detalle if d["t"] >= corte]
    regs = {}
    for nombre in ("compresion", "normal", "expansion"):
        v = [d["neto"] for d in detalle if d["vol"] == nombre]
        regs[nombre] = {"n": len(v), "media": media_de(v)}
    return {
        "n": n, "media": round(media, 4),
        "bruto_medio": round(sum(d["bruto"] for d in detalle) / n, 4),
        "coste_medio": round(sum(d["coste"] for d in detalle) / n, 4),
        "ic95": [round(lo, 4), round(hi, 4)], "p_boot": round(p, 5),
        "hit_rate": round(wins / n, 4),
        "profit_factor": round(gp / gl, 3) if gl > 0 else None,
        "equidad": round(eq, 2), "max_dd": round(mdd, 2),
        "mitades": {"h1": {"n": len(m1), "media": media_de(m1)},
                    "h2": {"n": len(m2), "media": media_de(m2)}},
        "regimenes": regs,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", default=None, help="salida:conviccion, p.ej. E2_gest:todas")
    a = ap.parse_args()

    muestras = cargar_muestras()
    kl = cargar_klines()
    tiempos = [v["t"] for v in kl]
    print(f"muestras: {len(muestras)} | klines: {len(kl)}")

    celdas = {}
    for salida in SALIDAS:
        for conv in CONVICCIONES:
            rets, detalle = secuencia_independiente(muestras, kl, tiempos, salida, conv)
            if not rets:
                continue
            c = evaluar(rets, detalle)
            # costes x2
            rets2 = [d["neto"] - d["coste"] for d in detalle]
            celdas[f"{salida}:{conv}"] = {
                "resumen": c,
                "costes_x2_media": round(sum(rets2) / len(rets2), 4) if rets2 else None,
            }
            print(f"  {salida:9s} {conv:7s} n={c['n']:5d} neta={c['media']:+.4f}% "
                  f"ic95=[{c['ic95'][0]:+.4f},{c['ic95'][1]:+.4f}] "
                  f"hit={c['hit_rate']:.2f} x2={celdas[f'{salida}:{conv}']['costes_x2_media']:+.4f}")

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

    out = {
        "hipotesis": "H3", "modelo": "toques-wf-1 (congelado, solo leido)",
        "fecha": datetime.datetime.now(UTC).isoformat(),
        "parametros": {"coste_pct_viaje": FEE_PCT * 2 + SLIP_BASE * 2,
                       "atr_k": SLIP_K, "tp_pct": TP_PCT, "sl_pct": SL_PCT,
                       "cooldown_h": COOLDOWN_H, "bootstrap": BOOT, "semilla": SEMILLA,
                       "p_top": P_TOP, "muestras_replay": len(muestras)},
        "variantes_probadas": n_celdas, "p_corregido": round(p_corr, 5),
        "celdas": {k: dict(v["resumen"], costes_x2_media=v["costes_x2_media"],
                           veredicto=veredictos[k]) for k, v in celdas.items()},
    }
    p = os.path.join(AQUI, "data", "edge_toques.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\np_corregido (Bonferroni {n_celdas} celdas): {p_corr:.5f}")
    print("veredictos:", {k: v for k, v in veredictos.items()})
    print(f"OK -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
