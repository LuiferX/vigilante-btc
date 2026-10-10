#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vigilante_cloud.py - VIGILANTE BTCUSDT v2 PRO (1H 4H 1D 1S) en la nube.

Nivel casi-comercial:
 - Confluencia multi-timeframe: EMA20/50 + pendiente (regresion) + RSI + MACD
   + ESTRUCTURA de mercado (HH/HL vs LH/LL) -> score -5..+5 por marco.
 - Soportes/resistencias agrupadas: fractales de 14 velas por marco + pivotes
   diario y semanal.
 - Sentimiento de futuros (publico): funding rate, open interest, ratio taker L/S.
 - Regimen de volatilidad (percentil de ATR en el historico).
 - Momento probable: distancia en horas por ATR, proxima apertura de sesion,
   cierre de vela 4H, compresion (fuelle).

SEGURIDAD:
 - Solo API PUBLICA de Binance Futures (fapi.binance.com). Sin API keys, sin
   trading, no envia datos fuera salvo el parte a Telegram.
 - Secretos (token de Telegram y chat ID) por VARIABLES DE ENTORNO
   (GitHub Actions Secrets). Nunca en el repositorio.

USO:
  python vigilante_cloud.py                   -> envia el parte a Telegram
  python vigilante_cloud.py (sin variables)   -> imprime el parte y guarda parte_cloud.txt
"""

import datetime
import json
import math
import os
import time
import urllib.request

BASE = "https://fapi.binance.com/fapi/v1"
DATA = "https://fapi.binance.com/futures/data"


def fetch(url, timeout=20, tries=3):
    """GET con reintentos (transparente ante caidas de la API)."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vigilante-cloud/2.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            if i < tries - 1:
                time.sleep(2 * (i + 1))
    raise last


def klines(interval, limit):
    data = fetch(f"{BASE}/klines?symbol=BTCUSDT&interval={interval}&limit={limit}")
    return [
        {
            "t": datetime.datetime.fromtimestamp(k[0] / 1000, datetime.timezone.utc),
            "o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
            "c": float(k[4]), "v": float(k[5]),
        }
        for k in data
    ]


def ticker24():
    t = fetch(f"{BASE}/ticker/24hr?symbol=BTCUSDT")
    return {
        "last": float(t["lastPrice"]),
        "chg": float(t["priceChangePercent"]),
        "hi": float(t["highPrice"]),
        "lo": float(t["lowPrice"]),
    }


def sentiment():
    """Sentimiento de futuros (endpoints publicos). Fallo parcial = n/d."""
    out = {"funding": None, "oi": None, "taker": None}
    try:
        f = fetch(f"{BASE}/premiumIndex?symbol=BTCUSDT")
        out["funding"] = round(float(f["lastFundingRate"]) * 100, 4)
    except Exception:
        pass
    try:
        oi = fetch(f"{BASE}/openInterest?symbol=BTCUSDT")
        out["oi"] = float(oi["openInterest"])
    except Exception:
        pass
    try:
        t = fetch(f"{DATA}/takerlongshortRatio?symbol=BTCUSDT&period=1h&limit=1")
        if t:
            out["taker"] = round(float(t[-1]["buySellRatio"]), 3)
    except Exception:
        pass
    return out


def ema_series(vals, n):
    if not vals:
        return []
    k = 2.0 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def ema(vals, n):
    if len(vals) < n:
        return vals[-1]
    return ema_series(vals, n)[-1]


def rsi(closes):
    if len(closes) < 15:
        return 50.0
    win = closes[-15:]
    g = p = 0.0
    for i in range(1, len(win)):
        d = win[i] - win[i - 1]
        if d >= 0:
            g += d
        else:
            p -= d
    if p == 0:
        return 100.0
    return round(100 - 100 / (1 + g / p), 1)


def slope(vals):
    n = len(vals)
    if n < 3:
        return 0.0
    sx = sy = sxy = sxx = 0.0
    for i, y in enumerate(vals):
        sx += i
        sy += y
        sxy += i * y
        sxx += i * i
    den = n * sxx - sx * sx
    if den == 0:
        return 0.0
    return (n * sxy - sx * sy) / den


def atr(candles):
    n = len(candles)
    if n < 3:
        return 0.0
    trs = []
    for i in range(1, n):
        pc = candles[i - 1]["c"]
        trs.append(max(candles[i]["h"] - candles[i]["l"],
                       abs(candles[i]["h"] - pc),
                       abs(candles[i]["l"] - pc)))
    return sum(trs[-14:]) / min(14, len(trs))


def atr_regime(candles):
    """Percentil del ATR actual dentro del historico (regimen de volatilidad)."""
    hists = []
    for i in range(14, len(candles), 5):
        hists.append(atr(candles[i - 14:i]))
    cur = atr(candles[-14:])
    if not hists:
        return 50.0, "Media"
    pct = round(sum(1 for x in hists if x <= cur) / len(hists) * 100)
    label = "Baja" if pct < 25 else ("Alta" if pct >= 75 else "Media")
    return pct, label


def detect_swings(candles, k=2):
    highs, lows = [], []
    n = len(candles)
    for i in range(k, n - k):
        if all(candles[i]["h"] >= candles[j]["h"] for j in range(i - k, i + k + 1) if j != i):
            highs.append(candles[i]["h"])
        if all(candles[i]["l"] <= candles[j]["l"] for j in range(i - k, i + k + 1) if j != i):
            lows.append(candles[i]["l"])
    return highs, lows


def structure(candles):
    """Estructura: HH/HL (alcista), LH/LL (bajista) o mezcla."""
    highs, lows = detect_swings(candles)
    hh = hl = None
    if len(highs) >= 2:
        hh = highs[-1] > highs[-2]
    if len(lows) >= 2:
        hl = lows[-1] > lows[-2]
    if hh is True and hl is True:
        return 1, "HH/HL alcista"
    if hh is False and hl is False:
        return -1, "LH/LL bajista"
    return 0, "estructura mixta"


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
    # MACD
    macd_pos = 0
    if len(closes) >= 40:
        ef = ema_series(closes, 12)
        es = ema_series(closes, 26)
        macd_line = [a - b for a, b in zip(ef, es)]
        sig = ema_series(macd_line, 9)
        macd_pos = 1 if macd_line[-1] - sig[-1] > 0 else -1
    # Estructura
    s_sign, s_label = structure(candles[-60:])
    # score -5..+5
    s = (1 if last > e20 else -1) + (1 if e20 > e50 else -1) + \
        (1 if sl > 0 else -1) + macd_pos + s_sign
    tend = "ALCISTA" if s >= 3 else ("BAJISTA" if s <= -3 else "lateral")
    vol = 100
    win14 = candles[-14:]
    wh = max(c["h"] for c in win14)
    wl = min(c["l"] for c in win14)
    prior = candles[:max(0, len(candles) - 14)]
    vp = (sum(c["v"] for c in prior) / len(prior)) if prior else last
    va = sum(c["v"] for c in win14) / 14
    if vp > 0:
        vol = round(va / vp * 100)
    all_c = candles[-40:]
    r_all = max(c["h"] for c in all_c) - min(c["l"] for c in all_c)
    comp = round((wh - wl) / r_all, 2) if r_all > 0 else 1.0
    now = datetime.datetime.now(datetime.timezone.utc)
    rem = max(0, (candles[-1]["t"] + datetime.timedelta(minutes=mins) - now).total_seconds() / 60)
    reg_pct, reg_label = atr_regime(candles[-90:])
    return {
        "tf": label, "tend": tend, "score": s, "rsi": r, "volRel": vol,
        "ema20": round(e20), "ema50": round(e50), "slopePct": slpct,
        "winH": round(wh), "winL": round(wl), "atr": round(at), "atrPct": atpct,
        "compresion": comp, "precio": round(last), "cierreEnMin": round(rem),
        "macd": macd_pos, "estructura": s_label, "regPct": reg_pct, "regLabel": reg_label,
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


def niveles(h1, h4, d1, w1, pd, pw, precio):
    sups, ress = [], []
    cands = [
        ("min14 1H", h1["winL"]), ("max14 1H", h1["winH"]),
        ("min14 4H", h4["winL"]), ("max14 4H", h4["winH"]),
        ("min14 1D", d1["winL"]), ("max14 1D", d1["winH"]),
        ("min14 1S", w1["winL"]), ("max14 1S", w1["winH"]),
        ("S1 diario", pd["S1"] if pd else None), ("R1 diario", pd["R1"] if pd else None),
        ("S2 diario", pd["S2"] if pd else None), ("R2 diario", pd["R2"] if pd else None),
        ("S1 semanal", pw["S1"] if pw else None), ("R1 semanal", pw["R1"] if pw else None),
    ]
    for o, v in cands:
        if v is None or v <= 0:
            continue
        v = round(v)
        dup = lambda arr: any(abs(x["precio"] - v) < 20 for x in arr)
        if v < precio:
            if not dup(sups):
                sups.append({"precio": v, "origen": o})
        else:
            if not dup(ress):
                ress.append({"precio": v, "origen": o})
    if not sups:
        sups.append({"precio": h1["winL"], "origen": "min14 1H cercano"})
    if not ress:
        ress.append({"precio": h1["winH"], "origen": "max14 1H cercano"})
    sups.sort(key=lambda x: x["precio"], reverse=True)
    ress.sort(key=lambda x: x["precio"])
    return {"soportes": sups[:3], "resistencias": ress[:3]}


def direccion(h1, h4, d1, w1):
    w4, wd, ws = 1.5, 2.0, 2.0
    s = h1["score"] * 1.0 + h4["score"] * w4 + d1["score"] * wd + w1["score"] * ws
    norm = s / 32.5  # 5 * (1.0+1.5+2.0+2.0)
    bias = "ALZA" if norm >= 0.25 else ("BAJA" if norm <= -0.25 else "LATERAL")
    return {"bias": bias, "score": round(norm, 2), "confianza": round(abs(norm) * 100)}


def proxima_sesion():
    now = datetime.datetime.now(datetime.timezone.utc)
    ld = (now + datetime.timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    ny = (now + datetime.timedelta(days=1)).replace(hour=13, minute=30, second=0, microsecond=0)
    h_l = (ld - now).total_seconds() / 3600
    h_n = (ny - now).total_seconds() / 3600
    if h_l <= h_n:
        return f"Londres 08:00 UTC en ~{round(h_l, 1)} h"
    return f"NY 13:30 UTC en ~{round(h_n, 1)} h"


def fmt_miles(x):
    return f"{x:,.0f}".replace(",", ".")


def sesion_hora():
    hh = datetime.datetime.now(datetime.timezone.utc).hour + datetime.datetime.now(datetime.timezone.utc).minute / 60
    if 8 <= hh < 13.5:
        return "Londres"
    if 13.5 <= hh < 21.5:
        return "Londres+NY (solape)"
    return "fuera de sesion"


def build_parte(t, h1, h4, d1, w1, pd, pw, niv, dirb, prox, senti):
    res = niv["resistencias"][0]
    sup = niv["soportes"][0]
    horas_res = round((res["precio"] - t["last"]) / h1["atr"], 1) if h1["atr"] > 0 else None
    horas_sup = round((t["last"] - sup["precio"]) / h1["atr"], 1) if h1["atr"] > 0 else None
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%d/%m %H:%M UTC")

    icon = {"ALCISTA": "🟢", "BAJISTA": "🔴", "lateral": "🟡"}

    L = []
    L.append("🤖 VIGILANTE BTC v2 PRO")
    L.append(f"📅 {now}  |  {sesion_hora()}")
    L.append("=================================")
    L.append(f"💰 PRECIO: {fmt_miles(t['last'])}  ({t['chg']:+.2f}% 24h)")
    L.append(f"📈 max {fmt_miles(t['hi'])} / min {fmt_miles(t['lo'])}")
    L.append("")
    L.append(f"🧭 DIRECCION: {dirb['bias']} (confianza {dirb['confianza']}%)")
    for x in (h1, h4, d1, w1):
        L.append(f"  {icon.get(x['tend'],'🟡')} {x['tf']}: {x['tend'].upper()} (s{x['score']:+d}) "
                 f"RSI {x['rsi']} | MACD {'+' if x['macd']>0 else '-'}")
    L.append("")
    s_txt = "  |  ".join(f"{fmt_miles(x['precio'])} ({x['origen']})" for x in niv["soportes"])
    r_txt = "  |  ".join(f"{fmt_miles(x['precio'])} ({x['origen']})" for x in niv["resistencias"])
    L.append(f"🟢 SOPORTES: {s_txt}")
    L.append(f"🔴 RESISTENCIAS: {r_txt}")
    L.append("")
    if dirb["bias"] == "ALZA":
        L.append(f"🎯 Objetivo: cierre 1H SOBRE {fmt_miles(res['precio'])} ({res['origen']})")
        L.append(f"⏱ Distancia ~{horas_res} h (ATR 1H)")
    elif dirb["bias"] == "BAJA":
        L.append(f"🎯 Objetivo: cierre 1H BAJO {fmt_miles(sup['precio'])} ({sup['origen']})")
        L.append(f"⏱ Distancia ~{horas_sup} h (ATR 1H)")
    else:
        L.append(f"⚖️ RANGO {fmt_miles(sup['precio'])} - {fmt_miles(res['precio'])}")
        L.append("   Esperar ruptura con volumen en sesion.")
    L.append(f"⏰ Proxima sesion: {prox} | vela 4H en {h4['cierreEnMin']} min")
    coil = [x["tf"] for x in (h1, h4, d1, w1) if x["compresion"] < 0.5]
    if coil:
        L.append(f"🌀 Compresion: {', '.join(coil)} (antes de expansion)")
    L.append(f"🌡 Volatilidad: {h1['regLabel']} ({h1['regPct']}% percentil ATR 1H)")
    L.append("")
    sent = []
    if senti["funding"] is not None:
        sent.append(f"funding {senti['funding']:+.4f}%")
    if senti["oi"] is not None:
        sent.append(f"OI {fmt_miles(senti['oi'] * t['last'])}$")
    if senti["taker"] is not None:
        sent.append(f"taker L/S {senti['taker']}")
    if sent:
        L.append("⚡ FUTUROS: " + " | ".join(sent))
    L.append("")
    L.append("⚠️ Analisis probabilistico, no asesoramiento financiero.")
    return "\n".join(L)


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode("ascii"))
        with open("parte_cloud.txt", "w", encoding="utf-8") as fh:
            fh.write(text)
        print("\n[modo local] Variables TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ausentes.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()
    return True


def main():
    try:
        t = ticker24()
        h1 = analyze(klines("1h", 72), 60, "1H")
        h4 = analyze(klines("4h", 60), 240, "4H")
        d1 = analyze(klines("1d", 60), 1440, "1D")
        w1 = analyze(klines("1w", 52), 10080, "1S")
        pd = pivots("1d", "D")
        pw = pivots("1w", "S")
        niv = niveles(h1, h4, d1, w1, pd, pw, t["last"])
        dirb = direccion(h1, h4, d1, w1)
        prox = proxima_sesion()
        senti = sentiment()
        msg = build_parte(t, h1, h4, d1, w1, pd, pw, niv, dirb, prox, senti)
        ok = send_telegram(msg)
        print("Enviado OK" if ok else "NO enviado (modo local)")
    except Exception as e:  # noqa: BLE001
        err = f"⚠️ El Vigilante fallo: {e}"
        try:
            print(err)
        except UnicodeEncodeError:
            pass
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if token and chat:
            send_telegram(err)
        raise SystemExit(1)


if __name__ == "__main__":
    main()