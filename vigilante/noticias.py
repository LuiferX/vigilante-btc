#!/usr/bin/env python3
"""
noticias.py - PRENSA Y CALENDARIO (Fase 11): RSS con peso por impacto,
calendario macro con cuenta regresiva y escenarios.
"""

import datetime
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

DIR_BULL = (
    "inflow",
    "inflows",
    "buy",
    "buys",
    "bought",
    "record",
    "demand",
    "adopt",
    "approval",
    "approve",
    "accumulat",
    "breakout",
    "rate cut",
    "cuts rates",
)
DIR_BEAR = (
    "outflow",
    "outflows",
    "sell",
    "sells",
    "sold",
    "lawsuit",
    "ban",
    "hack",
    "crash",
    "hike",
    "crackdown",
    "fraud",
    "charged",
    "fine",
    "bankrupt",
)

FEEDS = [
    "https://cointelegraph.com/rss",
    "https://cryptoslate.com/feed/",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/feed",
    "https://bitcoinist.com/feed/",
    "https://watcher.guru/news/feed",
    "https://www.theblock.co/rss.xml",
]


GRUPOS = [
    (
        "macro",
        6,
        r"\b(fed|fomc|rate[- ]?cut|rate[- ]?hike|inflation|cpi|treasury|yield|recession|tariff|dollar)\b",
    ),
    (
        "institucional",
        4,
        r"\b(etf|blackrock|fidelity|microstrateg|mstr|institution|sovereign|reserve|adoption)\b",
    ),
    ("regulacion", 4, r"\b(sec|gensler|regulat|court|ruling|lawsuit|cftc|doj|indict|charged)\b"),
    ("flujos", 5, r"\b(binance|coinbase|tether|usdt|stablecoin|outflow|inflow)\b"),
    ("red", 2, r"\b(halving|hash[- ]?rate|mining|miner|difficulty|lightning|ordinals)\b"),
]


EXPLICA = {
    "macro": "macro EE.UU.: mueve al dolar y a todo el riesgo, incluido BTC",
    "institucional": "dinero grande (ETFs/empresas): entradas = compra, salidas = venta",
    "regulacion": "reglas y juicios: deciden si el dinero grande entra o sale",
    "flujos": "movimiento en exchanges/stablecoins: anticipa compra o venta",
    "red": "salud de la red Bitcoin (mineria): efecto lento, poco inmediato",
}


def peso_noticia(titulo):
    t = titulo.lower()
    s = 0
    tags = []
    if re.search(r"\bbtc\b", t) or "bitcoin" in t:
        s += 4
    for tag, peso, rx in GRUPOS:
        if re.search(rx, t):
            s += peso
            tags.append(tag)
    return s, tags


def impacto_noticia(score):
    if score >= 9:
        return "ALTO (±2-6%)"
    if score >= 6:
        return "MEDIO (±0.5-2%)"
    return "BAJO (<±1%)"


def explicar_noticia(tags):
    if not tags:
        return "tema crypto general con posible efecto en BTC"
    return " + ".join(EXPLICA[t] for t in tags[:2])


def noticias(limit=5, _presupuesto_s=40):
    titulos = []
    _t0_notis = time.monotonic()
    for f in FEEDS:
        try:
            if time.monotonic() - _t0_notis > _presupuesto_s:
                break
            req = urllib.request.Request(f, headers={"User-Agent": "vigilante-cloud/3.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                raw = r.read(512 * 1024)
            root = ET.fromstring(raw)
            n = 0
            for el in root.iter():
                if el.tag.split("}")[-1] not in ("item", "entry"):
                    continue
                if n >= 6:
                    break
                titulo = ""
                for ch in el:
                    if ch.tag.split("}")[-1] == "title" and ch.text:
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
    (
        r"fomc|fed funds|rate decision|statement",
        "la Fed decide las tasas: el evento que mas mueve a BTC",
    ),
    (r"\bcpi\b", "inflacion de EE.UU.: si sale alta, caen los activos de riesgo"),
    (
        r"nfp|non-farm|nonfarm|unemployment|jobless|payroll",
        "empleo de EE.UU.: dato fuerte = menos recortes = cae BTC",
    ),
    (r"\bpce\b", "inflacion favorita de la Fed (PCE)"),
    (r"\bppi\b", "inflacion mayorista (PPI): adelanta al CPI"),
    (r"retail sales", "ventas minoristas: mide al consumidor de EE.UU."),
    (r"\bgdp\b", "crecimiento (PIB) de EE.UU."),
    (r"powell|fomc member|testimony|speech", "habla la Fed: cada palabra mueve al dolar y a BTC"),
]


def explicar_evento(titulo):
    t = titulo.lower()
    for rx, exp in CAL_EXP:
        if re.search(rx, t):
            return exp
    return "dato macro de EE.UU.: mueve al dolar y a BTC"


def impacto_evento(impact):
    return "ALTO (±3-8%)" if impact == "High" else "MEDIO (±0.5-2%)"


def calendario(limit=5, incluir_pasadas_h=0):
    """Próximos eventos USD (High/Medium). Con `incluir_pasadas_h>0` también
    devuelve los ocurridos en las últimas N horas (para el estudio de eventos)."""
    evs = []
    try:
        req = urllib.request.Request(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            headers={"User-Agent": "vigilante-cloud/3.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
    except Exception:
        return []
    ahora = datetime.datetime.now(datetime.timezone.utc)
    try:
        limite_pasado = ahora - datetime.timedelta(hours=max(0.0, float(incluir_pasadas_h or 0)))
    except Exception:
        limite_pasado = ahora
    for e in data:
        if e.get("country") != "USD":
            continue
        if e.get("impact") not in ("High", "Medium"):
            continue
        try:
            cuando = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        if cuando < limite_pasado:
            continue
        evs.append(
            {
                "titulo": e.get("title", ""),
                "cuando": cuando,
                "impact": e.get("impact"),
                "forecast": e.get("forecast"),
                "previous": e.get("previous"),
            }
        )
    evs.sort(key=lambda x: x["cuando"])
    return evs[:limit]


def direccion_noticia(titulo):
    t = titulo.lower()
    b = any(k in t for k in DIR_BULL)
    s = any(k in t for k in DIR_BEAR)
    if b and not s:
        return 1
    if s and not b:
        return -1
    return 0


def presion_noticias(notis):
    """Presion direccional neta de las noticias (-100..+100), ponderada por peso."""
    if not notis:
        return {"valor": 0, "txt": "sin noticias", "nb": 0, "ns": 0}
    sw = sum(n["score"] * direccion_noticia(n["titulo"]) for n in notis)
    w = sum(n["score"] for n in notis) or 1
    v = round(sw / w * 100)
    nb = sum(1 for n in notis if direccion_noticia(n["titulo"]) > 0)
    ns = sum(1 for n in notis if direccion_noticia(n["titulo"]) < 0)
    et = "alcista" if v >= 25 else ("bajista" if v <= -25 else "mixta")
    return {"valor": v, "txt": f"{v:+d} {et} ({nb}🟢/{ns}🔴)", "nb": nb, "ns": ns}
