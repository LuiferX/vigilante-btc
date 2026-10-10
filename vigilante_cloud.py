#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vigilante_cloud.py - VIGILANTE BTCUSDT v3 (1H 4H 1D 1S) en la nube.

Novedades v3:
 - ALERTAS INTELIGENTES: solo envia a Telegram cuando hay senal (cambio de
   direccion, confianza alta, toque de nivel) + resumen en aperturas. Sin ruido.
 - MIEDO/CODICIA 0-100: RSI 1D, funding, taker L/S, volatilidad, tendencia, 24h.
 - HISTORIAL Y PRECISION: guarda cada pasada y evalua las senales enviadas
   8 h despues (acierto = precio se movio >=0.2% a favor). Muestra precision real.
 - Estado en rama 'estado' del repo (main queda limpio, solo codigo).

SEGURIDAD: solo API publica de Binance (+ espejo vision si bloquean).
Secretos por variables de entorno. Sin API keys, sin trading.
"""

import datetime
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

FAPI = "https://fapi.binance.com/fapi/v1"
FDATA = "https://fapi.binance.com/futures/data"
VISION = "https://data-api.binance.vision/api/v3"
FUENTE = {"nombre": "futuros"}

# ---------------- Noticias (prensa) y calendario (eventos futuros) --------

FEEDS = [
    'https://cointelegraph.com/rss',
    'https://cryptoslate.com/feed/',
    'https://decrypt.co/feed',
    'https://bitcoinmagazine.com/feed',
    'https://bitcoinist.com/feed/',
    'https://watcher.guru/news/feed',
    'https://www.theblock.co/rss.xml',
]
GRUPOS = [
    ('macro', 6, r'\b(fed|fomc|rate[- ]?cut|rate[- ]?hike|inflation|cpi|treasury|yield|recession|tariff|dollar)\b'),
    ('institucional', 4, r'\b(etf|blackrock|fidelity|microstrateg|mstr|institution|sovereign|reserve|adoption)\b'),
    ('regulacion', 4, r'\b(sec|gensler|regulat|court|ruling|lawsuit|cftc|doj|indict|charged)\b'),
    ('flujos', 5, r'\b(binance|coinbase|tether|usdt|stablecoin|outflow|inflow)\b'),
    ('red', 2, r'\b(halving|hash[- ]?rate|mining|miner|difficulty|lightning|ordinals)\b'),
]
EXPLICA = {
    'macro': 'macro EE.UU.: mueve al dolar y a todo el riesgo, incluido BTC',
    'institucional': 'dinero grande (ETFs/empresas): entradas = compra, salidas = venta',
    'regulacion': 'reglas y juicios: deciden si el dinero grande entra o sale',
    'flujos': 'movimiento en exchanges/stablecoins: anticipa compra o venta',
    'red': 'salud de la red Bitcoin (mineria): efecto lento, poco inmediato',
}


def peso_noticia(titulo):
    t = titulo.lower()
    s = 0
    tags = []
    if re.search(r'\bbtc\b', t) or 'bitcoin' in t:
        s += 4
    for tag, peso, rx in GRUPOS:
        if re.search(rx, t):
            s += peso
            tags.append(tag)
    return s, tags


def impacto_noticia(score):
    if score >= 9:
        return 'ALTO (±2-6%)'
    if score >= 6:
        return 'MEDIO (±0.5-2%)'
    return 'BAJO (<±1%)'


def explicar_noticia(tags):
    if not tags:
        return 'tema crypto general con posible efecto en BTC'
    return ' + '.join(EXPLICA[t] for t in tags[:2])


def noticias(limit=5):
    titulos = []
    for f in FEEDS:
        try:
            req = urllib.request.Request(f, headers={"User-Agent": "vigilante-cloud/3.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                raw = r.read()
            root = ET.fromstring(raw)
            n = 0
            for el in root.iter():
                if el.tag.split('}')[-1] not in ('item', 'entry'):
                    continue
                if n >= 6:
                    break
                titulo = ''
                for ch in el:
                    if ch.tag.split('}')[-1] == 'title' and ch.text:
                        titulo = ch.text.strip()
                        break
                if titulo:
                    titulos.append(titulo)
                    n += 1
        except Exception:
            continue
    scored = []
    vistos = set()
    for tt in titulos:
        if tt in vistos:
            continue
        vistos.add(tt)
        s, tags = peso_noticia(tt)
        if s >= 5:
            scored.append({"titulo": tt, "score": s, "tags": tags})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


CAL_EXP = [
    (r'fomc|fed funds|rate decision|statement', 'la Fed decide las tasas: el evento que mas mueve a BTC'),
    (r'\bcpi\b', 'inflacion de EE.UU.: si sale alta, caen los activos de riesgo'),
    (r'nfp|non-farm|nonfarm|unemployment|jobless|payroll', 'empleo de EE.UU.: dato fuerte = menos recortes = cae BTC'),
    (r'\bpce\b', 'inflacion favorita de la Fed (PCE)'),
    (r'\bppi\b', 'inflacion mayorista (PPI): adelanta al CPI'),
    (r'retail sales', 'ventas minoristas: mide al consumidor de EE.UU.'),
    (r'\bgdp\b', 'crecimiento (PIB) de EE.UU.'),
    (r'powell|fomc member|testimony|speech', 'habla la Fed: cada palabra mueve al dolar y a BTC'),
]


def explicar_evento(titulo):
    t = titulo.lower()
    for rx, exp in CAL_EXP:
        if re.search(rx, t):
            return exp
    return 'dato macro de EE.UU.: mueve al dolar y a BTC'


def impacto_evento(impact):
    return 'ALTO (±3-8%)' if impact == 'High' else 'MEDIO (±0.5-2%)'


def calendario(limit=5):
    evs = []
    try:
        req = urllib.request.Request(
            'https://nfs.faireconomy.media/ff_calendar_thisweek.json',
            headers={"User-Agent": "vigilante-cloud/3.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
    except Exception:
        return []
    ahora = datetime.datetime.now(datetime.timezone.utc)
    for e in data:
        if e.get('country') != 'USD':
            continue
        if e.get('impact') not in ('High', 'Medium'):
            continue
        try:
            cuando = datetime.datetime.fromisoformat(e['date'].replace('Z', '+00:00'))
        except Exception:
            continue
        if cuando <= ahora:
            continue
        evs.append({"titulo": e.get('title', ''), "cuando": cuando, "impact": e.get('impact')})
    evs.sort(key=lambda x: x['cuando'])
    return evs[:limit]


def cuenta_regresiva(cuando, ahora):
    d = cuando - ahora
    dias = d.days
    hs = d.seconds // 3600
    ms = (d.seconds % 3600) // 60
    if dias > 0:
        return f"en {dias}d {hs}h"
    if hs > 0:
        return f"en {hs}h {ms}m"
    return f"en {ms}m"


BLOQUES = "▁▂▃▄▅▆▇█"


def sparkline(precios):
    """Mini-grafico 24h con caracteres de bloque (sin librerias)."""
    if not precios:
        return ""
    lo, hi = min(precios), max(precios)
    n = min(len(precios), 24)
    sel = precios[-n:]
    if hi <= lo:
        return BLOQUES[3] * n
    return "".join(BLOQUES[min(7, int((p - lo) / (hi - lo) * 8))] for p in sel)


def combustible(t, d1):
    """Cuanto le queda al dia vs su ATR: con nafta / medio / agotado."""
    if not d1["atr"]:
        return "n/d"
    uso = (t["hi"] - t["lo"]) / d1["atr"]
    if uso < 0.5:
        return f"con nafta ({round(uso * 100)}% del ATR usado)"
    if uso <= 1.0:
        return f"medio ({round(uso * 100)}% del ATR usado)"
    return f"agotado ({round(uso * 100)}% del ATR usado)"


def funding_flag(senti):
    """Funding extremo = un lado recargado (lectura contrarian)."""
    f = senti["funding"]
    if f is None:
        return None
    if f >= FUNDING_EXTREMO:
        return "longs recargados: cuidado con caídas (contrarian)"
    if f <= -FUNDING_EXTREMO:
        return "shorts recargados: cuidado con subidas (contrarian)"
    return None


def plan_entrada(dirb, niv, evs, ahora):
    """Checklist concreto: gatillo, stop, objetivo 2R, guardia de eventos, 1%."""
    res = niv["resistencias"][0]
    sup = niv["soportes"][0]
    lineas = []
    if dirb["bias"] == "ALZA":
        gatillo = res["precio"]
        stop = sup["precio"]
        obj = gatillo + (gatillo - stop) * 2
        lineas.append(f"ESPERA: cierre 1H SOBRE {fmt_miles(gatillo)} ({res['origen']}) con volumen")
        lineas.append(f"STOP: bajo {fmt_miles(stop)} ({sup['origen']}) · OBJETIVO: {fmt_miles(obj)} (2R)")
        lineas.append("NO entres antes del cierre ni persigas velas estiradas")
    elif dirb["bias"] == "BAJA":
        gatillo = sup["precio"]
        stop = res["precio"]
        obj = gatillo - (stop - gatillo) * 2
        lineas.append(f"ESPERA: cierre 1H BAJO {fmt_miles(gatillo)} ({sup['origen']}) con volumen")
        lineas.append(f"STOP: sobre {fmt_miles(stop)} ({res['origen']}) · OBJETIVO: {fmt_miles(obj)} (2R)")
        lineas.append("NO entres antes del cierre ni vendas el piso sin confirmación")
    else:
        lineas.append(f"ESPERA: ruptura de {fmt_miles(sup['precio'])} - {fmt_miles(res['precio'])} con volumen en sesión")
        lineas.append("Sin sesgo no hay plan: el que opera rangos sin reglas, dona")
    if evs:
        e0 = evs[0]
        lineas.append(f"GUARDIA: {e0['titulo']} {cuenta_regresiva(e0['cuando'], ahora)}: no operes encima del evento")
    lineas.append("Riesga máx 1% de tu cuenta por idea")
    return lineas


ESTADO_FILE = "estado.json"
HIST_FILE = "historial.jsonl"
MAX_HIST = 1500
EVAL_HORAS = 8
UMBRAL_MOV = 0.002
UMBRAL_CONF_FUERTE = 55
UMBRAL_CONF_CAMBIO = 40
UMBRAL_CONF_SENAL = 45
UMBRAL_TOQUE = 0.0025  # 0.25% del nivel = "tocando"
DEDUP_HORAS = 4          # misma direccion en 4 h = 1 sola senal (sin duplicados)
UMBRAL_ATR_MULT = 0.5    # acierto = moverse >= 0.5 * ATR 1H a favor (relativo al mercado)
MIN_SENALES = 5          # minimo de senales para mostrar % de precision
FUNDING_EXTREMO = 0.05   # |funding| >= 0.05% = un lado recargado (lectura contrarian)


def fetch(url, timeout=20, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vigilante-cloud/3.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            if i < tries - 1:
                time.sleep(2 * (i + 1))
    raise last


def klines(interval, limit):
    try:
        data = fetch(f"{FAPI}/klines?symbol=BTCUSDT&interval={interval}&limit={limit}")
    except Exception:
        data = fetch(f"{VISION}/klines?symbol=BTCUSDT&interval={interval}&limit={limit}", tries=2)
        FUENTE["nombre"] = "spot"
    return [
        {
            "t": datetime.datetime.fromtimestamp(k[0] / 1000, datetime.timezone.utc),
            "o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
            "c": float(k[4]), "v": float(k[5]),
        }
        for k in data
    ]


def ticker24():
    try:
        t = fetch(f"{FAPI}/ticker/24hr?symbol=BTCUSDT")
    except Exception:
        t = fetch(f"{VISION}/ticker/24hr?symbol=BTCUSDT", tries=2)
        FUENTE["nombre"] = "spot"
    return {
        "last": float(t["lastPrice"]),
        "chg": float(t["priceChangePercent"]),
        "hi": float(t["highPrice"]),
        "lo": float(t["lowPrice"]),
    }


def sentiment():
    out = {"funding": None, "oi": None, "taker": None}
    try:
        f = fetch(f"{FAPI}/premiumIndex?symbol=BTCUSDT", tries=1)
        out["funding"] = round(float(f["lastFundingRate"]) * 100, 4)
    except Exception:
        pass
    try:
        oi = fetch(f"{FAPI}/openInterest?symbol=BTCUSDT", tries=1)
        out["oi"] = float(oi["openInterest"])
    except Exception:
        pass
    try:
        t = fetch(f"{FDATA}/takerlongshortRatio?symbol=BTCUSDT&period=1h&limit=1", tries=1)
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
    macd_pos = 0
    if len(closes) >= 40:
        ef = ema_series(closes, 12)
        es = ema_series(closes, 26)
        macd_line = [a - b for a, b in zip(ef, es)]
        sig = ema_series(macd_line, 9)
        macd_pos = 1 if macd_line[-1] - sig[-1] > 0 else -1
    s_sign, s_label = structure(candles[-60:])
    s = (1 if last > e20 else -1) + (1 if e20 > e50 else -1) + \
        (1 if sl > 0 else -1) + macd_pos + s_sign
    tend = "ALCISTA" if s >= 3 else ("BAJISTA" if s <= -3 else "lateral")
    win14 = candles[-14:]
    wh = max(c["h"] for c in win14)
    wl = min(c["l"] for c in win14)
    prior = candles[:max(0, len(candles) - 14)]
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
    norm = s / 32.5
    bias = "ALZA" if norm >= 0.25 else ("BAJA" if norm <= -0.25 else "LATERAL")
    return {"bias": bias, "score": round(norm, 2), "confianza": round(abs(norm) * 100)}


def clamp(x, a, b):
    return max(a, min(b, x))


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
    w = {"RSI 1D": 0.25, "funding": 0.15, "taker": 0.15,
         "vol": 0.15, "tendencia": 0.15, "24h": 0.15}
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
    now = datetime.datetime.now(datetime.timezone.utc)
    hh = now.hour + now.minute / 60
    if 8 <= hh < 13.5:
        return "Londres"
    if 13.5 <= hh < 21.5:
        return "Londres+NY (solape)"
    return "fuera de sesion"


# ---------------- Companero: tono, narrativa, memoria, comandos ------------

ABRIDORES = [
    "Oye, te cuento lo que veo",
    "Reporte desde la nube",
    "Pasaba por aquí y vi esto",
    "Actualización del mercado",
    "Te traigo noticias frescas",
]
LECCIONES = [
    "Funding positivo alto = muchos longs apalancados: si el precio cae, las liquidaciones aceleran la caída.",
    "RSI sobre 70 no significa 'vende ya': en tendencias fuertes se queda arriba días. Mira la estructura.",
    "Un soporte roto se vuelve resistencia: el mercado tiene memoria de niveles.",
    "Compresión + volatilidad baja = el mercado carga energía. La expansión suele ser violenta.",
    "El volumen confirma: ruptura sin volumen suele ser trampa.",
    "Taker L/S sobre 1.2 = compradores agresivos; bajo 0.9 = vendedores agresivos.",
    "El ATR te dice el tamaño normal del movimiento: no esperes 5% en un mercado de 0.5%.",
    "Los fines de semana el volumen cae: los movimientos de domingo se revierten fácil el lunes.",
    "FOMC y CPI son los eventos que más mueven a BTC: opera menos (o nada) alrededor de ellos.",
    "La confianza del parte es confluencia de marcos: más marcos alineados = señal más seria.",
]


def narrar(dirb, h1, h4, d1, res, sup, precio):
    b, c = dirb["bias"], dirb["confianza"]
    if b == "ALZA":
        base = (f"los compradores mandan con {c}% de confianza: el corto plazo empuja "
                f"y busca romper {fmt_miles(res['precio'])}")
    elif b == "BAJA":
        base = (f"los vendedores mandan con {c}% de confianza: la presión va "
                f"hacia {fmt_miles(sup['precio'])}")
    else:
        if h1["tend"] == "ALCISTA":
            base = ("el corto plazo quiere subir pero los marcos grandes no confirman: mercado indeciso, "
                    f"atrapado entre {fmt_miles(sup['precio'])} y {fmt_miles(res['precio'])}")
        elif h1["tend"] == "BAJISTA":
            base = ("el corto plazo quiere caer pero los marcos grandes no confirman: mercado indeciso, "
                    f"atrapado entre {fmt_miles(sup['precio'])} y {fmt_miles(res['precio'])}")
        else:
            base = (f"nadie manda: todos los marcos laterales entre {fmt_miles(sup['precio'])} y "
                    f"{fmt_miles(res['precio'])}. Cuando esto pasa, el movimiento que rompa suele ser fuerte")
    extra = ""
    if h1["rsi"] >= 70:
        extra = " El 1H va caliente (RSI alto): puede seguir, pero no persigas entradas tarde."
    elif h1["rsi"] <= 30:
        extra = " El 1H va sobrevendido: los rebotes pueden ser bruscos."
    return base + "." + extra


def toques_hoy(hist, nivel, ahora):
    hoy = ahora.strftime("%Y-%m-%d")
    n = 0
    for h in hist:
        try:
            if not h.get("t", "").startswith(hoy):
                continue
            if abs(h["precio"] - nivel) / nivel <= UMBRAL_TOQUE:
                n += 1
        except Exception:
            continue
    return n


def vs_ayer(hist, precio, ahora):
    obj = (ahora - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H")
    cand = None
    for h in reversed(hist):
        if h.get("t", "")[:13] <= obj:
            cand = h
            break
    if not cand or not cand.get("precio"):
        return None
    return round((precio - cand["precio"]) / cand["precio"] * 100, 2)


def stats_fecha(hist, fecha):
    ps = [h["precio"] for h in hist if h.get("t", "").startswith(fecha) and h.get("precio")]
    bs = [h["bias"] for h in hist if h.get("t", "").startswith(fecha) and h.get("bias")]
    if not ps:
        return None
    dom = max(set(bs), key=bs.count) if bs else "?"
    return {"max": max(ps), "min": min(ps), "dom": dom, "n": len(ps)}


def stats_dia(hist, ahora):
    return stats_fecha(hist, ahora.strftime("%Y-%m-%d"))


def cierre_ayer(hist, ahora):
    ay = (ahora - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    ps = [h["precio"] for h in hist if h.get("t", "").startswith(ay) and h.get("precio")]
    return ps[-1] if ps else None


def leer_comandos(offset):
    """Lee mensajes nuevos dirigidos al bot (chat en 2 vías con retardo)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return [], offset
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=10"
        req = urllib.request.Request(url, headers={"User-Agent": "vigilante-cloud/3.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        msgs = []
        new_off = offset
        for u in data.get("result", [])[-10:]:
            new_off = max(new_off, u.get("update_id", 0) + 1)
            m = u.get("message", {})
            txt = (m.get("text") or "").strip()
            cid = (m.get("chat") or {}).get("id")
            if txt.startswith("/"):
                msgs.append({"chat": cid, "texto": txt.split()[0].lower(),
                             "nombre": ((m.get("from") or {}).get("first_name") or "")})
        return msgs, new_off
    except Exception:
        return [], offset


def responder_comando(cmd, ctx):
    """Solo responde al dueño (seguridad: verifica el chat)."""
    chat_ok = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if str(cmd["chat"]) != str(chat_ok):
        return None
    c = cmd["texto"]
    t = ctx["t"]
    dirb = ctx["dirb"]
    niv = ctx["niv"]
    fg = ctx["fg"]
    est = ctx["est"]
    res = niv["resistencias"][0]
    sup = niv["soportes"][0]
    if c == "/precio":
        return (f"BTC ahora: {fmt_miles(t['last'])} ({t['chg']:+.2f}% 24h). "
                f"Rango del día: {fmt_miles(t['lo'])} - {fmt_miles(t['hi'])}.")
    if c == "/direccion":
        return (f"Dirección: {dirb['bias']} (confianza {dirb['confianza']}%). "
                f"1H {ctx['h1']['tend']}, 4H {ctx['h4']['tend']}, "
                f"1D {ctx['d1']['tend']}, 1S {ctx['w1']['tend']}.")
    if c == "/niveles":
        return ("Soportes: " + " | ".join(fmt_miles(x['precio']) for x in niv['soportes']) +
                "\nResistencias: " + " | ".join(fmt_miles(x['precio']) for x in niv['resistencias']))
    if c == "/miedo":
        ff = f"{ctx['senti']['funding']:+.4f}%" if ctx['senti']['funding'] is not None else "n/d"
        tk = ctx['senti']['taker'] if ctx['senti']['taker'] is not None else "n/d"
        return f"{fg['etiqueta']}: {fg['valor']}/100 (RSI 1D {ctx['d1']['rsi']}, funding {ff}, taker {tk})."
    if c == "/noticias":
        ns = ctx["notis"][:3]
        if not ns:
            return "Sin noticias relevantes ahora mismo."
        return "Top noticias:\n" + "\n".join(f"• [{n['score']}] {n['titulo']}" for n in ns)
    if c == "/eventos":
        evs = ctx["evs"][:3]
        if not evs:
            return "Sin eventos fuertes esta semana."
        return "Próximos eventos:\n" + "\n".join(
            f"• {e['titulo']} ({e['cuando'].strftime('%a %d %H:%M')} UTC)" for e in evs)
    if c == "/precision":
        return (f"Precisión: ALZA {prec_str(est.get('alza', []))} · "
                f"BAJA {prec_str(est.get('baja', []))}.")
    hola = f" Hola {cmd['nombre']}." if cmd['nombre'] else " Hola."
    return (hola + " Te respondo en cada pasada (máx ~30 min).\n"
            "Comandos: /precio /direccion /niveles /miedo /noticias /eventos /precision")


# ---------------- Estado / historial / precision ----------------

def cargar_estado():
    est = {"ultimo_bias": "?", "ultima_conf": 0, "ultimo_precio": 0,
           "ultimo_run": "", "ultimo_resumen": "", "ultimo_resumen_noche": "",
           "alza": [], "baja": [], "pendientes": [], "offset": 0, "runs": 0, "vistas": []}
    try:
        with open(ESTADO_FILE, encoding="utf-8") as fh:
            est.update(json.load(fh))
    except Exception:
        pass
    hist = []
    try:
        with open(HIST_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    hist.append(json.loads(line))
    except Exception:
        pass
    return est, hist


def guardar_estado(est, hist):
    with open(ESTADO_FILE, "w", encoding="utf-8") as fh:
        json.dump(est, fh)
    hist = hist[-MAX_HIST:]
    with open(HIST_FILE, "w", encoding="utf-8") as fh:
        for h in hist:
            fh.write(json.dumps(h) + "\n")


def prec_str(lista):
    if len(lista) < MIN_SENALES:
        return f"pocas ({len(lista)})" if lista else "s/d"
    ok = sum(lista)
    return f"{round(ok / len(lista) * 100)}% ({ok}/{len(lista)})"


def evaluar(est, precio_now, ahora, umbral):
    """Evalua senales enviadas hace >= EVAL_HORAS: acierto si el precio se
    movio >= umbral (relativo al ATR) a favor."""
    nuevas_pend = []
    for p in est.get("pendientes", []):
        try:
            t0 = datetime.datetime.fromisoformat(p["t"])
            edad = (ahora - t0).total_seconds() / 3600
        except Exception:
            continue
        if edad < EVAL_HORAS:
            nuevas_pend.append(p)
            continue
        mov = (precio_now - p["precio"]) / p["precio"] if p["precio"] else 0
        if p["bias"] == "ALZA":
            hit = 1 if mov >= umbral else 0
            est["alza"] = (est.get("alza", []) + [hit])[-50:]
        elif p["bias"] == "BAJA":
            hit = 1 if mov <= -umbral else 0
            est["baja"] = (est.get("baja", []) + [hit])[-50:]
    est["pendientes"] = nuevas_pend


def decidir_alerta(precio, niv, dirb, est, ahora):
    """Devuelve (enviar, motivo, tipo). Tipos: alerta, preny, manana, madrugada, noche, ny, nada."""
    res = niv["resistencias"][0]
    sup = niv["soportes"][0]
    dist_res = (res["precio"] - precio) / precio if res["precio"] > 0 else 1
    dist_sup = (precio - sup["precio"]) / precio if precio > 0 else 1
    bias, conf = dirb["bias"], dirb["confianza"]
    prev = est.get("ultimo_bias", "?")
    if prev != "?" and prev != bias and bias in ("ALZA", "BAJA") and conf >= UMBRAL_CONF_CAMBIO:
        return True, f"Cambio de direccion: {prev} -> {bias}", "alerta"
    if bias in ("ALZA", "BAJA") and conf >= UMBRAL_CONF_FUERTE:
        return True, f"Senal fuerte {bias} (confianza {conf}%)", "alerta"
    if min(dist_res, dist_sup) <= UMBRAL_TOQUE:
        lado = f"resistencia {fmt_miles(res['precio'])}" if dist_res <= dist_sup else f"soporte {fmt_miles(sup['precio'])}"
        return True, f"Tocando {lado}", "alerta"
    hoy = ahora.strftime("%Y-%m-%d")
    hh = ahora.hour + ahora.minute / 60
    if ahora.hour == 13 and ahora.minute == 0 and est.get("ultimo_preny") != hoy:
        return True, "REPORTE PRE-NY (30 min para la apertura)", "preny"
    if ahora.hour == 7 and est.get("ultimo_madrugada") != hoy:
        return True, "Resumen nocturno (mientras dormías)", "madrugada"
    if 13 < hh < 17:
        return True, "NY en vivo", "ny"
    if 8 <= hh < 9 and est.get("ultimo_resumen") != f"{hoy}-manana":
        return True, "Buenos días, plan del día (Londres)", "manana"
    if hh >= 20.5 and est.get("ultimo_resumen_noche") != hoy:
        return True, "Buenas noches, resumen del día", "noche"
    return False, "sin senal (rango, sin cambios)", "nada"


def build_compacto(t, dirb, niv, extras):
    """Mensaje corto para NY en vivo (cada 5 min): precio, sesgo, niveles, 1 linea."""
    res = niv["resistencias"][0]
    sup = niv["soportes"][0]
    ahora_s = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M UTC")
    d_res = (res["precio"] - t["last"]) / t["last"] * 100 if t["last"] else 0
    d_sup = (t["last"] - sup["precio"]) / t["last"] * 100 if t["last"] else 0
    L = []
    L.append(f"⚡ NY EN VIVO {ahora_s}")
    L.append(f"💰 {fmt_miles(t['last'])} ({t['chg']:+.2f}%) | 🧭 {dirb['bias']} {dirb['confianza']}%")
    L.append(f"🎯 R {fmt_miles(res['precio'])} (a {d_res:.1f}%) | S {fmt_miles(sup['precio'])} (a {d_sup:.1f}%)")
    if extras.get("mov_ny") is not None:
        L.append(f"🕯 NY: {extras['mov_ny']:+.2f}% desde la apertura")
    L.append("📖 " + extras.get("narrativa", ""))
    for m in extras.get("memoria", [])[:2]:
        L.append("🧠 " + m)
    for n in extras.get("nuevas", [])[:2]:
        L.append(f"🆕 [{n['score']}] {n['titulo']}")
    if extras.get("fflag"):
        L.append("⚠️ Funding extremo: " + extras["fflag"])
    return "\n".join(L)


def build_parte(t, h1, h4, d1, w1, niv, dirb, prox, senti, fg, est, motivo, tipo, notis, evs, ahora, extras):
    res = niv["resistencias"][0]
    sup = niv["soportes"][0]
    horas_res = round((res["precio"] - t["last"]) / h1["atr"], 1) if h1["atr"] > 0 else None
    horas_sup = round((t["last"] - sup["precio"]) / h1["atr"], 1) if h1["atr"] > 0 else None
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%d/%m %H:%M UTC")
    icon = {"ALCISTA": "🟢", "BAJISTA": "🔴", "lateral": "🟡"}

    icono_tipo = {"alerta": "🚨", "preny": "📊", "manana": "☀️", "madrugada": "🌙", "noche": "🌙", "ny": "⚡"}.get(tipo, "🤖")
    L = []
    L.append(icono_tipo + " " + motivo)
    L.append("💬 " + extras.get("intro", ""))
    L.append("🤖 VIGILANTE BTC v3")
    L.append(f"📅 {now}  |  {sesion_hora()}")
    L.append(f"📡 Datos: {FUENTE['nombre']} (Binance)")
    L.append("=================================")
    L.append(f"💰 PRECIO: {fmt_miles(t['last'])}  ({t['chg']:+.2f}% 24h)")
    L.append(f"📈 max {fmt_miles(t['hi'])} / min {fmt_miles(t['lo'])}")
    L.append("")
    L.append(f"🧭 DIRECCION: {dirb['bias']} (confianza {dirb['confianza']}%)")
    for x in (h1, h4, d1, w1):
        L.append(f"  {icon.get(x['tend'], '🟡')} {x['tf']}: {x['tend'].upper()} (s{x['score']:+d}) "
                 f"RSI {x['rsi']} | MACD {'+' if x['macd'] > 0 else '-'}")
    L.append("")
    L.append("📖 " + extras.get("narrativa", ""))
    L.append("")
    s_txt = "  |  ".join(f"{fmt_miles(x['precio'])} ({x['origen']})" for x in niv["soportes"])
    r_txt = "  |  ".join(f"{fmt_miles(x['precio'])} ({x['origen']})" for x in niv["resistencias"])
    L.append(f"🟢 SOPORTES: {s_txt}")
    L.append(f"🔴 RESISTENCIAS: {r_txt}")
    for m in extras.get("memoria", []):
        L.append("🧠 " + m)
    L.append("")
    L.append("📈 24h: " + extras.get("spark", ""))
    L.append("⛽ Combustible del día: " + extras.get("comb", "n/d"))
    if extras.get("fflag"):
        L.append("⚠️ Funding extremo: " + extras["fflag"])
    L.append("")
    L.append("🎯 PLAN (qué esperar para entrar):")
    for p in extras.get("plan", []):
        L.append("   • " + p)
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
    fg_icon = "😱" if fg["valor"] < 25 else ("😨" if fg["valor"] < 45 else ("😐" if fg["valor"] < 55 else ("🙂" if fg["valor"] < 75 else "🤑")))
    L.append(f"{fg_icon} MIEDO/CODICIA: {fg['etiqueta']} {fg['valor']}/100")
    sent = []
    if senti["funding"] is not None:
        sent.append(f"funding {senti['funding']:+.4f}%")
    if senti["oi"] is not None:
        sent.append(f"OI {fmt_miles(senti['oi'] * t['last'])}$")
    if senti["taker"] is not None:
        sent.append(f"taker L/S {senti['taker']}")
    if sent:
        L.append("⚡ FUTUROS: " + " | ".join(sent))
    L.append(f"🎯 PRECISION: ALZA {prec_str(est.get('alza', []))} · BAJA {prec_str(est.get('baja', []))}")
    L.append("")
    L.append("📰 NOTICIAS TOP (peso real sobre BTC):")
    if notis:
        for n in notis:
            icono = '🔴' if n['score'] >= 9 else '🟡'
            L.append(f"  {icono} [{n['score']}] {n['titulo']}")
            L.append(f"     → {explicar_noticia(n['tags'])} · impacto {impacto_noticia(n['score'])}")
    else:
        L.append("  (sin noticias relevantes ahora)")
    L.append("")
    L.append("🗓 PROXIMOS EVENTOS EE.UU.:")
    if evs:
        for e in evs:
            cuando_s = e['cuando'].strftime('%a %d %H:%M UTC')
            L.append(f"  📌 {e['titulo']} ({cuando_s}, {cuenta_regresiva(e['cuando'], ahora)})")
            L.append(f"     → {explicar_evento(e['titulo'])} · impacto {impacto_evento(e['impact'])}")
    else:
        L.append("  (sin eventos fuertes esta semana)")
    L.append("  Rangos ±% = referencia historica tipica, no prediccion.")
    L.append("")
    L.append("💡 " + extras.get("leccion", ""))
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
    ahora = datetime.datetime.now(datetime.timezone.utc)
    try:
        t = ticker24()
        kl_h1 = klines("1h", 72)
        h1 = analyze(kl_h1, 60, "1H")
        h4 = analyze(klines("4h", 60), 240, "4H")
        d1 = analyze(klines("1d", 60), 1440, "1D")
        w1 = analyze(klines("1w", 52), 10080, "1S")
        pd = pivots("1d", "D")
        pw = pivots("1w", "S")
        niv = niveles(h1, h4, d1, w1, pd, pw, t["last"])
        dirb = direccion(h1, h4, d1, w1)
        prox = proxima_sesion()
        senti = sentiment()
        fg = fear_greed(d1, senti, t["chg"])
        notis = noticias()
        evs = calendario()

        est, hist = cargar_estado()
        umbral = max(UMBRAL_MOV, (h1["atr"] / t["last"]) * UMBRAL_ATR_MULT) if t["last"] else UMBRAL_MOV
        evaluar(est, t["last"], ahora, umbral)
        hist.append({"t": ahora.isoformat(), "precio": round(t["last"]),
                     "bias": dirb["bias"], "conf": dirb["confianza"], "fg": fg["valor"],
                     "fund": senti["funding"], "taker": senti["taker"]})

        enviar, motivo, tipo = decidir_alerta(t["last"], niv, dirb, est, ahora)
        hoy = ahora.strftime("%Y-%m-%d")
        fresco = est.get("runs", 0) == 0
        est["runs"] = est.get("runs", 0) + 1
        res = niv["resistencias"][0]
        sup = niv["soportes"][0]

        est["ultimo_bias"] = dirb["bias"]
        est["ultima_conf"] = dirb["confianza"]
        est["ultimo_precio"] = round(t["last"])
        est["ultimo_run"] = ahora.isoformat()
        if tipo == "manana":
            est["ultimo_resumen"] = f"{hoy}-manana"
        elif tipo == "noche":
            est["ultimo_resumen_noche"] = hoy
        elif tipo == "preny":
            est["ultimo_preny"] = hoy
        elif tipo == "madrugada":
            est["ultimo_madrugada"] = hoy
        if enviar and tipo == "alerta" and dirb["bias"] in ("ALZA", "BAJA") and dirb["confianza"] >= UMBRAL_CONF_SENAL:
            reciente = False
            for p in est.get("pendientes", []):
                try:
                    if p.get("bias") == dirb["bias"] and (ahora - datetime.datetime.fromisoformat(p["t"])).total_seconds() / 3600 < DEDUP_HORAS:
                        reciente = True
                        break
                except Exception:
                    continue
            if not reciente:
                est["pendientes"] = est.get("pendientes", []) + [
                    {"t": ahora.isoformat(), "precio": round(t["last"]),
                     "bias": dirb["bias"], "conf": dirb["confianza"]}]
        guardar_estado(est, hist)

        ctx = {"t": t, "dirb": dirb, "niv": niv, "fg": fg, "est": est,
               "h1": h1, "h4": h4, "d1": d1, "w1": w1, "senti": senti,
               "notis": notis, "evs": evs}
        try:
            cmds, new_off = leer_comandos(est.get("offset", 0))
        except Exception:
            cmds, new_off = [], est.get("offset", 0)
        if new_off != est.get("offset", 0):
            est["offset"] = new_off
            guardar_estado(est, hist)
        if not fresco:
            for cm in cmds:
                r = responder_comando(cm, ctx)
                if r:
                    send_telegram("💬 " + cm["texto"] + "\n" + r)

        if not enviar:
            print(f"Sin alerta ({motivo}). Estado e historial guardados.")
            return
        runs = est["runs"]
        if tipo == "alerta":
            intro = ABRIDORES[runs % len(ABRIDORES)] + " 👀"
        elif tipo == "manana":
            intro = "¡Buenos días! Arranca Londres: este es el plan del día."
        elif tipo == "preny":
            intro = "Faltan 30 min para NY: reporte detallado pre-apertura."
        elif tipo == "madrugada":
            intro = "Mientras dormías: así le fue a la noche."
        elif tipo == "ny":
            intro = "NY en vivo."
        else:
            intro = "Cerramos el día: esto fue lo importante."
        memoria = []
        if tipo == "alerta" and motivo.startswith("Tocando"):
            nivel = res["precio"] if "resistencia" in motivo else sup["precio"]
            n = toques_hoy(hist, nivel, ahora)
            if n >= 2:
                memoria.append(f"ya tocó ese nivel {n} veces hoy: cada toque lo debilita")
        va = vs_ayer(hist, t["last"], ahora)
        if va is not None:
            memoria.append(f"vs ayer a esta hora: {va:+.2f}%")
        lf = None
        for h in reversed(hist[:-1]):
            if h.get("fund") is not None:
                lf = h["fund"]
                break
        if lf is not None and senti["funding"] is not None:
            dd = senti["funding"] - lf
            if abs(dd) >= 0.002:
                direc = "se calentó" if dd > 0 else "se enfrió"
                memoria.append(f"el funding {direc} desde tu último parte ({lf:+.4f}% → {senti['funding']:+.4f}%)")
        nuevas = [n for n in notis if n["titulo"] not in est.get("vistas", [])][:2]
        if nuevas:
            est["vistas"] = (est.get("vistas", []) + [n["titulo"] for n in nuevas])[-30:]
        mov_ny = None
        corte = hoy + "T13:30"
        for h in hist:
            if h.get("t", "")[:16] >= corte and h.get("precio"):
                mov_ny = round((t["last"] - h["precio"]) / h["precio"] * 100, 2)
                break
        if tipo == "manana":
            ca = cierre_ayer(hist, ahora)
            if ca:
                memoria.append(f"ayer cerró en {fmt_miles(ca)}")
            if evs:
                memoria.append("hoy vigilo: " + ", ".join(e["titulo"] for e in evs[:2]))
        if tipo == "madrugada":
            ay = (ahora - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            sd = stats_fecha(hist, ay)
            if sd:
                memoria.append(f"anoche: máx {fmt_miles(sd['max'])}, mín {fmt_miles(sd['min'])}, sesgo {sd['dom']}")
        if tipo == "noche":
            sd = stats_dia(hist, ahora)
            if sd:
                memoria.append(f"hoy: máx {fmt_miles(sd['max'])}, mín {fmt_miles(sd['min'])}, sesgo dominante {sd['dom']}")
            if evs:
                memoria.append("mañana vigilo: " + ", ".join(e["titulo"] for e in evs[:2]))
        extras = {"intro": intro,
                  "narrativa": narrar(dirb, h1, h4, d1, res, sup, t["last"]),
                  "memoria": memoria,
                  "leccion": LECCIONES[runs % len(LECCIONES)],
                  "plan": plan_entrada(dirb, niv, evs, ahora),
                  "spark": sparkline([c["c"] for c in kl_h1[-24:]]),
                  "comb": combustible(t, d1),
                  "fflag": funding_flag(senti),
                  "nuevas": nuevas,
                  "mov_ny": mov_ny}
        if tipo == "ny":
            msg = build_compacto(t, dirb, niv, extras)
        else:
            msg = build_parte(t, h1, h4, d1, w1, niv, dirb, prox, senti, fg, est, motivo, tipo, notis, evs, ahora, extras)
        ok = send_telegram(msg)
        print("Enviado OK" if ok else "NO enviado (modo local)")
    except Exception as e:  # noqa: BLE001
        err = f"⚠️ El Vigilante fallo: {e} (si es Telegram 400: revisa Chat ID, pulsa Start en tu bot y verifica el token)"
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
