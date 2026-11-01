#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""laboratorio.py - motor COMPARTIDO de los experimentos de señal (H3-H6).

Antes cada `analysis/expr_*.py` traía su propia copia de los cargadores, el
bootstrap, el ATR y la máquina de independencia: 5 copias de lo mismo, que era
5 sitios donde arreglar el mismo bug. Aquí vive una sola vez.

Cada experimento mantiene SU política (cómo se entra, cuándo se sale, cuánto
dura el hold) y delega la infraestructura aquí:

    from laboratorio import (cargar_muestras, cargar_klines, motor_secuencia,
                             bootstrap_ci, evaluar, atr_pct, coste_viaje)

Reglas que este modulo garantiza (y que los tests comprueban):
  - Cero look-ahead en los cargadores (los datos vienen ya ordenados y solo se
    mira el pasado).
  - Independencia real: una operación a la vez + cooldown explícito.
  - Bootstrap determinista (semilla fija) para que el IC sea reproducible.
"""

from __future__ import annotations

import datetime
import json
import os
import random
import sys

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(AQUI, "data", "cache")

# ---- constantes de coste (idénticas en todos los experimentos) ----
FEE_PCT = 0.05  # fee taker por lado
SLIP_BASE = 0.02  # slippage base por lado, en %
SLIP_K = 0.25  # slippage proporcional al ATR%, por lado
BOOT = 10000
SEMILLA = 42
P_TOP = 0.858  # cuartil superior de prob_modelo (medido en el gate)


def coste_viaje(atr_pct_val: float) -> float:
    """Coste de ida y vuelta en %: fee x2 + slippage (base + k·ATR) x2."""
    return FEE_PCT * 2 + SLIP_BASE * 2 + SLIP_K * (atr_pct_val or 0.0) * 2


# ------------------------------------------------------------------ datos --
def cargar_muestras():
    """Muestras de replay (sin la cabecera _meta)."""
    filas = []
    with open(os.path.join(CACHE, "expr_muestras.jsonl"), encoding="utf-8") as fh:
        for linea in fh:
            r = json.loads(linea)
            if r.get("_meta"):
                continue
            filas.append(r)
    return filas


def cargar_klines():
    """Klines 5m del cache, ordenadas por tiempo."""
    sys.path.insert(0, AQUI)
    import hold_model as hm  # noqa: E402

    kl = hm.load_klines_jsonl(os.path.join(CACHE, "klines_5m.jsonl"))
    kl.sort(key=lambda v: v["t"])
    return kl


def atr_pct(kl: list[dict], idx: int, n: int = 14):
    """ATR(n) como % del precio, usando solo velas cerradas hasta idx."""
    i0 = max(0, idx - n)
    trs = []
    prev = kl[i0]
    for v in kl[i0 : idx + 1]:
        tr = max(v["h"] - v["l"], abs(v["h"] - prev["c"]), abs(v["l"] - prev["c"]))
        trs.append(tr)
        prev = v
    if not trs:
        return None
    return (sum(trs) / len(trs)) / kl[idx]["c"] * 100.0


# ------------------------------------------------------- máquina de medidas --
def bootstrap_ci(vals, alpha: float = 0.05, boot: int = BOOT, semilla: int = SEMILLA):
    """IC por bootstrap (determinista) + p one-sided de la media > 0."""
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


def motor_secuencia(
    muestras,
    resolver,
    *,
    conviccion: str = "todas",
    p_top: float = P_TOP,
    cooldown_h: float = 4,
    hold_fn=None,
    ordenar_por_t: bool = True,
):
    """Simula un operador real: una posición a la vez + cooldown.

    `resolver(muestra)` devuelve un dict con al menos {"neto", "t"} o None si
    la muestra no genera operación. `hold_fn(r)` dice cuántas velas 5m duró el
    hold (por defecto se lee de `r["hold_barras"]`, y si no está, 48).
    """
    if conviccion == "todas":
        sel = list(muestras)
    else:
        sel = [m for m in muestras if m.get("prob_modelo", 0) >= p_top]
    if ordenar_por_t:
        sel = sorted(sel, key=lambda m: m["t"])
    rets, detalle = [], []
    libre = None
    for m in sel:
        t = datetime.datetime.fromisoformat(m["t"].replace("Z", "+00:00"))
        if libre is not None and t < libre:
            continue  # sigo dentro del hold/cooldown
        r = resolver(m)
        if r is None:
            continue
        if hold_fn is None:
            barras = r.get("hold_barras", 48)
        else:
            barras = hold_fn(r)
        fin = r["t"] + datetime.timedelta(minutes=5 * barras)
        libre = fin + datetime.timedelta(hours=cooldown_h)
        rets.append(r["neto"])
        detalle.append(r)
    return rets, detalle


def evaluar(rets, detalle):
    """Resumen estadístico de una celda. Incluye funding solo si el detalle lo trae."""
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
    regs = {}
    for nombre in ("compresion", "normal", "expansion"):
        v = [d["neto"] for d in detalle if d.get("vol") == nombre]
        regs[nombre] = {"n": len(v), "media": md(v)}
    out = {
        "n": n,
        "media": round(media, 4),
        "bruto_medio": round(sum(d["bruto"] for d in detalle) / n, 4),
        "coste_medio": round(sum(d["coste"] for d in detalle) / n, 4),
        "ic95": [round(lo, 4), round(hi, 4)],
        "p_boot": round(p, 5),
        "hit_rate": round(wins / n, 4),
        "profit_factor": round(gp / gl, 3) if gl > 0 else None,
        "equidad": round(eq, 2),
        "max_dd": round(mdd, 2),
        "mitades": {"h1": {"n": len(m1), "media": md(m1)}, "h2": {"n": len(m2), "media": md(m2)}},
        "regimenes": regs,
    }
    # el funding solo se publica cuando el experimento lo modelo (H6)
    if all("funding_pct" in d for d in detalle):
        out["funding_medio"] = round(sum(d["funding_pct"] for d in detalle) / n, 4)
    return out


def veredicto(c, costes_x2_media) -> str:
    """Criterio de muerte pre-registrado, por celda."""
    if not c:
        return "sin_datos"
    if c["n"] < 300:
        return "no_concluyente"
    ok = (
        c["media"] > 0
        and c["ic95"][0] > 0
        and (c["mitades"]["h1"]["media"] or 0) > 0
        and (c["mitades"]["h2"]["media"] or 0) > 0
        and sum(1 for k in c["regimenes"] if (c["regimenes"][k]["media"] or 0) > 0) >= 2
        and (costes_x2_media is None or costes_x2_media > 0)
    )
    return "edge" if ok else "sin_edge"
