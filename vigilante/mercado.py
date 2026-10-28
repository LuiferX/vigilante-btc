#!/usr/bin/env python3
"""
mercado.py - CONTEXTO DE MERCADO del Vigilante (Fase 5 de modularizacion).

Extraido 1:1 de vigilante_cloud.py: macro/dolar/SPX, Coinbase (premium USA),
flujos (ballenas, CVD, long/short global), imanes Deribit, FVGs, liquidez,
zonas PILAS y su mensaje, divergencias, mapa de liquidaciones.
La costura de red vive en vigilante/red.py; la matematica pura en
vigilante/indicadores.py. vigilante_cloud.py re-exporta estos nombres.
"""

import json
import os
import urllib.request

from vigilante.red import fetch, FAPI, FDATA, VISION
from vigilante.indicadores import fmt_miles, sesion_bucket, clamp, rsi
from vigilante.toques import UMBRAL_TOQUE

# Rejilla de identidad de niveles (vivia en vigilante_cloud.py; se muda con
# snap_nivel, que es quien la usa). vigilante_cloud.py la re-exporta.
GRID_NIVELES = 500

UMBRAL_RUPTURA_MIN = float(
    os.environ.get("VIGILANTE_RUPTURA_MIN", "0.30")
)  # margen minimo % mas alla del nivel


UMBRAL_RUPTURA_ESTRICTO = os.environ.get("VIGILANTE_RUPTURA_ESTRICTO", "1") not in (
    "",
    "0",
    "false",
    "False",
)


UMBRAL_BALLENA = 5  # print >= 5 BTC (~$400k) = huella de ballena


def snap_nivel(v):
    """Ancla un nivel a la rejilla para que tenga identidad estable entre pasadas."""
    try:
        return int(round(float(v) / GRID_NIVELES) * GRID_NIVELES)
    except Exception:
        return v


def dominancia(data=None):
    """Dominancia BTC/ETH (CoinGecko global, gratis). Acepta data inyectada (tests)."""
    try:
        if data is None:
            data = fetch("https://api.coingecko.com/api/v3/global", timeout=15, tries=1)
        pct = (data.get("data") or {}).get("market_cap_percentage") or {}
        btc, eth = pct.get("btc"), pct.get("eth")
        if btc is None:
            return None
        return {"btc": round(float(btc), 1), "eth": round(float(eth or 0), 1)}
    except Exception:
        return None


def veredicto_dom(btc, prev=None):
    try:
        b = float(btc)
        base = (
            "temporada BTC 🟠"
            if b >= 55
            else ("zona mixta ⚪" if b >= 48 else "aires de altseason 🟣")
        )
        if prev is None:
            return base
        d = b - float(prev)
        fle = "▲" if d > 0.2 else ("▼" if d < -0.2 else "＝")
        return f"{base} {fle}"
    except Exception:
        return "s/d"


REAC_BASE = 0.522


REAC_TAB = {  # mini-IA contenida: P(reaccion>=0.3%/4h en PILAS). Entrenada replay
    # 8m (2026-02 a 2026-10, n=314); test temporal: top25 72.7% / mid 54.4% / bot 51.5%.
    # SOLO lectura (etiqueta en el mensaje). No decide, no opera, no toca red.
    "rsi=0": 0.456,
    "rsi=1": 0.523,
    "rsi=2": 0.586,
    "adx=0": 0.418,
    "adx=1": 0.573,
    "er=0": 0.562,
    "er=1": 0.5,
    "er=2": 0.501,
    "ses=Asia": 0.473,
    "ses=Londres": 0.617,
    "ses=NY": 0.533,
    "h1t=ALCISTA": 0.558,
    "h1t=BAJISTA": 0.437,
    "h1t=lateral": 0.56,
    "zt=0": 0.471,
    "zt=1": 0.583,
    "zt=2": 0.538,
}


def prob_reaccion(feats):
    """Puntaje 0..1 de reaccion probable (media de tablas). None si falla."""
    try:
        vals = [
            REAC_TAB.get(k + "=" + str((feats or {}).get(k)), REAC_BASE)
            for k in ("rsi", "adx", "er", "ses", "h1t", "zt")
        ]
        return round(sum(vals) / len(vals), 3)
    except Exception:
        return None


def punto_control(kl, n=168):
    """POC + área de valor (microestructura sin dependencias):
    nivel con más volumen negociado en las últimas n velas 1H y rango
    que concentra el 70% del volumen. None si no hay datos."""
    try:
        velas = [c for c in (kl or [])[-n:] if c.get("v", 0) > 0 and c.get("h") and c.get("l")]
        if len(velas) < 24:
            return None
        lo = min(c["l"] for c in velas)
        hi = max(c["h"] for c in velas)
        if hi <= lo:
            return None
        nb = 20
        paso = (hi - lo) / nb
        cubos = [0.0] * nb
        for c in velas:
            i = min(nb - 1, int((c["c"] - lo) / paso)) if paso > 0 else 0
            cubos[i] += float(c["v"])
        tot = sum(cubos)
        if tot <= 0:
            return None
        ipoc = max(range(nb), key=lambda i: cubos[i])
        poc = round(lo + (ipoc + 0.5) * paso)
        orden = sorted(range(nb), key=lambda i: -cubos[i])
        acum, eleg = 0.0, []
        for i in orden:
            acum += cubos[i]
            eleg.append(i)
            if acum >= 0.7 * tot:
                break
        vah = round(lo + (max(eleg) + 1) * paso)
        val = round(lo + min(eleg) * paso)
        return {"poc": poc, "vah": vah, "val": val}
    except Exception:
        return None


def _atr_serie(kl, n=14):
    """ATR simple por vela (sin pandas). None en las primeras n."""
    atr = [None] * len(kl)
    # None = vela sin ATR todavia (las primeras n); ver el `all(...)` de abajo.
    trs: list[float | None] = []
    for i in range(1, len(kl)):
        try:
            h, l, pc = float(kl[i]["h"]), float(kl[i]["l"]), float(kl[i - 1]["c"])
        except Exception:
            trs.append(None)
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if i >= n and all(x is not None for x in trs[i - n : i]):
            # el all() de arriba ya garantiza que no hay None en la ventana
            atr[i] = sum(x for x in trs[i - n : i] if x is not None) / n
    return atr


def fvg_velas(kl, min_atr=0.25, max_bars=400):
    """Fair Value Gaps SIN LLENAR (ICT) sobre velas cerradas.

    Medido en BTC (5.000 velas 1H + 2.000 4H, in/out-of-sample): como señal
    de entrada NO funciona (esperanza out-of-sample negativa, incluso con
    barrido+recuperacion). Como IMAN si: 81-86 % de los huecos se vuelven a
    tocar y ~69 % se llenan del todo en 1H. Uso: zona de referencia/objetivo,
    nunca gatillo de compra/venta.
    """
    n = len(kl) if kl else 0
    if n < 5:
        return []
    atr = _atr_serie(kl, 14)
    desde = max(2, n - max_bars)
    zonas = []
    for i in range(desde, n):
        a = atr[i]
        if not a or a <= 0:
            continue
        try:
            c0, c2 = kl[i - 2], kl[i]
            h0, l2 = float(c0["h"]), float(c2["l"])
            l0, h2 = float(c0["l"]), float(c2["h"])
        except Exception:
            continue
        if l2 > h0:  # FVG alcista: hueco entre el alto de i-2 y el bajo de i
            lo, hi = h0, l2
            if hi - lo >= min_atr * a:
                zonas.append({"dir": "ALZA", "lo": lo, "hi": hi, "i": i, "size": hi - lo, "atr": a})
        elif h2 < l0:  # FVG bajista
            lo, hi = h2, l0
            if hi - lo >= min_atr * a:
                zonas.append({"dir": "BAJA", "lo": lo, "hi": hi, "i": i, "size": hi - lo, "atr": a})
    activas = []
    for z in zonas:
        lleno = False
        for k in range(z["i"] + 1, n):
            try:
                if z["dir"] == "ALZA" and float(kl[k]["l"]) <= z["lo"]:
                    lleno = True
                    break
                if z["dir"] == "BAJA" and float(kl[k]["h"]) >= z["hi"]:
                    lleno = True
                    break
            except Exception:
                continue
        if lleno:
            continue
        z["edad"] = n - 1 - z["i"]
        z["size_atr"] = round(z["size"] / z["atr"], 2) if z["atr"] else None
        activas.append(z)
    return activas


def fvgs_cercanos(kl, precio, min_atr=0.25, max_bars=400, max_zonas=3):
    """FVG sin llenar mas cercanos al precio, deduplicados. Solo contexto."""
    try:
        precio = float(precio)
    except Exception:
        return []
    if precio <= 0:
        return []
    zonas = fvg_velas(kl, min_atr=min_atr, max_bars=max_bars)
    for z in zonas:
        if z["lo"] <= precio <= z["hi"]:
            z["dist_pct"] = 0.0
            z["dentro"] = True
        elif precio < z["lo"]:
            z["dist_pct"] = round((z["lo"] - precio) / precio * 100, 2)
            z["dentro"] = False
        else:
            z["dist_pct"] = -round((precio - z["hi"]) / precio * 100, 2)
            z["dentro"] = False
    zonas.sort(key=lambda z: abs(z["dist_pct"]))
    out: list[dict] = []
    for z in zonas:
        if len(out) >= max_zonas:
            break
        solapa = False
        for q in out:
            if q["dir"] != z["dir"]:
                continue
            inter = max(0.0, min(q["hi"], z["hi"]) - max(q["lo"], z["lo"]))
            union = max(q["hi"], z["hi"]) - min(q["lo"], z["lo"])
            if union > 0 and inter / union > 0.6:
                solapa = True
                break
        if not solapa:
            out.append(z)
    return out


def fvgs_activos(kl_h1, kl_h4, precio):
    """Estructura compacta para snapshot/parte: {'h1': [...], 'h4': [...]}."""
    return {"h1": fvgs_cercanos(kl_h1, precio), "h4": fvgs_cercanos(kl_h4, precio)}


def texto_fvg(fvg, precio, max_partes=2, max_dist=1.2):
    """Linea corta con FVG sin llenar relevantes (iman). NO es una alerta."""
    try:
        dentro, cerca = [], []
        etiqueta = {"h1": "1H", "h4": "4H"}
        for tf in ("h1", "h4"):
            for z in (fvg or {}).get(tf, []):
                d = z.get("dist_pct")
                if d is None:
                    continue
                _etq = etiqueta.get(tf, tf)
                if z.get("dentro"):
                    dentro.append(f"FVG {_etq} dentro de {fmt_miles(z['lo'])}-{fmt_miles(z['hi'])}")
                elif abs(d) <= max_dist:
                    cerca.append(
                        f"FVG {_etq} {fmt_miles(z['lo'])}-{fmt_miles(z['hi'])} ({d:+.1f}%)"
                    )
        partes = dentro + cerca
        if not partes:
            return ""
        return "🧲 " + " · ".join(partes[:max_partes])
    except Exception:
        return ""


def yahoo_cierres(sym):
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
    req = urllib.request.Request(
        u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.load(r)["chart"]["result"][0]
        q = [v for v in d["indicators"]["quote"][0]["close"] if v]
    except Exception:
        return None
    if len(q) < 2 or not q[-2]:
        return None
    return {"px": round(q[-1], 2), "chg": round((q[-1] - q[-2]) / q[-2] * 100, 2)}


def macro_ext():
    """Dolar (DXY) y bolsa (SPX) gratis via Yahoo. Devuelve dict o None."""
    try:
        out = {}
        dxy = yahoo_cierres("DX-Y.NYB")
        spx = yahoo_cierres("%5EGSPC")
        if dxy:
            out["dxy"] = dxy
        if spx:
            out["spx"] = spx
        return out or None
    except Exception:
        return None


def lectura_macro(mx):
    if not mx or "dxy" not in mx or "spx" not in mx:
        return "macro n/d"
    d, s = mx["dxy"]["chg"], mx["spx"]["chg"]
    if d <= -0.2 and s >= 0:
        return "macro a favor de BTC (dólar débil + bolsa fuerte)"
    if d >= 0.2 and s <= 0:
        return "macro en contra de BTC (dólar fuerte + bolsa débil)"
    return "macro mixto"


def coinbase_premium(last):
    """Premium de Coinbase vs Binance: USA pagando mas = demanda institucional."""
    try:
        req = urllib.request.Request(
            "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
            headers={"User-Agent": "vigilante-cloud/3.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            cb = float(json.load(r)["price"])
        return round((cb - last) / last * 100, 3) if last else None
    except Exception:
        return None


def coinbase_analisis(last, vol_bin):
    """Coinbase (puerta institucional USA): premium vs Binance, peso de su
    volumen y desbalance del libro (muros). Todo gratis, sin llaves."""
    out: dict[str, float | None] = {"prem": None, "vol_share": None, "imb": None}
    try:
        tk = json.load(
            urllib.request.urlopen(
                urllib.request.Request(
                    "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
                    headers={"User-Agent": "vigilante-cloud/3.0"},
                ),
                timeout=10,
            )
        )
        cb = float(tk["price"])
        out["prem"] = round((cb - last) / last * 100, 3) if last else None
        cv = float(tk.get("volume", 0) or 0)
        if vol_bin and vol_bin > 0:
            out["vol_share"] = round(cv / vol_bin * 100, 1)
        bk = json.load(
            urllib.request.urlopen(
                urllib.request.Request(
                    "https://api.exchange.coinbase.com/products/BTC-USD/book?level=2",
                    headers={"User-Agent": "vigilante-cloud/3.0"},
                ),
                timeout=10,
            )
        )
        nb = sum(float(p) * float(s) for p, s, _ in bk.get("bids", [])[:30])
        na = sum(float(p) * float(s) for p, s, _ in bk.get("asks", [])[:30])
        if nb + na > 0:
            out["imb"] = round((nb - na) / (nb + na) * 100, 1)
    except Exception:
        pass
    return out


def cb_veredicto(cb):
    p = cb.get("prem") or 0
    ib = cb.get("imb") or 0
    if p > 0.03 and ib > 5:
        return "USA comprando + muro comprador: demanda real"
    if p < -0.03 and ib < -5:
        return "USA vendiendo + muro vendedor: presión real"
    if p > 0.03:
        return "USA paga de más: interés comprador"
    if p < -0.03:
        return "USA con descuento: interés vendedor"
    return "Coinbase neutro vs Binance"


def smart_money(t, h1, senti, notis, prem=None):
    """Instituciones vs minoristas con proxies gratuitos (premium, ETFs, funding, taker)."""
    if prem is None:
        prem = coinbase_premium(t["last"])
    etf = None
    for n in notis:
        tl = n["titulo"].lower()
        if "etf" in tl and any(k in tl for k in ("inflow", "buy", "bought", "record", "demand")):
            etf = "entradas"
            break
        if "etf" in tl and any(k in tl for k in ("outflow", "sell", "sold", "exit")):
            etf = "salidas"
            break
    inst, ret, det = 50, 50, []
    if prem is not None:
        if prem > 0.03:
            inst += 20
            det.append(f"Coinbase premium +{prem}%: USA comprando spot")
        elif prem < -0.03:
            inst -= 20
            det.append(f"Coinbase descuento {prem}%: USA vendiendo")
    if etf == "entradas":
        inst += 15
        det.append("ETFs con entradas: instituciones comprando")
    elif etf == "salidas":
        inst -= 15
        det.append("ETFs con salidas: instituciones vendiendo")
    f = senti["funding"]
    if f is not None:
        if f >= 0.03:
            ret += 20
            det.append(f"funding alto ({f:+.4f}%): retail eufórico en longs")
        elif f <= -0.01:
            ret -= 10
            det.append("funding negativo: retail con miedo o en shorts")
    tk = senti["taker"]
    if tk is not None:
        if tk >= 1.2:
            ret += 10
            det.append("takers comprando agresivo (FOMO)")
        elif tk <= 0.9:
            ret -= 10
            det.append("takers vendiendo agresivo (pánico)")
    if h1["rsi"] >= 75:
        ret += 10
    elif h1["rsi"] <= 25:
        ret -= 10
    inst = clamp(inst, 0, 100)
    ret = clamp(ret, 0, 100)
    if inst >= 60 and ret >= 60:
        ver = "todos compran: sube pero cuidado con el techo"
    elif inst >= 60 and ret < 40:
        ver = "instituciones acumulan y retail con miedo: gasolina alcista"
    elif inst < 40 and ret >= 60:
        ver = "retail eufórico e instituciones vendiendo: techo probable"
    elif inst < 40 and ret < 40:
        ver = "todos venden: pánico, los rebotes se venden"
    else:
        ver = "sin manos claras: mercado mixto"
    return {"inst": inst, "ret": ret, "veredicto": ver, "det": det[:3]}


def psico(last):
    """Niveles psicologicos (miles redondos) mas cercanos arriba/abajo."""
    up = (int(last // 1000) + 1) * 1000
    down = int(last // 1000) * 1000
    if down >= last:  # B5: si last es multiplo exacto, el de abajo es 1000 menos
        down -= 1000
    return up, down


def retest(kl, res, sup, last):
    """Ruptura + vuelta al nivel en las ultimas 24 velas 1H (trampa o confirmacion)."""
    if len(kl) < 24:
        return None
    rec = kl[-24:]
    if last < res["precio"] and any(c["h"] > res["precio"] for c in rec):
        if abs(last - res["precio"]) / res["precio"] <= UMBRAL_TOQUE * 1.5:
            return f"ruptura fallida + re-test de {fmt_miles(res['precio'])}: posible trampa, espera cierre"
    if last > sup["precio"] and any(c["l"] < sup["precio"] for c in rec):
        if abs(last - sup["precio"]) / sup["precio"] <= UMBRAL_TOQUE * 1.5:
            return f"defensa + re-test de {fmt_miles(sup['precio'])}: el soporte aguanta"
    return None


def ruptura(kl_h1, sup, res):
    """Ruptura confirmada: la última vela 1H CERRADA quedó más allá del
    soporte (bajista) o la resistencia (alcista) más cercanos.
    F6: exige vela en dirección del break, cruce real del nivel (la vela previa
    cerraba al otro lado) y margen mínimo, para no cantar "rupturas" de chop
    cuando el soporte/resistencia más cercano se pega al precio.
    Reversible: VIGILANTE_RUPTURA_ESTRICTO=0 vuelve al comportamiento anterior."""
    try:
        if not kl_h1 or len(kl_h1) < 2:
            return None
        vc = kl_h1[-2]
        c = vc["c"]
        o = vc.get("o", c)
        prev = kl_h1[-3] if len(kl_h1) >= 3 else None
        pc = prev.get("c", c) if prev else None
        hh = ""
        try:
            hh = vc["t"].strftime("%H:%M")
        except Exception:
            pass
        estricto = UMBRAL_RUPTURA_ESTRICTO
        if sup and c < sup:
            d = (sup - c) / sup * 100
            if estricto and not (
                c < o and pc is not None and pc >= sup and d >= UMBRAL_RUPTURA_MIN
            ):
                return None
            return f"ruptura BAJISTA confirmada bajo {fmt_miles(sup)} (cierre 1H {hh} en {fmt_miles(c)}, {d:.2f}% debajo)"
        if res and c > res:
            d = (c - res) / res * 100
            if estricto and not (
                c > o and pc is not None and pc <= res and d >= UMBRAL_RUPTURA_MIN
            ):
                return None
            return f"ruptura ALCISTA confirmada sobre {fmt_miles(res)} (cierre 1H {hh} en {fmt_miles(c)}, {d:.2f}% encima)"
        return None
    except Exception:
        return None


def liquidez_nivel(kl, last):
    """Toma de liquidez con datos para plan: barrido 24h + cierre de vuelta.

    Devuelve {"lado": "max"|"min", "nivel", "extremo", "cluster", "texto"} o None.
    "extremo" es la mecha del barrido: sirve de stop estructural del fade.
    Puro, sin red."""
    if len(kl) < 27:
        return None
    base = kl[-27:-3]
    hi = max(c["h"] for c in base)
    lo = min(c["l"] for c in base)
    # niveles iguales (cluster de liquidez): cuantas velas tocan el extremo
    n_hi = sum(1 for c in base if c["h"] >= hi * 0.999)
    n_lo = sum(1 for c in base if c["l"] <= lo * 1.001)
    ult3 = kl[-3:]
    MIN_SWEEP = 0.0005  # 0.05% minimo de barrido (evita ruido)
    if (
        any(c["h"] > hi * (1 + MIN_SWEEP) for c in ult3)
        and last < hi
        and abs(last - hi) / hi <= 0.004
    ):
        extra = f" (×{n_hi})" if n_hi >= 3 else ""
        return {
            "lado": "max",
            "nivel": hi,
            "extremo": max(c["h"] for c in ult3),
            "cluster": n_hi,
            "texto": f"barrido sobre máximos {fmt_miles(hi)}{extra} con devolución (trampa para compradores)",
        }
    if (
        any(c["l"] < lo * (1 - MIN_SWEEP) for c in ult3)
        and last > lo
        and abs(last - lo) / lo <= 0.004
    ):
        extra = f" (×{n_lo})" if n_lo >= 3 else ""
        return {
            "lado": "min",
            "nivel": lo,
            "extremo": min(c["l"] for c in ult3),
            "cluster": n_lo,
            "texto": f"barrido bajo mínimos {fmt_miles(lo)}{extra} con devolución (trampa para vendedores)",
        }
    return None


def liquidez(kl, last):
    """Texto del barrido de liquidez (compatibilidad). None si no hay."""
    d = liquidez_nivel(kl, last)
    return d["texto"] if d else None


def lado_ok(bias, texto):
    """Un solo lado por sesgo: ALZA solo PISO, BAJA solo TECHO, LATERAL ambos.
    Puro. Evita el doble mensaje contradictorio (techo y piso seguidos)."""
    try:
        lado = "PISO" if "PISO" in str(texto) else ("TECHO" if "TECHO" in str(texto) else "?")
        if bias == "LATERAL" or lado == "?":
            return True
        if bias == "ALZA":
            return lado == "PISO"
        if bias == "BAJA":
            return lado == "TECHO"
        return True
    except Exception:
        return True


def mensaje_pila(zonas, last, sops, ress, h1=None, a4=None, hora=None):
    """Texto claro de la zona PILAS mas cercana (o (None, None) si esta lejos).
    Incluye el encajonamiento piso/techo para no confundir (ayer: short bueno
    entre dos zonas). sops/ress: soportes y resistencias ({precio})."""
    if not zonas or not last:
        return None, None
    try:
        zp = min(zonas, key=lambda z: abs(z["precio"] - last))
        dist = abs(zp["precio"] - last) / last
        if dist > 0.0035:
            return None, None
        razones = "+".join(zp.get("razones", [])[:3])
        debajo = sorted((z["precio"] for z in zonas if z["precio"] < last), reverse=True)
        encima = sorted(z["precio"] for z in zonas if z["precio"] > last)
        ctx = ""
        if debajo and encima:
            ctx = f" Estás entre 🛡 {fmt_miles(debajo[0])} y 🧲 {fmt_miles(encima[0])}."
        adv = ""
        try:
            if isinstance(h1, dict):
                er = h1.get("er")
                rsi = h1.get("rsi", 50)
                if (
                    zp["precio"] > last
                    and h1.get("tend") == "ALCISTA"
                    and ((er is not None and er >= 0.4) or rsi >= 60)
                ):
                    adv = " Va contra momentum 1H: tamaño pequeño o espera."
                elif (
                    zp["precio"] <= last
                    and h1.get("tend") == "BAJISTA"
                    and ((er is not None and er >= 0.4) or rsi <= 40)
                ):
                    adv = " Va contra momentum 1H: tamaño pequeño o espera."
        except Exception:
            pass
        rc = ""
        try:
            if isinstance(h1, dict) and isinstance(a4, dict) and hora is not None:
                rsi = h1.get("rsi", 50)
                er = h1.get("er")
                # `er` (Efficiency Ratio de Kaufman) es None cuando el 1H no tiene
                # 30+ velas: se supone 0.2 (chop suave). El fallback debe aplicarse
                # en LAS DOS comparaciones: con `er < 0.4` pelado, er=None hacia
                # TypeError y el except de abajo tiraba el bloque entero.
                er_v = er if er is not None else 0.2
                f = {
                    "rsi": 0 if rsi < 40 else (1 if rsi < 60 else 2),
                    "adx": 1 if (a4.get("adx", 0) or 0) >= 20 else 0,
                    "er": 0 if er_v < 0.15 else (1 if er_v < 0.4 else 2),
                    "ses": sesion_bucket(hora),
                    "h1t": h1.get("tend", "?"),
                    "zt": (
                        0
                        if abs(h1.get("z") or 0) < 1.0
                        else (1 if abs(h1.get("z") or 0) < 2.0 else 2)
                    ),
                }
                p = prob_reaccion(f)
                if p is not None:
                    # F7: el puntaje de prob_reaccion vive en [0.459, 0.580] (media de 6
                    # tablas, base 0.522). Los umbrales 0.55/0.65 dejaban "ALTA" inalcanzable
                    # y "BAJA" en ~89% de los casos. Se alinean a los percentiles reales
                    # (p25≈0.505, p75≈0.537) para que la etiqueta informe de verdad.
                    rc = f" Reacción probable {'ALTA' if p >= 0.540 else ('BAJA' if p < 0.505 else 'MEDIA')} (historial)."
        except Exception:
            pass
        if zp["precio"] <= last:
            inv = sops[0]["precio"] if sops else zp["precio"]
            return (
                f"Zona de referencia: a {dist * 100:.1f}% de {fmt_miles(zp['precio'])} "
                f"({razones}) → 🛡 PISO: estás encima; si cae hasta ahí puede devolver hacia arriba. "
                f"Se anula SOLO si 1H cierra bajo {fmt_miles(inv)}.{ctx}{adv}{rc}"
                f" Zona de referencia, no una entrada.",
                str(zp["precio"]),
            )
        inv = ress[0]["precio"] if ress else zp["precio"]
        return (
            f"Zona de referencia: a {dist * 100:.1f}% de {fmt_miles(zp['precio'])} "
            f"({razones}) → 🧱 TECHO: estás debajo; si sube hasta ahí puede devolver hacia abajo. "
            f"Se anula SOLO si 1H cierra sobre {fmt_miles(inv)}.{ctx}{adv}{rc}"
            f" Zona de referencia, no una entrada.",
            str(zp["precio"]),
        )
    except Exception:
        return None, None


def zonas_pilas(pw, d1, w1, last, ima):
    """Zonas mayores de largo plazo (semanales, diarias, psicologicos, imanes).
    La paciencia vive aqui: el precio vuelve a estas zonas."""
    cands = []
    if pw:
        if pw.get("S1"):
            cands.append((pw["S1"], "S1 semanal"))
        if pw.get("R1"):
            cands.append((pw["R1"], "R1 semanal"))
    cands.append((d1["winL"], "mín 1D"))
    cands.append((d1["winH"], "máx 1D"))
    cands.append((w1["winL"], "mín 1S"))
    cands.append((w1["winH"], "máx 1S"))
    pu, pdn = psico(last)
    cands.append((pu, "psicológico"))
    cands.append((pdn, "psicológico"))
    if ima:
        if ima.get("up"):
            cands.append((ima["up"], "imán"))
        if ima.get("down"):
            cands.append((ima["down"], "imán"))
    zonas: list[dict] = []
    for v, o in cands:
        if not v:
            continue
        v = snap_nivel(v)
        hall = None
        for z in zonas:
            if abs(z["precio"] - v) < 25:
                hall = z
                break
        if hall:
            if o not in hall["razones"]:
                hall["razones"].append(o)
        else:
            zonas.append({"precio": v, "razones": [o]})
    return zonas


def divergencia(kl):
    """Divergencia RSI 1H: precio hace minimo mas bajo pero RSI sube (alcista) y viceversa."""
    closes = [c["c"] for c in kl]
    if len(closes) < 30:
        return None
    p1 = min(closes[-21:-7])
    p2 = min(closes[-7:])
    q1 = max(closes[-21:-7])
    q2 = max(closes[-7:])
    r_prev = rsi(closes[:-7])
    r_now = rsi(closes)
    if p2 < p1 and r_now > r_prev + 2:
        return "alcista"
    if q2 > q1 and r_now < r_prev - 2:
        return "bajista"
    return None


def div_cvd(data=None):
    """Divergencia CVD: precio maximo nuevo + CVD cayendo (distribucion)
    o minimo nuevo + CVD subiendo (absorcion)."""
    if data is None:
        data = None
        for base in (FAPI, VISION):
            try:
                data = fetch(base + "/aggTrades?symbol=BTCUSDT&limit=1000", tries=1)
                break
            except Exception:
                continue
    if not data or len(data) < 200:
        return None
    mid = len(data) // 2

    def _cv(trs):
        s = 0.0
        for tr in trs:
            try:
                q = float(tr["q"])
            except Exception:
                continue
            s += -q if tr.get("m") else q
        return s

    c1, c2 = _cv(data[:mid]), _cv(data[mid:])
    p1 = [float(t["p"]) for t in data[:mid] if t.get("p")]
    p2 = [float(t["p"]) for t in data[mid:] if t.get("p")]
    if not p1 or not p2:
        return None
    if max(p2) > max(p1) and c2 < c1:
        return "bajista (máximo nuevo + CVD cayendo: distribución)"
    if min(p2) < min(p1) and c2 > c1:
        return "alcista (mínimo nuevo + CVD subiendo: absorción)"
    return None


def mapa_liq(kl, last, funding):
    """Mapa ESTIMADO de liquidaciones: los stops viven tras maximos/minimos
    recientes y numeros redondos. El funding cargado marca el lado jugoso
    (contrarian: longs recargados -> stops abajo).
    Devuelve top-5 por lado + imán (lado con más score)."""
    if len(kl) < 30:
        return None
    rec = kl[-72:]
    altos, bajos = [], []
    for i in range(5, len(rec) - 5):
        if all(rec[i]["h"] >= rec[j]["h"] for j in range(i - 5, i + 6) if j != i):
            altos.append(rec[i]["h"])
        if all(rec[i]["l"] <= rec[j]["l"] for j in range(i - 5, i + 6) if j != i):
            bajos.append(rec[i]["l"])
    cands = []
    for h in altos[-5:]:
        cands.append({"precio": round(h), "origen": "stop sobre máximo"})
    for l in bajos[-5:]:
        cands.append({"precio": round(l), "origen": "stop bajo mínimo"})
    base = (int(last // 1000)) * 1000
    for r in (base - 1000, base, base + 1000):
        if r > 0:
            cands.append({"precio": r, "origen": "redondo"})
    f = funding or 0.0
    mag = min(1.0, abs(f) / 0.05)
    for c in cands:
        s = 50
        if c["origen"] == "redondo":
            s += 25
        if f > 0 and c["precio"] < last:
            s += round(25 * mag)
        if f < 0 and c["precio"] > last:
            s += round(25 * mag)
        c["score"] = s
        c["dist"] = round((c["precio"] - last) / last * 100, 2)
    arriba = sorted([c for c in cands if c["precio"] > last], key=lambda x: -x["score"])[:5]
    abajo = sorted([c for c in cands if c["precio"] < last], key=lambda x: -x["score"])[:5]
    if not arriba and not abajo:
        return None
    ta = sum(c["score"] for c in arriba)
    tb = sum(c["score"] for c in abajo)
    tot = ta + tb or 1
    lado = "abajo" if tb >= ta else "arriba"
    return {
        "arriba": arriba,
        "abajo": abajo,
        "iman": {"lado": lado, "pct": round(100 * (tb if lado == "abajo" else ta) / tot)},
    }


def ballenas(data=None):
    """Cinta de ballenas: prints >= UMBRAL_BALLENA en ~3000 trades recientes
    (fapi, con fallback a spot). m=True = vendedor agresivo.
    Ventana ancha porque los prints 5+ son ralos (1-5 por cada 1000)."""
    if data is None:
        data = []
        for base in (FAPI, VISION):
            try:
                pg = fetch(base + "/aggTrades?symbol=BTCUSDT&limit=1000", tries=1)
            except Exception:
                continue
            if not pg:
                continue
            data = list(pg)
            try:
                vistos = {t.get("a") for t in data}
                for _ in range(2):
                    viejos = [t.get("a") for t in data if isinstance(t.get("a"), int)]
                    if not viejos:
                        break
                    pg2 = fetch(
                        base
                        + "/aggTrades?symbol=BTCUSDT&limit=1000&fromId=%d"
                        % max(0, min(viejos) - 1000),
                        tries=1,
                    )
                    if not pg2:
                        break
                    for t in pg2:
                        if t.get("a") not in vistos:
                            vistos.add(t.get("a"))
                            data.append(t)
            except Exception:
                pass
            break
    if not data:
        return None
    buys = sells = 0.0
    nb = ns = 0
    big = 0.0
    for tr in data:
        try:
            q = float(tr["q"])
        except Exception:
            continue
        if q < UMBRAL_BALLENA:
            continue
        if tr.get("m"):
            sells += q
            ns += 1
        else:
            buys += q
            nb += 1
        big = max(big, q)
    if nb + ns == 0:
        return {"nb": 0, "ns": 0, "buys": 0, "sells": 0, "big": 0, "txt": "sin prints de ballenas"}
    if sells > buys * 1.5:
        ver = "ballenas distribuyendo"
    elif buys > sells * 1.5:
        ver = "ballenas acumulando"
    else:
        ver = "ballenas mixtas"
    return {
        "nb": nb,
        "ns": ns,
        "buys": round(buys, 1),
        "sells": round(sells, 1),
        "big": round(big, 1),
        "txt": ver,
    }


def oro_vs_btc(btc_chg):
    """Oro (PAXG) vs BTC: refugio contra riesgo."""
    try:
        paxg = yahoo_cierres("PAXG-USD") or yahoo_cierres("GC=F")
        if not paxg:
            return None
        diff = round(btc_chg - paxg["chg"], 2)
        if diff > 1:
            lec = "apetito por riesgo (BTC manda)"
        elif diff < -1:
            lec = "huida al refugio (oro manda)"
        else:
            lec = "a la par"
        return {"oro": paxg["chg"], "diff": diff, "lectura": lec}
    except Exception:
        return None


def etiquetar_senal(senti, hora, dcvd):
    """Tags solo-medición para validar señales en papel (funding/OI/CVD/sesión).
    Puro, sin red, NO decide nada: solo etiqueta para futuro PF por régimen."""
    try:
        s = senti if isinstance(senti, dict) else {}
        return {
            "funding": s.get("funding"),
            "taker": s.get("taker"),
            "sesion": sesion_bucket(hora) if isinstance(hora, int) else "?",
            "cvd_div": dcvd if isinstance(dcvd, str) else ("sí" if dcvd else "no"),
        }
    except Exception:
        return {"funding": None, "taker": None, "sesion": "?", "cvd_div": "no"}


def ls_global():
    """Ratio long/short global de cuentas (Binance, gratis): lectura contrarian."""
    try:
        d = fetch(f"{FDATA}/globalLongShortAccountRatio?symbol=BTCUSDT&period=1h&limit=1", tries=1)
        r = round(float(d[-1]["longShortRatio"]), 2)
        if r >= 1.5:
            lec = "cuentas cargadas long (contrarian: cuidado arriba)"
        elif r <= 0.8:
            lec = "cuentas cargadas short (contrarian: cuidado abajo)"
        else:
            lec = "posicionamiento equilibrado"
        return {"ratio": r, "lectura": lec}
    except Exception:
        return None


def cvd(data=None):
    """Cumulative Volume Delta con la cinta (fapi, fallback spot).
    Divergencia CVD vs precio = absorcion/distribucion oculta."""
    if data is None:
        data = None
        for base in (FAPI, VISION):
            try:
                data = fetch(base + "/aggTrades?symbol=BTCUSDT&limit=1000", tries=1)
                break
            except Exception:
                continue
    if not data:
        return None
    cv = 0.0
    precios = []
    for tr in data:
        try:
            q = float(tr["q"])
            precios.append(float(tr["p"]))
        except Exception:
            continue
        cv += -q if tr.get("m") else q
    dpx = (precios[-1] - precios[0]) / precios[0] * 100 if len(precios) > 1 and precios[0] else 0
    if cv > 0 and dpx < -0.1:
        lec = "CVD sube y precio baja: absorción (alcista oculto)"
    elif cv < 0 and dpx > 0.1:
        lec = "CVD baja y precio sube: distribución (bajista oculto)"
    elif cv > 0:
        lec = "flujo comprador dominando"
    else:
        lec = "flujo vendedor dominando"
    return {"cvd": round(cv, 1), "dpx": round(dpx, 2), "lectura": lec}
