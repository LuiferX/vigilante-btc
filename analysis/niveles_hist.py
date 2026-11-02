#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""niveles_hist.py - SUELOS Y TECHOS HISTORICOS de verdad.

El detector de niveles del sistema (`vigilante/analisis.py`) solo mira las
ultimas 14 velas de cada marco: 14 horas en 1H, 3,5 meses en 1S. No tiene ni
idea de lo que paso antes. Este modulo usa el archivo de 4 anos de velas 5m
(`analysis/data/cache/klines_5m.jsonl`) para decir, de cada nivel activo:

  - cuantas veces se ha probado en TODA la historia (visitas distintas)
  - cuando se toco por primera y por ultima vez
  - cuanto reboto y cuanto barrio tras cada toque (mediana)
  - que porcentaje de las veces AGUANTO (ningun cierre 0,5% mas alla en 4h):
    exactamente el target del modelo congelado, para que sea comparable
  - en que percentil de fuerza esta frente a todos los niveles de la historia

Reglas:
  - Un toque es una VISITA DISTINTA: entra en la zona (tol), sale 0,3%, y
    vuelve al menos `sep` velas despues. Un rango pegado no cuenta (igual que
    vigilante/toques.py, para que los numeros sean comparables).
  - Las excursiones se miden SOLO con velas POSTERIORES al toque: cero
    look-ahead.
  - La historia se declara con su fecha de corte: si el cache es viejo, se dice.

Uso:
    python analysis/niveles_hist.py                     # top historicos
    python analysis/niveles_hist.py --nivel 112340      # un nivel concreto
    python analysis/niveles_hist.py --precio 113500     # contra un precio dado
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
CACHE = os.path.join(AQUI, "data", "cache")
COLECTOR = os.path.join(os.path.dirname(AQUI), "collector", "data", "btcusdt")

TOL = 0.0015  # 0,15%: mitad de la zona (igual que vigilante/toques.py)
SALIDA = 0.003  # 0,3% para que el toque cuente como cerrado
SEP = 12  # 1 h en 5m entre visitas distintas
BARRAS_HOLD = 48  # 4 h: horizonte del target del modelo
HOLD_PCT = 0.5  # 0,5% mas alla del nivel = "no aguanto"
K_PIVOTE = 5  # pivote fractal: maximo/minimo local de 5 velas a cada lado


# ------------------------------------------------------------------ datos --
def cargar_historial():
    """4 anos de velas 5m, ordenadas."""
    sys.path.insert(0, AQUI)
    import hold_model as hm

    kl = hm.load_klines_jsonl(os.path.join(CACHE, "klines_5m.jsonl"))
    kl.sort(key=lambda v: v["t"])
    return kl


def precio_actual():
    """Precio vivo: ultimo cierre del colector (fresco), no del cache viejo."""
    p = os.path.join(COLECTOR, "klines_5m.jsonl")
    ultimo = None
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    r = json.loads(linea)
                except Exception:
                    continue
                c = r.get("close", r.get("c"))
                if c is None:
                    continue
                ultimo = float(c)
    return ultimo


# ------------------------------------------------------- detectar niveles --
def pivotes(kl, k=K_PIVOTE):
    """Maximos/minimos locales (fractal) sobre toda la serie.

    Devuelve (indices, precios, es_techo) para poder agrupar por POSICION, no
    solo por precio: dos niveles parecidos en epocas distintas son el mismo.
    """
    idx: list[int] = []
    pre: list[float] = []
    for i in range(k, len(kl) - k):
        ventana = kl[i - k : i + k + 1]
        if kl[i]["h"] >= max(x["h"] for x in ventana):
            idx.append(i)
            pre.append(kl[i]["h"])
        if kl[i]["l"] <= min(x["l"] for x in ventana):
            idx.append(i)
            pre.append(kl[i]["l"])
    return idx, pre


def candidatos(kl, cuantos=40):
    """Clusters de pivotes (baratos) ordenados por cuantos pivotes agrupan.

    Es un filtro previo: escanear la serie completa por cada candidato seria
    O(niveles x velas). Con esto solo se paga el escaneo caro por los mejores.
    """
    idx, pre = pivotes(kl)
    orden = sorted(range(len(pre)), key=lambda j: pre[j])
    clusters: list[dict] = []
    for j in orden:
        p = pre[j]
        hit = clusters[-1] if clusters else None
        if hit and abs(hit["precio"] - p) / p <= TOL:
            hit["n"] += 1
            hit["precio"] = (hit["precio"] * (hit["n"] - 1) + p) / hit["n"]
        else:
            clusters.append({"precio": p, "n": 1})
    clusters.sort(key=lambda c: -c["n"])
    return clusters[:cuantos], len(idx)


def toques_distintos(kl, nivel, tol=TOL, salida=SALIDA, sep=SEP):
    """Indices de las velas donde se INICIA una visita distinta al nivel."""
    idx = []
    dentro, last = False, -(10**9)
    for i, x in enumerate(kl):
        en_zona = x["l"] <= nivel * (1 + tol) and x["h"] >= nivel * (1 - tol)
        if en_zona and not dentro and (i - last) >= sep:
            idx.append(i)
            dentro = True
            last = i
        elif not en_zona and abs(x["c"] - nivel) / nivel >= salida:
            dentro = False
    return idx


def medir_toque(kl, i, nivel, barras=BARRAS_HOLD):
    """Excursiones tras un toque. Cero look-ahead: solo velas > i."""
    fin = min(i + barras, len(kl) - 1)
    if fin <= i:
        return None
    ventana = kl[i + 1 : fin + 1]
    if not ventana:
        return None
    max_h = max(v["h"] for v in ventana)
    min_l = min(v["l"] for v in ventana)
    # "aguanta" = ningun CIERRE 0,5% mas alla del nivel (target del modelo)
    aguanta = not any(
        (v["c"] < nivel * (1 - HOLD_PCT / 100)) or (v["c"] > nivel * (1 + HOLD_PCT / 100))
        for v in ventana
    )
    return {
        "rebote_pct": (max_h - nivel) / nivel * 100,
        "barrido_pct": (nivel - min_l) / nivel * 100,
        "aguanta": aguanta,
        "barras": len(ventana),
    }


def mediana(vals):
    s = sorted(vals)
    if not s:
        return None
    return s[len(s) // 2]


def ficha(kl, nivel, ts=None):
    """Ficha completa de un nivel sobre la historia dada."""
    idx = toques_distintos(kl, nivel)
    if not idx:
        return None
    rebotes, barridos, aguantan = [], [], 0
    for i in idx:
        m = medir_toque(kl, i, nivel)
        if not m:
            continue
        rebotes.append(m["rebote_pct"])
        barridos.append(m["barrido_pct"])
        aguantan += 1 if m["aguanta"] else 0
    n = len(rebotes)
    if n == 0:
        return None
    return {
        "nivel": round(nivel, 2),
        "toques": n,
        "primero": (ts[idx[0]] if ts else kl[idx[0]]["t"]).isoformat(),
        "ultimo": (ts[idx[-1]] if ts else kl[idx[-1]]["t"]).isoformat(),
        "rebote_mediano_pct": round(mediana(rebotes), 4),
        "barrido_mediano_pct": round(mediana(barridos), 4),
        "aguante_pct": round(100.0 * aguantan / n, 1),
        "aguante_n": aguantan,
    }


# ------------------------------------------------------------ informe ------
def top_historicos(kl, cuantos=8, min_toques=4, escanear=40, precio=None, cerca_pct=None):
    """Niveles historicos ordenados por RESPETO, no por cuantas veces se cruzaron.

    Un nivel que el precio atravesso 400 veces no es un suelo: es una autopista.
    Lo que distingue un suelo de verdad es que, tras tocarlo, reboto mas de lo
    que barrio y que aguanto (ningun cierre 0,5% mas alla en 4h). Por eso se
    ordena por `aguante_pct` (el target del modelo) y se ofrece `respeto`.
    """
    cands, _ = candidatos(kl, cuantos=escanear)
    fichas = []
    for c in cands:
        f = ficha(kl, c["precio"])
        if not f or f["toques"] < min_toques:
            continue
        rb = f["rebote_mediano_pct"] or 0.0
        ba = f["barrido_mediano_pct"] or 0.0
        f["respeto"] = round(rb / ba, 2) if ba > 0 else None
        if precio:
            f["distancia_pct"] = round((f["nivel"] - precio) / precio * 100, 3)
            f["lado"] = "soporte" if f["nivel"] < precio else "resistencia"
            if cerca_pct is not None and abs(f["distancia_pct"]) > cerca_pct:
                continue
        fichas.append(f)
    fichas.sort(key=lambda f: (-f["aguante_pct"], -(f["respeto"] or 0), -f["toques"]))
    return fichas[:cuantos]


def percentil_fuerza(kl, nivel, todas):
    """Percentil de fuerza: cuantos niveles de la historia tienen menos toques."""
    vals = sorted(f["toques"] for f in todas)
    if not vals:
        return None
    t = nivel.get("toques", 0)
    return round(bisect.bisect_left(vals, t) / len(vals), 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nivel", type=float)
    ap.add_argument("--precio", type=float)
    ap.add_argument("--cuantos", type=int, default=8)
    ap.add_argument("--cerca", type=float, default=8.0, help="% maximo de distancia al precio")
    ap.add_argument("--min-toques", type=int, default=4)
    a = ap.parse_args()

    kl = cargar_historial()
    px = a.precio or precio_actual()
    corte = kl[-1]["t"]
    print(
        f"historia: {len(kl)} velas 5m | {kl[0]['t']:%Y-%m-%d} -> {corte:%Y-%m-%d} "
        f"| precio vivo: {px if px else 'desconocido'}"
    )

    if a.nivel:
        f = ficha(kl, a.nivel)
        print(
            json.dumps(f, ensure_ascii=False, indent=2)
            if f
            else "  ese nivel no tiene toques distinguibles"
        )
        return 0 if f else 1

    todas = top_historicos(kl, cuantos=100, min_toques=a.min_toques, precio=px, cerca_pct=None)
    print(f"niveles respetados (>={a.min_toques} toques) en la historia: " f"{len(todas)}")

    bloque_cerca = top_historicos(
        kl, cuantos=a.cuantos, min_toques=a.min_toques, precio=px, cerca_pct=a.cerca
    )
    bloque_lejos = top_historicos(
        kl, cuantos=a.cuantos, min_toques=a.min_toques, precio=px, cerca_pct=None
    )

    def pintar(titulo, filas):
        if not filas:
            return
        print("\n" + titulo)
        for f in filas:
            dist = f.get("distancia_pct")
            print(
                "  {:>9.0f}  {:>10}  toques={:<4} aguanta={:>5.1f}%  "
                "respeto={:>5}  rebote={:>6.3f}%  barrido={:>6.3f}%{}".format(
                    f["nivel"],
                    f.get("lado", "-"),
                    f["toques"],
                    f["aguante_pct"],
                    f.get("respeto"),
                    f["rebote_mediano_pct"] or 0,
                    f["barrido_mediano_pct"] or 0,
                    ("  a {:+.2f}%".format(dist) if dist is not None else ""),
                )
            )

    pintar("=== cerca del precio (<{}%) ===".format(a.cerca), bloque_cerca)
    pintar("=== los mas respetados de la historia ===", bloque_lejos)

    out = {
        "generado": datetime.datetime.now(UTC).isoformat(),
        "historia": {"velas": len(kl), "desde": kl[0]["t"].isoformat(), "hasta": corte.isoformat()},
        "precio": px,
        "cerca_pct": a.cerca,
        "cerca": bloque_cerca,
        "global": bloque_lejos,
    }
    p = os.path.join(AQUI, "data", "niveles_hist.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\nOK -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
