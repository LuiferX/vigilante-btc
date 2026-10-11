#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entrenar.py - LABORATORIO: mide como se mueve BTCUSDT y propone calibracion.

Lee 500 velas 1H + 200 velas 4H reales (Binance) y mide:
 1. Volatilidad por hora (percentiles) -> umbral de brusco honesto
 2. Movimiento 8h tipico -> valida ventana EVAL y umbral ATR
 3. Factibilidad del plan 2R (rango 8h >= 2R disponible?)
 4. Sesiones: cual se mueve (Asia/Londres/NY/noche)
 5. Regimen ADX4H: % tiempo en tendencia vs rango
 6. Compresion -> expansion (el fuelle paga?)
Solo mide y propone. No toca el bot.
"""
import datetime
import json
import urllib.request

H = {"User-Agent": "entrenamiento/1.0"}


def get(url):
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def klines(interval, limit):
    base = "https://fapi.binance.com/fapi/v1"
    try:
        data = get(f"{base}/klines?symbol=BTCUSDT&interval={interval}&limit={limit}")
    except Exception:
        base = "https://data-api.binance.vision/api/v3"
        data = get(f"{base}/klines?symbol=BTCUSDT&interval={interval}&limit={limit}")
    return [{"t": datetime.datetime.fromtimestamp(k[0] / 1000, datetime.timezone.utc),
             "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])}
            for k in data]


def pct(vals, p):
    s = sorted(vals)
    if not s:
        return 0.0
    k = (len(s) - 1) * p / 100
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def ema(vals, n):
    e = vals[0]
    k = 2.0 / (n + 1)
    for x in vals[1:]:
        e = x * k + e * (1 - k)
    return e


def adx_calc(candles, n=14):
    m = len(candles)
    if m < n + 5:
        return 0.0
    trs, pdm, mdm = [], [], []
    for i in range(1, m):
        h, l, pc = candles[i]["h"], candles[i]["l"], candles[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - candles[i - 1]["h"], candles[i - 1]["l"] - l
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
    atr = sum(trs[:n])
    pd = sum(pdm[:n])
    md = sum(mdm[:n])
    dxs = []
    for i in range(n, len(trs)):
        atr = atr - atr / n + trs[i]
        pd = pd - pd / n + pdm[i]
        md = md - md / n + mdm[i]
        if atr <= 0:
            continue
        pip, mip = 100 * pd / atr, 100 * md / atr
        dxs.append(0.0 if pip + mip == 0 else 100 * abs(pip - mip) / (pip + mip))
    if not dxs:
        return 0.0
    tail = dxs[-n:]
    return sum(tail) / len(tail)


def sesion(h):
    if 0 <= h < 8:
        return "Asia"
    if 8 <= h < 13:
        return "Londres"
    if 13 <= h < 21:
        return "NY"
    return "noche"


def main():
    h1 = klines("1h", 500)
    h4 = klines("4h", 200)
    print(f"Velas: {len(h1)}x1H ({h1[0]['t']:%d/%m} -> {h1[-1]['t']:%d/%m %H:%M}) + {len(h4)}x4H")
    rets = []
    atrs = []
    for i in range(1, len(h1)):
        rets.append(abs(h1[i]["c"] / h1[i - 1]["c"] - 1) * 100)
        trs = [(c["h"] - c["l"]) for c in h1[max(0, i - 14):i]]
        atrs.append(sum(trs) / len(trs) / h1[i]["c"] * 100)
    print("\n[1] VOLATILIDAD HORARIA |ret| %:")
    print(f"    mediana {pct(rets, 50):.3f} | p75 {pct(rets, 75):.3f} | "
          f"p90 {pct(rets, 90):.3f} | p95 {pct(rets, 95):.3f} | p99 {pct(rets, 99):.3f}")
    print(f"    ATR14h medio: {sum(atrs) / len(atrs):.3f}%")
    print("\n[2] VENTANA 8H (rango maximo alcanzable):")
    hits2r = 0
    movs8 = []
    tot = 0
    for i in range(14, len(h1) - 8):
        atr = sum((c["h"] - c["l"]) for c in h1[i - 14:i]) / 14
        ruin = max(0.002 * h1[i]["c"], atr * 0.5)
        fut = h1[i + 1:i + 9]
        rg = max(c["h"] for c in fut) - min(c["l"] for c in fut)
        movs8.append(rg / h1[i]["c"] * 100)
        if rg >= 2 * ruin:
            hits2r += 1
        tot += 1
    print(f"    movimiento 8h mediano {pct(movs8, 50):.2f}% | p75 {pct(movs8, 75):.2f}%")
    print(f"    2R disponible en 8h: {hits2r}/{tot} = {hits2r / tot * 100:.0f}% de las horas")
    print("\n[3] SESIONES (movimiento medio |ret| y % horas calientes>0.5%):")
    for s in ("Asia", "Londres", "NY", "noche"):
        idx = [i for i in range(1, len(h1)) if sesion(h1[i]["t"].hour) == s]
        rr = [rets[i - 1] for i in idx]
        cal = sum(1 for x in rr if x > 0.5) / len(rr) * 100 if rr else 0
        print(f"    {s:8s} n={len(rr):4d} |ret|medio={sum(rr) / len(rr):.3f}% calientes={cal:.0f}%")
    print("\n[4] REGIMEN ADX(4H):")
    adxs = []
    for i in range(30, len(h4)):
        adxs.append(adx_calc(h4[max(0, i - 60):i + 1]))
    t25 = sum(1 for a in adxs if a >= 25) / len(adxs) * 100
    t20 = sum(1 for a in adxs if a >= 20) / len(adxs) * 100
    print(f"    ADX medio {sum(adxs) / len(adxs):.1f} | tendencia(>=25): {t25:.0f}% | >=20: {t20:.0f}% | chop: {100 - t20:.0f}%")
    print("\n[5] COMPRESION 1H (rango14/rango40 < 0.35) paga en 8h?")
    comp, norm = [], []
    for i in range(40, len(h1) - 8):
        r14 = max(c["h"] for c in h1[i - 14:i]) - min(c["l"] for c in h1[i - 14:i])
        r40 = max(c["h"] for c in h1[i - 40:i]) - min(c["l"] for c in h1[i - 40:i])
        fut = h1[i + 1:i + 9]
        rg = (max(c["h"] for c in fut) - min(c["l"] for c in fut)) / h1[i]["c"] * 100
        (comp if r14 / r40 < 0.35 else norm).append(rg)
    print(f"    tras compresion (n={len(comp)}): mov8 mediano {pct(comp, 50):.2f}%")
    print(f"    normal (n={len(norm)}): mov8 mediano {pct(norm, 50):.2f}%")


if __name__ == "__main__":
    main()
