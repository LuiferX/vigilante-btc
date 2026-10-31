#!/usr/bin/env python3
"""
expr_edge.py - MISION EDGE 2026-10-31: H1 (funding extremo -> reversion).

Pre-registro: analysis/EXPERIMENTOS.md, seccion "MISION EDGE 2026-10-31"
(commiteado ANTES de correr esto). Gate de datos: docs/audit/EDGE_DATA.md
(H2 detenida por falta de datos: la API de OI/taker no baja de 30 dias).

Reglas duras implementadas aqui:
  - CERO look-ahead: los percentiles son causales (solo datos < t) y la
    entrada es al OPEN del bar 5m SIGUIENTE al timestamp de funding.
  - Costes SIEMPRE: fee taker 0,05% x2 + slippage por lado + funding
    cobrado/pagado durante el hold.
  - Eventos independientes: cooldown explicito (24 h variante A, 8 h variante B).
  - Bootstrap 10.000 con semilla fija (determinista).
  - Resultado negativo se publica igual.

stdlib puro. Uso:
    python analysis/expr_edge.py --hipotesis h1
"""

from __future__ import annotations

import argparse
import bisect
import datetime
import json
import math
import os
import random
import sys

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(AQUI, "data", "cache")

# ---------------- parametros fijados en el pre-registro ----------------
VENTANA_DIAS = 30        # percentiles causales de los 30 dias trailing
MIN_OBS = 30             # minimo de obs para calcular percentiles
P_ALTO, P_BAJO = 0.95, 0.05
HORIZONTES = {"4h": 48, "8h": 96, "12h": 144, "24h": 288}
COOLDOWNS = {"A24h": 24, "B8h": 8}
FEE_PCT = 0.05           # taker por lado
SLIP_BASE = 0.02         # % base por lado
SLIP_K = 0.25            # x ATR% por lado
BOOT = 10000
SEMILLA = 42
FEE_PAGO_HORAS = 8       # el funding se paga cada 8h


# ------------------------------------------------------------------ datos --
def cargar_funding():
    filas = []
    p = os.path.join(CACHE, "funding.jsonl")
    with open(p, encoding="utf-8") as fh:
        for linea in fh:
            r = json.loads(linea)
            filas.append((datetime.datetime.fromtimestamp(r["fundingTime"] / 1000, UTC),
                          float(r["fundingRate"])))
    filas.sort(key=lambda x: x[0])
    return filas


def cargar_klines():
    sys.path.insert(0, AQUI)
    import hold_model as hm  # noqa: E402
    p = os.path.join(CACHE, "klines_5m.jsonl")
    kl = hm.load_klines_jsonl(p)
    kl.sort(key=lambda v: v["t"])
    return kl


def percentil(vals, q):
    s = sorted(vals)
    if not s:
        return None
    i = min(len(s) - 1, max(0, int(q * len(s))))
    return s[i]


def atr_pct(kl, idx, n=14):
    """ATR(n) como % del precio, usando velas cerradas hasta idx."""
    i0 = max(0, idx - n)
    trs = []
    prev = kl[i0]
    for v in kl[i0:idx + 1]:
        tr = max(v["h"] - v["l"], abs(v["h"] - prev["c"]), abs(v["l"] - prev["c"]))
        trs.append(tr)
        prev = v
    if not trs:
        return None
    atr = sum(trs) / len(trs)
    px = kl[idx]["c"]
    return atr / px * 100.0 if px else None


# ------------------------------------------------------------- simulación --
def eventos_h1(funding, kl, cooldown_h):
    """Eventos independientes de H1 con todo el detalle para evaluar."""
    tiempos = [v["t"] for v in kl]
    ftimes = [t for t, _ in funding]
    fvals = [v for _, v in funding]
    eventos = []
    ultimo = None
    ventana = datetime.timedelta(days=VENTANA_DIAS)
    for i, (t, f) in enumerate(funding):
        i0 = bisect.bisect_left(ftimes, t - ventana)
        pasado = fvals[i0:i]           # SOLO la ventana trailing: cero look-ahead
        if len(pasado) < MIN_OBS:
            continue
        pa, pb = percentil(pasado, P_ALTO), percentil(pasado, P_BAJO)
        # Comparacion ESTRICTA (> y <): un valor que EMPATA con el percentil
        # no es "extremo". El 27,1% de los registros de funding de BTCUSDT es
        # exactamente +0.0001 (tasa por defecto de Binance); con >= el p95 de
        # la ventana empataba con el default y disparaba eventos falsos en el
        # 16,6% de las ventanas medidas. Corregido: mas estricto, no menos.
        if f > pa:
            lado = "SHORT"      # punta larga -> corto
        elif f < pb:
            lado = "LONG"       # punta corta -> largo
        else:
            continue
        if ultimo is not None and (t - ultimo).total_seconds() < cooldown_h * 3600:
            continue
        ultimo = t
        # entrada: open del bar 5m siguiente
        j = bisect.bisect_right(tiempos, t)
        if j >= len(kl):
            continue
        entrada = kl[j]["o"]
        t_ent = kl[j]["t"]
        atrp = atr_pct(kl, j) or 0.05
        # funding cobrado/pagado durante el hold (hasta cada horizonte)
        eventos.append({
            "t": t, "t_ent": t_ent, "lado": lado, "funding": f,
            "umbral_alto": pa, "umbral_bajo": pb,
            "entrada": entrada, "atr_pct": atrp,
        })
    return eventos


def resolver(evento, kl, tiempos, horizonte_barras):
    """Retorno NETO de un evento para un horizonte. None si no hay datos."""
    j = bisect.bisect_left(tiempos, evento["t_ent"])
    k = j + horizonte_barras
    if k >= len(kl):
        return None
    entrada = evento["entrada"]
    salida = kl[k]["c"]
    if evento["lado"] == "SHORT":
        bruto = (entrada - salida) / entrada * 100.0
    else:
        bruto = (salida - entrada) / entrada * 100.0
    # funding durante el hold (cada 8h); rate es fraccion -> x100 para %
    fin = kl[k]["t"]
    pagos = funding_en_rango(evento["t_ent"], fin, evento["lado"]) * 100.0
    coste = FEE_PCT * 2 + SLIP_BASE * 2 + SLIP_K * evento["atr_pct"] * 2
    neto = bruto + pagos - coste
    return {"bruto": bruto, "funding_pct": pagos, "coste": coste,
            "neto": neto, "t": evento["t_ent"], "atr_pct": evento["atr_pct"]}


_FUNDING_TS = []      # timestamps de funding, para bisect
_FUNDING_RATES = []   # rates alineados a _FUNDING_TS


def _indexar_funding(filas):
    global _FUNDING_TS, _FUNDING_RATES
    _FUNDING_TS = [t for t, _ in filas]
    _FUNDING_RATES = [r for _, r in filas]


def funding_en_rango(ini, fin, lado):
    """Suma de funding (fraccion) cobrado/pagado entre ini y fin.

    Cada pago es cada 8h. Convencion correcta del PnL del que mantiene:
      - LARGO  cobra si rate<0 (y paga si rate>0)  -> aporte = -rate
      - CORTO  cobra si rate>0 (y paga si rate<0) -> aporte = +rate
    (una senal de reversion siempre entra del lado que COBRA: corto con
    funding positivo, largo con funding negativo). Bisect sobre los
    timestamps: solo se recorren los pagos que tocan el hold (0-3).
    """
    i = bisect.bisect_left(_FUNDING_TS, ini)
    total = 0.0
    while i < len(_FUNDING_TS) and _FUNDING_TS[i] < fin:
        total += -_FUNDING_RATES[i] if lado == "LONG" else _FUNDING_RATES[i]
        i += 1
    return total


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


def evaluar_celda(rets,detalle, mitad, regimenes):
    if not rets:
        return None
    n = len(rets)
    media = sum(rets) / n
    lo, hi, p = bootstrap_ci(rets)
    wins = sum(1 for r in rets if r > 0)
    gp = sum(r for r in rets if r > 0)
    gl = -sum(r for r in rets if r <= 0)
    pf = gp / gl if gl > 0 else None
    var = sum((r - media) ** 2 for r in rets) / (n - 1) if n > 1 else 0.0
    sharpe = media / math.sqrt(var) if var > 0 else None
    # curva de equity y drawdown
    eq, pico, mdd = 0.0, 0.0, 0.0
    for r in rets:
        eq += r
        pico = max(pico, eq)
        mdd = max(mdd, pico - eq)
    bruto = sum(d["bruto"] for d in detalle) / n
    fund = sum(d["funding_pct"] for d in detalle) / n
    coste = sum(d["coste"] for d in detalle) / n
    return {
        "n": n,
        "media": round(media, 4),
        "bruto_medio": round(bruto, 4),
        "funding_medio": round(fund, 4),
        "coste_medio": round(coste, 4),
        "ic95": [round(lo, 4), round(hi, 4)],
        "p_boot": round(p, 5),
        "hit_rate": round(wins / n, 4),
        "profit_factor": round(pf, 3) if pf is not None else None,
        "sharpe_por_op": round(sharpe, 3) if sharpe is not None else None,
        "equidad": round(eq, 2), "max_dd": round(mdd, 2),
        "mitades": mitad, "regimenes": regimenes,
    }


def ejecutar(cooldown_nombre, cooldown_h):
    funding = cargar_funding()
    kl = cargar_klines()
    tiempos = [v["t"] for v in kl]
    _indexar_funding(funding)
    evs = eventos_h1(funding, kl, cooldown_h)
    if not evs:
        return None

    # regimenes de volatilidad: ATR% por encima/debajo de la mediana
    atrs = [e["atr_pct"] for e in evs]
    med_atr = sorted(atrs)[len(atrs) // 2]
    corte_mitad = evs[len(evs) // 2]["t"]

    celdas = {}
    for hnombre, hbars in HORIZONTES.items():
        rets, detalle = [], []
        for e in evs:
            r = resolver(e, kl, tiempos, hbars)
            if r is None:
                continue
            rets.append(r["neto"])
            detalle.append(r)
        if not rets:
            celdas[hnombre] = None
            continue
        # mitades temporales
        m1 = [d["neto"] for d in detalle if d["t"] < corte_mitad]
        m2 = [d["neto"] for d in detalle if d["t"] >= corte_mitad]
        # regimenes de volatilidad (baja/alta por mediana de ATR)
        baj = [d["neto"] for d in detalle if d["atr_pct"] <= med_atr]
        alt = [d["neto"] for d in detalle if d["atr_pct"] > med_atr]

        def media(x):
            return round(sum(x) / len(x), 4) if x else None

        celdas[hnombre] = evaluar_celda(rets, detalle, {
            "h1": {"n": len(m1), "media": media(m1)},
            "h2": {"n": len(m2), "media": media(m2)},
        }, {
            "baja": {"n": len(baj), "media": media(baj)},
            "alta": {"n": len(alt), "media": media(alt)},
        })

    # costes x2 (sensibilidad)
    celdas_x2 = {}
    for hnombre, hbars in HORIZONTES.items():
        rets = []
        for e in evs:
            r = resolver(e, kl, tiempos, hbars)
            if r is None:
                continue
            neto2 = r["bruto"] + r["funding_pct"] - (FEE_PCT * 2 + SLIP_BASE * 2 + SLIP_K * e["atr_pct"] * 2) * 2
            rets.append(neto2)
        celdas_x2[hnombre] = (round(sum(rets) / len(rets), 4) if rets else None)

    # veredicto (criterio de muerte por celda)
    veredictos = {}
    for hnombre, c in celdas.items():
        if not c:
            veredictos[hnombre] = "sin_datos"
            continue
        if c["n"] < 300:
            # el pre-registro exige >=300 eventos: con menos, no se puede
            # dictar veredicto economico -> no concluyente (no es un "no edge")
            veredictos[hnombre] = "no_concluyente"
            continue
        pasa = (c["media"] > 0 and c["ic95"][0] > 0
                and (c["mitades"]["h1"]["media"] or 0) > 0
                and (c["mitades"]["h2"]["media"] or 0) > 0
                and sum(1 for k in ("baja", "alta")
                        if (c["regimenes"][k]["media"] or 0) > 0) >= 2
                and (celdas_x2[hnombre] or -1) > 0)
        veredictos[hnombre] = "edge" if pasa else "sin_edge"

    return {"cooldown": cooldown_nombre, "n_eventos": len(evs),
            "celdas": celdas, "costes_x2": celdas_x2, "veredicto": veredictos}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hipotesis", default="h1", choices=["h1", "h2"])
    a = ap.parse_args()

    if a.hipotesis == "h2":
        out = {"hipotesis": "H2",
               "veredicto": "no_concluyente",
               "razon": "gate de datos: la API de Binance limita OI y taker a "
                        "30 dias (probado: startTime de 31 dias -> HTTP 400); "
                        "no se alcanzan 300 eventos independientes. Ver "
                        "docs/audit/EDGE_DATA.md.",
               "n_independientes": 0}
        p = os.path.join(AQUI, "data", "edge_liq.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print("H2: no concluyente por falta de datos (ver edge_liq.json)")
        return 0

    res = {}
    for nombre, horas in COOLDOWNS.items():
        r = ejecutar(nombre, horas)
        if r:
            res[nombre] = r
            print(f"--- cooldown {nombre}: {r['n_eventos']} eventos independientes")
            for h, c in r["celdas"].items():
                if c:
                    print(f"    {h:>4s} n={c['n']:4d} media={c['media']:+.4f}% "
                          f"ic95=[{c['ic95'][0]:+.4f}, {c['ic95'][1]:+.4f}] "
                          f"hit={c['hit_rate']:.2f} -> {r['veredicto'][h]}")

    p_boots = [r["celdas"][h]["p_boot"] for r in res.values()
               for h in r["celdas"] if r["celdas"][h]]
    n_celdas = len(p_boots)
    p_corregido = min(1.0, (min(p_boots) * n_celdas) if p_boots else 1.0)

    out = {"hipotesis": "H1", "parametros": {
        "ventana_dias": VENTANA_DIAS, "p_alto": P_ALTO, "p_bajo": P_BAJO,
        "horizontes": list(HORIZONTES), "cooldowns": list(COOLDOWNS),
        "fee_pct": FEE_PCT, "slip_base_pct": SLIP_BASE, "slip_k": SLIP_K,
        "bootstrap": BOOT, "semilla": SEMILLA},
        "variantes_probadas": n_celdas, "p_corregido": round(p_corregido, 5),
        "resultados": res,
        "veredicto": "sin_edge"}
    for r in res.values():
        if any(v == "edge" for v in r["veredicto"].values()):
            out["veredicto"] = "edge"
    p = os.path.join(AQUI, "data", "edge_funding.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\np_corregido (Bonferroni {n_celdas} celdas): {p_corregido:.5f}")
    print(f"veredicto global: {out['veredicto']}")
    print(f"OK -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
