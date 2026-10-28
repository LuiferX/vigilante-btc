#!/usr/bin/env python3
"""
indicadores.py - MATEMATICA PURA del Vigilante (Fase 1 de modularizacion).

Extraido 1:1 de vigilante_cloud.py (mismo codigo, mismo comportamiento). Solo
depende de stdlib.vigilante_cloud.py sigue re-exportando estos nombres, asi que
los tests, comandos.py y dashboard.py no cambian.

Si tocas algo aqui, corre: python test_vigilante.py
"""

import datetime
import re


def es_alerta_direccional(motivo):
    """True solo para textos que invitan a tomar direccion o traen un plan."""
    m = str(motivo or "").lower()
    if "no es entrada" in m or "no una entrada" in m or "sin plan" in m or "solo aviso" in m:
        return False
    marcas = (
        "señal fuerte",
        "cambio de dirección",
        "compra ",
        "venta ",
        "rechazo ",
        "tocando ",
        "toma de liquidez",
        "r:r",
        "stop ",
        "sl ",
    )
    return any(x in m for x in marcas)


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
        # B1: sin bajadas, pero si tampoco hay subidas el RSI es 50 (no 100)
        return 100.0 if g > 0 else 50.0
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
        trs.append(
            max(
                candles[i]["h"] - candles[i]["l"],
                abs(candles[i]["h"] - pc),
                abs(candles[i]["l"] - pc),
            )
        )
    return sum(trs[-14:]) / min(14, len(trs))


def adx(candles, n=14):
    """ADX de Wilder: >25 tendencia institucional, <20 rango/chop."""
    m = len(candles)
    if m < n + 5:
        return 0.0
    trs, pdm, mdm = [], [], []
    for i in range(1, m):
        h, l, pc = candles[i]["h"], candles[i]["l"], candles[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        up = h - candles[i - 1]["h"]
        dn = candles[i - 1]["l"] - l
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
    return round(sum(tail) / len(tail), 1)


def atr_regime(candles):
    hists = []
    for i in range(14, len(candles), 5):
        hists.append(atr(candles[i - 14 : i]))
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


def swings_idx(candles, k=2):
    """Swings con índice: [(i, máximo), ...], [(i, mínimo), ...]. Puro."""
    try:
        hs, ls = [], []
        n = len(candles or [])
        for i in range(k, n - k):
            try:
                if all(
                    candles[i]["h"] >= candles[j]["h"] for j in range(i - k, i + k + 1) if j != i
                ):
                    hs.append((i, candles[i]["h"]))
                if all(
                    candles[i]["l"] <= candles[j]["l"] for j in range(i - k, i + k + 1) if j != i
                ):
                    ls.append((i, candles[i]["l"]))
            except Exception:
                continue
        return hs, ls
    except Exception:
        return [], []


def find_swing_points(h, l, n=3):
    """Swing points estrictos (n velas a cada lado), estilo FractalTrader."""
    try:
        hs: list[tuple[int, float]] = []
        ls: list[tuple[int, float]] = []
        nn = len(h)
        if nn < 2 * n + 1:
            return hs, ls
        for i in range(n, nn - n):
            left_h = [h[j] for j in range(i - n, i)]
            right_h = [h[j] for j in range(i + 1, i + n + 1)]
            if h[i] > max(left_h + right_h):
                hs.append((i, float(h[i])))
            left_l = [l[j] for j in range(i - n, i)]
            right_l = [l[j] for j in range(i + 1, i + n + 1)]
            if l[i] < min(left_l + right_l):
                ls.append((i, float(l[i])))
        return hs, ls
    except Exception:
        return [], []


def find_equal_levels(swings, tolerance=0.001):
    """Agrupa swings iguales (dentro de tolerance) → liquidez más fuerte."""
    if not swings:
        return []
    try:
        ordenados = sorted(swings, key=lambda x: x[1])
        # cada cluster: [lista de (idx, precio), precio medio]
        clusters: list[list] = []
        for idx, price in ordenados:
            if clusters and abs(price - clusters[-1][1]) / clusters[-1][1] <= tolerance:
                clusters[-1][0].append((idx, price))
                clusters[-1][1] = sum(p for _, p in clusters[-1][0]) / len(clusters[-1][0])
            else:
                clusters.append([[(idx, price)], price])
        return [(c[0][-1][0], round(c[1], 2), len(c[0])) for c in clusters]
    except Exception:
        return []


def quiebre_estructura(candles):
    """BOS/CHoCH fresco: cruce del último swing en las últimas 2 cerradas.
    Devuelve {"dir","nivel","tipo"} o None. Puro, sin red."""
    try:
        n = len(candles or [])
        if n < 10:
            return None
        hs, ls = swings_idx(candles)
        if len(hs) < 2 or len(ls) < 2:
            return None
        c0, c1 = candles[-1]["c"], candles[-2]["c"]
        (ih, ph), (il, pl) = hs[-1], ls[-1]
        rompe_up = ih >= n - 8 and c1 <= ph and c0 > ph
        rompe_dn = il >= n - 8 and c1 >= pl and c0 < pl
        if not rompe_up and not rompe_dn:
            return None
        bajista = hs[-1][1] < hs[-2][1] and ls[-1][1] < ls[-2][1]
        alcista = hs[-1][1] > hs[-2][1] and ls[-1][1] > ls[-2][1]
        if rompe_up:
            tipo = "CHoCH" if bajista else "BOS"
            return {"dir": "ALZA", "nivel": ph, "tipo": tipo, "swing": pl}
        if alcista:
            tipo = "CHoCH"
        else:
            tipo = "BOS"
        return {"dir": "BAJA", "nivel": pl, "tipo": tipo, "swing": ph}
    except Exception:
        return None


def sl_estructura(entry, dire, ref, atr_val):
    """SL tras el swing contrario + 0.2*ATR. Devuelve (sl, dist_pct, lejos). Puro."""
    try:
        entry = float(entry)
        ref = float(ref)
        buf = float(atr_val or 0) * 0.2
        if dire == "ALZA":
            sl = ref - buf
        elif dire == "BAJA":
            sl = ref + buf
        else:
            return None
        if dire == "ALZA" and sl >= entry:
            return None
        if dire == "BAJA" and sl <= entry:
            return None
        dist = abs(entry - sl) / entry * 100 if entry > 0 else 99
        return (round(sl), round(dist, 2), dist > 1.5)
    except Exception:
        return None


def mecha_rechazo(candles):
    """Rechazo por mecha en BTC 1H. Puro, sin red.
    ALZA = martillo (mecha inferior domina, nivel=low).
    BAJA = estrella fugaz (mecha superior domina, nivel=high).
    Recencia: solo las ultimas 2 cerradas (la fresca manda).
    Si pasas la vela en formacion, llama con candles[:-1].
    Devuelve None o {"dir","nivel","mid","ref","ratio","fuerza"}."""
    try:
        n = len(candles or [])
        if n < 1:
            return None
        RANGO_MIN = 400
        MECHA_MIN_USDT = 250
        MECHA_MIN_PCT = 0.30
        RATIO_MIN = 0.50
        CUERPO_MAX = 0.35
        OPUESTA_MAX = 0.25
        for idx in ([n - 1, n - 2] if n >= 2 else [n - 1]):
            c = candles[idx]
            o, h, l, cl = float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"])
            rango = h - l
            if rango < RANGO_MIN or rango <= 0 or cl <= 0:
                continue
            cuerpo = abs(o - cl)
            mi = min(o, cl) - l
            ms = h - max(o, cl)
            if mi < 0 or ms < 0:
                continue
            ri, rs, rc = mi / rango, ms / rango, cuerpo / rango
            if rc > CUERPO_MAX:
                continue
            if ri >= RATIO_MIN and ri > rs and rs <= OPUESTA_MAX:
                if mi < MECHA_MIN_USDT or mi / cl * 100 < MECHA_MIN_PCT:
                    continue
                fuerte = ri >= 0.65 and rc <= 0.20
                return {
                    "dir": "ALZA",
                    "nivel": round(l),
                    "mid": round((l + cl) / 2),
                    "ref": round(cl),
                    "ratio": round(ri, 3),
                    "fuerza": "fuerte" if fuerte else "media",
                }
            if rs >= RATIO_MIN and rs > ri and ri <= OPUESTA_MAX:
                if ms < MECHA_MIN_USDT or ms / cl * 100 < MECHA_MIN_PCT:
                    continue
                fuerte = rs >= 0.65 and rc <= 0.20
                return {
                    "dir": "BAJA",
                    "nivel": round(h),
                    "mid": round((h + cl) / 2),
                    "ref": round(cl),
                    "ratio": round(rs, 3),
                    "fuerza": "fuerte" if fuerte else "media",
                }
        return None
    except Exception:
        return None


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


def clamp(x, a, b):
    return max(a, min(b, x))


def eficiencia(closes, n=30):
    """Efficiency Ratio de Kaufman (sin dependencias): |cambio neto| / camino.
    >0.5 el precio va a alguna parte (tendencia), <0.25 puro ruido (chop).
    None si no hay datos suficientes."""
    try:
        xs = list(closes[-n - 1 :])
        if len(xs) < n + 1:
            return None
        den = sum(abs(xs[i + 1] - xs[i]) for i in range(len(xs) - 1))
        if den <= 0:
            return 1.0
        return round(abs(xs[-1] - xs[0]) / den, 3)
    except Exception:
        return None


def zscore(closes, n=20):
    """Distancia a la media de n en sigmas: |z|>=2 = estirado (no perseguir).
    None si no hay datos suficientes."""
    try:
        import math

        xs = list(closes[-n:])
        if len(xs) < n:
            return None
        m = sum(xs) / len(xs)
        var = sum((x - m) ** 2 for x in xs) / len(xs)
        if var <= 0:
            return 0.0
        return round((xs[-1] - m) / math.sqrt(var), 2)
    except Exception:
        return None


def fmt_miles(x):
    return f"{x:,.0f}".replace(",", ".")


def sesion_hora():
    """Sesión actual en UTC, alineada con `sesion_bucket` (Asia/Londres/NY/noche).
    Antes decía "fuera de sesion" durante Asia (00–08 UTC) y llamaba "solape" a
    toda la tarde. Ahora: Asia 00–08, Londres 08–13:30, solape 13:30–16:30,
    NY 16:30–21, noche 21–24."""
    now = datetime.datetime.now(datetime.UTC)
    hh = now.hour + now.minute / 60
    if hh < 8:
        return "Asia"
    if hh < 13.5:
        return "Londres"
    if hh < 16.5:
        return "Londres+NY (solape)"
    if hh < 21:
        return "NY"
    return "noche"


def sesion_bucket(hora):
    if 0 <= hora < 8:
        return "Asia"
    if 8 <= hora < 13:
        return "Londres"
    if 13 <= hora < 21:
        return "NY"
    return "noche"


def tipo_de_motivo(motivo):
    """Clasifica el texto de una alerta en su tipo medible.
    Sirve para el scoreboard: saber QUE tipo acierta, no solo el total."""
    m = str(motivo or "")
    if m.startswith("🧱"):
        return "toques"
    if m.startswith("Toma de liquidez"):
        return "liquidez"
    if m.startswith("ruptura"):
        return "ruptura"
    if m.startswith("Tocando"):
        return "toque"
    if m.startswith("EYY PILAS") or m.startswith("Zona de referencia"):
        return "pila"
    if m.startswith("COMPRA") or m.startswith("VENTA"):
        return "estructura"
    if m.startswith("RECHAZO"):
        return "mecha"
    if "Movimiento brusco" in m:
        return "brusco"
    if "Ritmo acelerado" in m:
        return "ritmo"
    if m.startswith("Señal fuerte"):
        return "fuerte"
    if m.startswith("Cambio de dirección"):
        return "cambio"
    if m.startswith("Estirado"):
        return "estirado"
    if m.startswith("La sesión NY"):
        return "ny"
    return "otro"


def direccion_alerta(motivo, bias=None):
    """Devuelve la direccion REAL que propone la alerta, no el sesgo del bot.

    El scoreboard viejo media `bias`, y por eso una alerta de VENTA podia
    contarse como ALZA solo porque el sesgo general era alcista. Aqui manda
    el plan escrito en el mensaje (ALZA/BAJA: stop...) y, si no hay plan,
    solo los textos que invitan a una direccion concreta.
    """
    m = str(motivo or "")
    # El plan compacto siempre trae "ALZA: stop" o "BAJA: stop".
    mm = re.search(r"\b(ALZA|BAJA)\s*:\s*stop\b", m, re.I)
    if mm:
        return mm.group(1).upper()
    if m.startswith(("COMPRA ", "COMPRA\n")):
        return "ALZA"
    if m.startswith(("VENTA ", "VENTA\n")):
        return "BAJA"
    if m.startswith("RECHAZO ALZA"):
        return "ALZA"
    if m.startswith("RECHAZO BAJA"):
        return "BAJA"
    if m.startswith("ruptura ALCISTA"):
        return "ALZA"
    if m.startswith("ruptura BAJISTA"):
        return "BAJA"
    if m.startswith("Señal fuerte ALZA"):
        return "ALZA"
    if m.startswith("Señal fuerte BAJA"):
        return "BAJA"
    if m.startswith("Cambio de dirección"):
        # "Cambio de dirección: BAJA → ALZA": manda la ultima direccion.
        encontradas = re.findall(r"\b(ALZA|BAJA)\b", m)
        return encontradas[-1] if encontradas else None
    if m.startswith("Tocando"):
        return bias if bias in ("ALZA", "BAJA") else None
    return None


def num_txt(x):
    if x is None:
        return None
    m = re.search(r"-?\d+\.?\d*", str(x).replace(",", ""))
    return float(m.group()) if m else None


def validar_velas(candles, intervalo_min=60):
    """Validador puro: integridad OHLC + continuidad. No toca red ni umbrales."""
    try:
        velas = [c for c in (candles or []) if isinstance(c, dict)]
        malas, gaps = 0, 0
        prev_t = None
        for c in velas:
            try:
                o, h, l, cc = float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"])
                t = c["t"]
            except Exception:
                malas += 1
                continue
            if not (h >= max(o, cc) and l <= min(o, cc) and h >= l):
                malas += 1
            if prev_t is not None and t is not None:
                try:
                    dt = (t - prev_t).total_seconds() / 60
                    if dt > intervalo_min * 1.5:
                        gaps += 1
                except Exception:
                    pass
            prev_t = t
        return {
            "ok": bool(velas) and malas == 0 and gaps == 0,
            "n": len(velas),
            "malas": malas,
            "gaps": gaps,
        }
    except Exception:
        return {"ok": False, "n": 0, "malas": 0, "gaps": 0}


def latido_tarde(ultimo_run_iso, ahora_iso, max_min=15):
    """Watchdog puro: True si el último run supera max_min. Sin efectos."""
    try:
        t0 = datetime.datetime.fromisoformat(ultimo_run_iso)
        t1 = datetime.datetime.fromisoformat(ahora_iso)
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=datetime.UTC)
        if t1.tzinfo is None:
            t1 = t1.replace(tzinfo=datetime.UTC)
        return (t1 - t0).total_seconds() / 60 > max_min
    except Exception:
        return False


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
