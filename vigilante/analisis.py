#!/usr/bin/env python3
"""
analisis.py - ANALISIS TECNICO (Fase 6): velas -> indicadores por marco,
niveles/zonas, regimen, direccion con confianza, fear&greed, evaluacion de zonas.
"""

import datetime
from typing import Any

from vigilante.indicadores import (
    adx,
    atr,
    atr_regime,
    clamp,
    eficiencia,
    ema,
    ema_series,
    rsi,
    slope,
    structure,
    zscore,
)
from vigilante.mercado import snap_nivel
from vigilante.red import klines


def analyze(candles, mins, label):
    closes = [c["c"] for c in candles]
    last = closes[-1]
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    r = rsi(closes)
    sl = slope(closes[-14:])
    slpct = round(sl / last * 100, 3) if last else 0
    at = atr(candles)
    atpct = round(at / last * 100, 2) if last else 0
    macd_pos = 0
    if len(closes) >= 40:
        ef = ema_series(closes, 12)
        es = ema_series(closes, 26)
        macd_line = [a - b for a, b in zip(ef, es)]
        sig = ema_series(macd_line, 9)
        macd_pos = 1 if macd_line[-1] - sig[-1] > 0 else -1
    s_sign, s_label = structure(candles[-60:])
    s = (
        (1 if last > e20 else -1)
        + (1 if e20 > e50 else -1)
        + (1 if sl > 0 else -1)
        + macd_pos
        + s_sign
    )
    tend = "ALCISTA" if s >= 3 else ("BAJISTA" if s <= -3 else "lateral")
    win14 = candles[-14:]
    wh = max(c["h"] for c in win14)
    wl = min(c["l"] for c in win14)
    prior = candles[: max(0, len(candles) - 14)]
    vp = (sum(c["v"] for c in prior) / len(prior)) if prior else last
    va = sum(c["v"] for c in win14) / 14
    vol = round(va / vp * 100) if vp > 0 else 100
    all_c = candles[-40:]
    r_all = max(c["h"] for c in all_c) - min(c["l"] for c in all_c)
    comp = round((wh - wl) / r_all, 2) if r_all > 0 else 1.0
    now = datetime.datetime.now(datetime.timezone.utc)
    rem = max(0, (candles[-1]["t"] + datetime.timedelta(minutes=mins) - now).total_seconds() / 60)
    reg_pct, reg_label = atr_regime(candles[-90:])
    return {
        "tf": label,
        "tend": tend,
        "score": s,
        "rsi": r,
        "volRel": vol,
        "ema20": round(e20),
        "ema50": round(e50),
        "slopePct": slpct,
        "winH": round(wh),
        "winL": round(wl),
        "atr": round(at),
        "atrPct": atpct,
        "compresion": comp,
        "precio": round(last),
        "cierreEnMin": round(rem),
        "macd": macd_pos,
        "estructura": s_label,
        "regPct": reg_pct,
        "regLabel": reg_label,
        "adx": adx(candles),
        "er": eficiencia(closes),
        "z": zscore(closes),
    }


def pivots(interval, label):
    try:
        d = klines(interval, 2)
        y = d[-2]
        p = (y["h"] + y["l"] + y["c"]) / 3
        return {
            "etq": label,
            "P": round(p),
            "R1": round(2 * p - y["l"]),
            "S1": round(2 * p - y["h"]),
            "R2": round(p + (y["h"] - y["l"])),
            "S2": round(p - (y["h"] - y["l"])),
        }
    except Exception:
        return None


def ficha_zona(est, nivel):
    """Marcador de la zona: ' (aguanta H/R)' si tiene historia, '' si es nueva."""
    try:
        m = (est.get("mem_zonas") or {}).get(str(int(float(nivel))))
        if isinstance(m, dict):
            h, r = int(m.get("hold", 0) or 0), int(m.get("rompe", 0) or 0)
            if h + r > 0:
                return f" (aguanta {h}/{h + r})"
    except Exception:
        pass
    return ""


def evalua_zona(est, res, sop, high, low, close):
    """Memoria de zonas con la vela 1H cerrada. Cuenta EPISODIOS, no pasadas:
    mecha sin cierre = hold (aguanta); cierre mas alla = rompe (penaliza).
    Vuelve a tocar tras alejarse = episodio nuevo."""
    try:
        mem: dict[str, Any] = est.get("mem_zonas")
        if not isinstance(mem, dict):
            mem = {}
        vig: dict[str, Any] = est.get("vig_zona")
        if not isinstance(vig, dict):
            vig = {}
        for lado, nueva, es_res in (("res", res, True), ("sop", sop, False)):
            try:
                prev = vig.get(lado)
                # prev puede no existir (primera pasada) o venir corrupto del
                # estado.json: en ambos casos ant=None y la zona se inicializa.
                ant = float(prev["nivel"]) if isinstance(prev, dict) else None
            except Exception:
                ant = None
            if ant is None:
                if nueva:
                    vig[lado] = {"nivel": nueva, "toc": False}
                continue
            key = str(int(ant))
            z = mem.get(key)
            if not isinstance(z, dict):
                z = {"hold": 0, "rompe": 0}
            toc = bool((vig.get(lado) or {}).get("toc"))
            if es_res:
                roto = close is not None and close > ant
                wherein = (
                    high is not None and high >= ant * 0.999 and (close is None or close <= ant)
                )
            else:
                roto = close is not None and close < ant
                wherein = low is not None and low <= ant * 1.001 and (close is None or close >= ant)
            if roto:
                z["rompe"] = int(z.get("rompe", 0) or 0) + 1
                toc = False
            elif wherein:
                if not toc:
                    z["hold"] = int(z.get("hold", 0) or 0) + 1
                toc = True
            else:
                toc = False
            mem[key] = z
            vig[lado] = {"nivel": nueva, "toc": toc} if nueva else {"toc": False}
        if len(mem) > 60:
            mem = dict(
                sorted(
                    mem.items(),
                    key=lambda kv: -((kv[1] or {}).get("hold", 0) + (kv[1] or {}).get("rompe", 0)),
                )[:60]
            )
        est["mem_zonas"] = mem
        est["vig_zona"] = vig
    except Exception:
        pass


def niveles(h1, h4, d1, w1, pd, pw, precio):
    sups: list[dict] = []
    ress: list[dict] = []
    cands = [
        ("min14 1H", h1["winL"]),
        ("max14 1H", h1["winH"]),
        ("min14 4H", h4["winL"]),
        ("max14 4H", h4["winH"]),
        ("min14 1D", d1["winL"]),
        ("max14 1D", d1["winH"]),
        ("min14 1S", w1["winL"]),
        ("max14 1S", w1["winH"]),
        ("S1 diario", pd["S1"] if pd else None),
        ("R1 diario", pd["R1"] if pd else None),
        ("S2 diario", pd["S2"] if pd else None),
        ("R2 diario", pd["R2"] if pd else None),
        ("S1 semanal", pw["S1"] if pw else None),
        ("R1 semanal", pw["R1"] if pw else None),
    ]
    # Confluencia: varias fuentes que caen en el mismo nivel de la rejilla
    # valen mas que una sola. Se guardan TODAS las fuentes, no solo la primera.
    for o, v in cands:
        if v is None or v <= 0:
            continue
        v = snap_nivel(v)
        arr = sups if v < precio else ress
        hit = next((x for x in arr if abs(x["precio"] - v) < 20), None)
        if hit is not None:
            ops = hit.setdefault("origenes", [hit["origen"]])
            if o not in ops:
                ops.append(o)
            hit["n"] = len(ops)
        else:
            arr.append({"precio": v, "origen": o, "origenes": [o], "n": 1})
    if not sups:
        sups.append(
            {
                "precio": h1["winL"],
                "origen": "min14 1H cercano",
                "origenes": ["min14 1H cercano"],
                "n": 1,
            }
        )
    if not ress:
        ress.append(
            {
                "precio": h1["winH"],
                "origen": "max14 1H cercano",
                "origenes": ["max14 1H cercano"],
                "n": 1,
            }
        )
    # [0] sigue siendo el nivel MAS CERCANO (asi lo espera el resto del bot y el
    # dashboard). La confluencia viaja en "n"/"origenes" para mostrarla, no para
    # reordenar: un techo lejano no debe tapar al que estas tocando.
    sups.sort(key=lambda x: x["precio"], reverse=True)
    ress.sort(key=lambda x: x["precio"])
    return {"soportes": sups[:3], "resistencias": ress[:3]}


def fuentes_nivel(item, max_n=3):
    """Texto corto de las fuentes de un nivel: 'max14 1H + R1 diario'."""
    try:
        ops = item.get("origenes") or ([item.get("origen")] if item.get("origen") else [])
        ops = [o for o in ops if o]
        if not ops:
            return ""
        extra = "" if len(ops) <= max_n else f" +{len(ops) - max_n}"
        return " + ".join(ops[:max_n]) + extra
    except Exception:
        return ""


def confluencia_nivel(item):
    """Cuantas fuentes distintas forman el nivel (1 = una sola)."""
    try:
        return int(item.get("n") or len(item.get("origenes") or [1]))
    except Exception:
        return 1


def regimen_operativo(h1, h4):
    """Clasifica el mercado para decidir si vale la pena avisar de entradas.
    chop    = ruido puro (1H ER bajo y 4H sin ADX): no operar.
    rango   = lateral con algo de fuerza: solo niveles, no persecucion.
    tendencia = hay direccion y fuerza.
    """
    try:
        er = h1.get("er")
        adx4 = h4.get("adx") or 0
        adx1 = h1.get("adx") or 0
        er = 1.0 if er is None else float(er)
        if er < 0.25 and adx4 < 20 and adx1 < 20:
            return "chop"
        if adx4 >= 22 and (h4.get("tend") or "lateral") != "lateral":
            return "tendencia"
        return "rango"
    except Exception:
        return "rango"


def direccion(h1, h4, d1, w1):
    # Filtro chop: si el 1H es puro ruido (ER<0.25), no sesgar (no perseguir).
    er1 = h1.get("er") if isinstance(h1, dict) else None
    if er1 is not None and er1 < 0.25:
        return {"bias": "LATERAL", "score": 0.0, "confianza": 0}
    w4, wd, ws = 1.5, 2.0, 1.0
    s = h1["score"] * 1.0 + h4["score"] * w4 + d1["score"] * wd + w1["score"] * ws
    norm = s / 27.5
    bias = "ALZA" if norm >= 0.25 else ("BAJA" if norm <= -0.25 else "LATERAL")
    return {"bias": bias, "score": round(norm, 2), "confianza": round(abs(norm) * 100)}


def fear_greed(d1, senti, chg24):
    """Medidor miedo/codicia 0-100 con componentes explicables."""
    comps = {}
    comps["RSI 1D"] = clamp(d1["rsi"], 0, 100)
    f = senti["funding"] if senti["funding"] is not None else 0.0
    comps["funding"] = clamp(50 + f * 500, 0, 100)
    tk = senti["taker"] if senti["taker"] is not None else 1.0
    comps["taker"] = clamp((tk - 0.7) / 0.6 * 100, 0, 100)
    comps["vol"] = 100 - d1["regPct"]
    dist = (d1["precio"] - d1["ema50"]) / d1["ema50"] * 100 if d1["ema50"] else 0
    comps["tendencia"] = clamp(50 + dist * 10, 0, 100)
    comps["24h"] = clamp(50 + chg24 * 10, 0, 100)
    w = {
        "RSI 1D": 0.25,
        "funding": 0.15,
        "taker": 0.15,
        "vol": 0.15,
        "tendencia": 0.15,
        "24h": 0.15,
    }
    val = round(sum(comps[k] * w[k] for k in comps))
    if val < 25:
        label = "Miedo extremo"
    elif val < 45:
        label = "Miedo"
    elif val < 55:
        label = "Neutral"
    elif val < 75:
        label = "Codicia"
    else:
        label = "Codicia extrema"
    return {"valor": val, "etiqueta": label, "comp": {k: round(v) for k, v in comps.items()}}


def proxima_sesion():
    now = datetime.datetime.now(datetime.timezone.utc)

    def _siguiente(hora, minuto):
        # F8: antes siempre sumaba +1 día, así que a las 03:00 UTC decía que la
        # próxima Londres era "en ~29 h" (mañana) en vez de hoy. Ahora calcula la
        # próxima ocurrencia real (hoy si aún no pasó, si no mañana).
        d = now.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if d <= now:
            d += datetime.timedelta(days=1)
        return d

    ld = _siguiente(8, 0)
    ny = _siguiente(13, 30)
    h_l = (ld - now).total_seconds() / 3600
    h_n = (ny - now).total_seconds() / 3600
    if h_l <= h_n:
        return f"Londres 08:00 UTC en ~{round(h_l, 1)} h"
    return f"NY 13:30 UTC en ~{round(h_n, 1)} h"
