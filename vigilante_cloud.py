#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vigilante_cloud.py - VIGILANTE BTCUSDT v6 (1H 4H 1D 1S) en la nube.

v6 institucional: score A/B/C, regimen ADX + MACD en rango, veto premium/DXY,
blackout de eventos, anti-spam por categoria, PILAS techo/piso, plan 2R,
paper invisible con frenos, precision MFE/MAE a 8h.
v5 Companero (tono, narrativa, memoria, comandos) + v4 Maquina + v3 base.

SEGURIDAD: solo API publica de Binance (+ espejo vision si bloquean).
Secretos por variables de entorno. Sin API keys, sin trading.
"""

import datetime
import json
import math
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

VERSION = "v6"

FAPI = "https://fapi.binance.com/fapi/v1"
FDATA = "https://fapi.binance.com/futures/data"
VISION = "https://data-api.binance.vision/api/v3"
FUENTE = {"nombre": "futuros"}
# Fuente de mercado: se fija UNA vez por pasada para que precio y velas vengan
# del mismo sitio. Antes cada llamada hacia su propio fallback y una pasada podia
# quedar con klines de futuros y ticker de spot (mezcla inconsistente).
MERCADO = {"base": None}


def _elegir_fuente():
    """Fija FAPI (futuros) o VISION (spot) para TODA la pasada. Devuelve la base."""
    if MERCADO.get("base"):
        return MERCADO["base"]
    try:
        fetch(f"{FAPI}/ping", tries=1)
        MERCADO["base"] = FAPI
        FUENTE["nombre"] = "futuros"
    except Exception:
        MERCADO["base"] = VISION
        FUENTE["nombre"] = "spot"
    return MERCADO["base"]

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


def calendario(limit=5, incluir_pasadas_h=0):
    """Próximos eventos USD (High/Medium). Con `incluir_pasadas_h>0` también
    devuelve los ocurridos en las últimas N horas (para el estudio de eventos)."""
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
    try:
        limite_pasado = ahora - datetime.timedelta(hours=max(0.0, float(incluir_pasadas_h or 0)))
    except Exception:
        limite_pasado = ahora
    for e in data:
        if e.get('country') != 'USD':
            continue
        if e.get('impact') not in ('High', 'Medium'):
            continue
        try:
            cuando = datetime.datetime.fromisoformat(e['date'].replace('Z', '+00:00'))
        except Exception:
            continue
        if cuando < limite_pasado:
            continue
        evs.append({"titulo": e.get('title', ''), "cuando": cuando, "impact": e.get('impact'),
                      "forecast": e.get('forecast'), "previous": e.get('previous')})
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
MAX_PEND_TODO = 100
MAX_EVAL_TODO = 200
MAX_PAPER_ABIERTAS = 5
MAX_OPS = 20
MAX_DELTAS = 25
EVAL_HORAS = 8
UMBRAL_MOV = 0.002
UMBRAL_CONF_FUERTE = 55
UMBRAL_CONF_CAMBIO = 40
UMBRAL_CONF_SENAL = 50    # subido de 45: menos señales, mayor calidad (replay: confluencia > umbral solo)
UMBRAL_PAPEL = 40         # subido de 35: el papel aprende con menos ruido
UMBRAL_TOQUE = 0.0025  # 0.25% del nivel = "tocando"
# F6: anti "ruptura de chop". Una ruptura confirmada DEBE tener la vela en la
# direccion del break (roja=bajista, verde=alcista), cruzar el nivel de verdad
# (la vela previa cerraba al otro lado) y superar un margen minimo. Evita cantar
# "ruptura BAJISTA" cuando el soporte mas cercano sube pegado al precio en subida.
UMBRAL_RUPTURA_MIN = float(os.environ.get("VIGILANTE_RUPTURA_MIN", "0.30"))   # margen minimo % mas alla del nivel
UMBRAL_RUPTURA_ESTRICTO = os.environ.get("VIGILANTE_RUPTURA_ESTRICTO", "1") not in ("", "0", "false", "False")
DEDUP_HORAS = 4          # misma direccion en 4 h = 1 sola senal (sin duplicados)
UMBRAL_ATR_MULT = 0.5    # acierto = moverse >= 0.5 * ATR 1H a favor (relativo al mercado)
FEE_PCT = 0.001          # 0.10% ida+vuelta (costo de operar)
FILTRO_VOL = False        # opt-in: descarta senales cuando FEE/umbral > 0.25 (break-even > 41.7%)
MIN_SENALES = 5          # minimo de senales para mostrar % de precision
FUNDING_EXTREMO = 0.05   # |funding| >= 0.05% = un lado recargado (lectura contrarian)
UMBRAL_BRUSCO = float(os.environ.get("VIGILANTE_UMBRAL_BRUSCO", "1.5"))  # +/-1.5% en 1h: ruido comun, no aviso
UMBRAL_RITMO = float(os.environ.get("VIGILANTE_UMBRAL_RITMO", "1.5"))    # +/-1.5% en 30min: movimiento real
GATE_FILE = os.environ.get("VIGILANTE_VALIDATION", "analysis/data/validation.json")
UMBRAL_DIA_NY = 2.0      # +/-2% en el dia NY = dia de tendencia (avisa)
UMBRAL_BALLENA = 5       # print >= 5 BTC (~$400k) = huella de ballena
BLACKOUT_MIN = 30        # sin senales nuevas X min antes/despues de evento High
SEMILLA_SESION = {"NY": 1.0, "Londres": 1.0, "noche": 1.0, "Asia": 1.0}  # neutra: ver doc
PAPER_BANCO = float(os.environ.get("PAPER_BANCO", "100.0"))   # perfil XLX: banco virtual en USDT
PAPER_LEV = int(os.environ.get("PAPER_LEV", "50"))   # apalancamiento: solo dimensiona la liquidacion estimada
PAPER_RIESGO = 0.01    # 1% por idea (0.5% en racha de 3+ perdidas)


def _gate_desde_validacion(data):
    """Convierte validation.json en un permiso explicito para alertas direccionales.

    No es una opinion: si no hay muestra efectiva, Brier skill positivo y drift
    controlado, el bot no debe convertir una corazonada en senal.

    Canales de evidencia (el primero que califica abre la puerta):
      - vivo: 100+ muestras efectivas del flujo real, skill>0, ECE<=0.08, drift ok.
      - oos:  backtest purgado (analysis/backtest.py) con 100+ muestras etiquetadas
              sin solapamiento, skill>0, ECE<=0.08, drift ok. Evidencia debil pero
              medida; validation.json la reporta en gate.canal.
    El canal vivo siempre puede veto: si su estado es degradado/roto, no se abre.
    """
    if not isinstance(data, dict):
        return {"ok": False, "reason": "sin validation.json"}
    samples = data.get("samples") if isinstance(data.get("samples"), dict) else {}
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    drift = data.get("drift") if isinstance(data.get("drift"), dict) else {}
    status = str(data.get("status") or "sin_datos")
    gate = data.get("gate") if isinstance(data.get("gate"), dict) else {}
    oos = data.get("oos") if isinstance(data.get("oos"), dict) else {}
    try:
        effective = int(samples.get("effective") or 0)
    except Exception:
        effective = 0
    try:
        skill = float(metrics.get("brier_skill"))
    except Exception:
        skill = None
    try:
        ece = float(metrics.get("calibration_error"))
    except Exception:
        ece = None
    drift_status = str(drift.get("status") or "sin_datos")
    partes = [status]
    if effective:
        partes.append(f"{effective} efectivas")
    if skill is not None:
        partes.append(f"skill {skill:+.2f}")
    if ece is not None:
        partes.append(f"ECE {ece:.2f}")
    if drift_status == "alert":
        partes.append("drift alert")
    # 1) canal vivo (como siempre)
    if (status == "ok"
            and effective >= 100
            and skill is not None and skill > 0
            and ece is not None and ece <= 0.08
            and drift_status != "alert"):
        return {"ok": True, "reason": "vivo · " + " · ".join(partes)}
    # 2) canal OOS: validation.json ya lo calcula (oos_valido + sin veto vivo)
    canal = str(gate.get("canal") or "")
    if canal == "oos":
        try:
            o_eff = int(oos.get("effective") or 0)
        except Exception:
            o_eff = 0
        try:
            o_skill = float(oos.get("brier_skill"))
        except Exception:
            o_skill = None
        try:
            o_ece = float(oos.get("ece"))
        except Exception:
            o_ece = None
        if (o_eff >= 100 and o_skill is not None and o_skill > 0
                and o_ece is not None and o_ece <= 0.08
                and status not in ("roto", "degradado")):
            partes.append(f"OOS {o_eff} muestras · skill {o_skill:+.4f} · ECE {o_ece:.3f}")
            return {"ok": True, "reason": " · ".join(partes)}
    return {"ok": False, "reason": " · ".join(partes)}


def cargar_gate_validacion(path=None):
    try:
        with open(path or GATE_FILE, encoding="utf-8") as fh:
            return _gate_desde_validacion(json.load(fh))
    except Exception:
        return {"ok": False, "reason": "sin validation.json"}


MOTOR_FILE = os.environ.get("VIGILANTE_MOTOR", "analysis/data/latest_decision.json")


def cargar_motor_nuevo(path=None, max_age_min=90):
    """Lee el motor 4h nuevo (solo contexto, no ejecuta ni decide por el bot).

    Devuelve None si no existe o esta viejo. El bot viejo puede seguir midiendo
    y alertando con su propia logica; esto solo evita contar dos historias.
    """
    try:
        with open(path or MOTOR_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    ts = d.get("event_time") or d.get("logged_at")
    edad = None
    try:
        t = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        edad = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 60
    except Exception:
        pass
    if edad is not None and edad > max_age_min:
        return None
    dec = d.get("decision") if isinstance(d.get("decision"), dict) else {}
    state = d.get("state") if isinstance(d.get("state"), dict) else {}
    return {
        "action": str(dec.get("action") or "?"),
        "confidence": dec.get("confidence"),
        "trigger": str(dec.get("trigger") or ""),
        "invalidation": str(dec.get("invalidation") or ""),
        "bias": state.get("bias"),
        "price": d.get("price"),
        "summary": str(d.get("summary") or ""),
        "age_min": round(edad, 1) if edad is not None else None,
    }


def linea_motor(motor):
    """Linea corta para reportes de Telegram. Vacia si no hay motor fresco."""
    if not isinstance(motor, dict):
        return ""
    partes = [f"motor 4h: {motor.get('action', '?')}"]
    if motor.get("bias"):
        partes.append(f"sesgo {motor['bias']}")
    if motor.get("age_min") is not None:
        partes.append(f"hace {motor['age_min']:.0f} min")
    txt = " · ".join(partes)
    if motor.get("trigger"):
        txt += f" · trigger {motor['trigger'][:90]}"
    return txt


# ---------------- Modo PRECISION: avisos de nivel defendido -----------------
# Solo avisa cuando el motor 4h marca un nivel con aguante medido alto
# (hold_prob alto, 3+ toques reales, calidad alta, sin quiebre confirmado) y el
# precio esta cerca. NO es una orden: publica la probabilidad medida y su muestra.
BT_FILE = os.environ.get("VIGILANTE_MOTOR_BT", "analysis/data/backtest.json")
VALIDATION_FILE = os.environ.get("VIGILANTE_VALIDATION", "analysis/data/validation.json")
PRECISION_MODO = os.environ.get("VIGILANTE_PRECISION", "1") not in ("", "0", "false", "False")
PRECISION_MIN_PROB = float(os.environ.get("VIGILANTE_PRECISION_MIN", "0.85"))
PRECISION_MIN_CALIDAD = float(os.environ.get("VIGILANTE_PRECISION_CALIDAD", "8.0"))
PRECISION_MIN_TOQUES = int(os.environ.get("VIGILANTE_PRECISION_TOQUES", "3"))
PRECISION_MAX_EDAD_MIN = float(os.environ.get("VIGILANTE_PRECISION_EDAD", "20"))
PRECISION_CERCA_PCT = float(os.environ.get("VIGILANTE_PRECISION_CERCA", "0.35"))
PRECISION_DEDUP_HORAS = float(os.environ.get("VIGILANTE_PRECISION_DEDUP", "12"))
PRECISION_EVAL_HORAS = 4.0   # mismo horizonte que el motor (48 velas de 5m)


def cargar_motor_full(path=None, max_age_min=None):
    """Lee analysis/data/latest_decision.json completo (niveles incluidos).

    Devuelve None si no existe o si el registro es mas viejo que la tolerancia.
    """
    try:
        with open(path or MOTOR_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    if max_age_min is None:
        max_age_min = PRECISION_MAX_EDAD_MIN * 4.5  # holgado: el filtro fino va en nivel_precision
    ts = d.get("event_time") or d.get("logged_at")
    try:
        t = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        edad = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 60
        if edad > max_age_min:
            return None
        d["_edad_min"] = round(edad, 1)
    except Exception:
        return None
    return d


def precision_evidencia(path=None):
    """Banda >=0.80 del backtest OOS: muestra y acierto real medidos (o None)."""
    try:
        with open(path or BT_FILE, encoding="utf-8") as fh:
            bt = json.load(fh)
    except Exception:
        return None
    if not isinstance(bt, dict):
        return None
    for b in bt.get("bins") or []:
        if str(b.get("bin", "")).startswith("0.80"):
            try:
                return {"n": int(b.get("n") or 0), "real": float(b.get("real") or 0),
                        "pred": float(b.get("pred") or 0),
                        "skill": bt.get("brier_skill"),
                        "muestras": int(bt.get("samples") or 0),
                        "inicio": bt.get("start")}
            except Exception:
                return None
    return None


def nivel_precision(motor, precio, min_prob=None, min_cal=None, min_toques=None, max_edad=None):
    """Mejor nivel del motor que califica como 'defendido' (o None). Puro."""
    if not isinstance(motor, dict) or not precio or precio <= 0:
        return None
    min_prob = PRECISION_MIN_PROB if min_prob is None else min_prob
    min_cal = PRECISION_MIN_CALIDAD if min_cal is None else min_cal
    min_toques = PRECISION_MIN_TOQUES if min_toques is None else min_toques
    max_edad = PRECISION_MAX_EDAD_MIN if max_edad is None else max_edad
    edad = motor.get("_edad_min")
    if edad is not None and edad > max_edad:
        return None
    dec = motor.get("decision") if isinstance(motor.get("decision"), dict) else {}
    if str(dec.get("action") or "") == "datos_desactualizados":
        return None
    mejor = None
    for lv in motor.get("levels") or []:
        if not isinstance(lv, dict):
            continue
        prob = lv.get("hold_prob")
        if prob is None:
            continue
        try:
            prob = float(prob)
        except (TypeError, ValueError):
            continue
        if prob < min_prob:
            continue
        try:
            calidad = float(lv.get("quality") or 0)
            toques = int(lv.get("touches_6h") or 0)
        except (TypeError, ValueError):
            continue
        if calidad < min_cal or toques < min_toques:
            continue
        if lv.get("break_confirmed"):
            continue                      # un nivel roto no esta "defendido"
        center = lv.get("center")
        if not center or center <= 0:
            continue
        cerca = abs(center - precio) / precio * 100
        if cerca > PRECISION_CERCA_PCT:
            continue                      # el aviso es "precio en el nivel"
        if mejor is None or prob > mejor[0]:
            mejor = (prob, lv, calidad, toques, cerca)
    if not mejor:
        return None
    prob, lv, calidad, toques, cerca = mejor
    return {"nivel": lv.get("center"), "lado": lv.get("role"), "prob": round(prob, 3),
            "calidad": round(calidad, 1), "toques": toques, "cerca": round(cerca, 2),
            "round_level": lv.get("round_level"), "confluencia": lv.get("htf_confluence"),
            "edad_min": motor.get("_edad_min"), "bias": (motor.get("state") or {}).get("bias"),
            "accion": dec.get("action"), "confianza": dec.get("confidence")}


def precision_nueva(est, nivel, ahora):
    """Dedup por nivel: 1 aviso por nivel cada PRECISION_DEDUP_HORAS. Puro."""
    clave = f"{nivel['nivel']:.0f}:{nivel['lado']}"
    try:
        ult = est.get("precision_ult") or {}
        prev = ult.get(clave)
        if prev:
            dt = (ahora - datetime.datetime.fromisoformat(prev)).total_seconds() / 3600
            if dt < PRECISION_DEDUP_HORAS:
                return False
    except Exception:
        pass
    return True


def texto_alerta_precision(nivel, precio, evidencia=None):
    """Mensaje del aviso de precision. Nunca suena a orden."""
    prob = nivel["prob"]
    lado = "soporte" if str(nivel["lado"]).lower().startswith("sop") else "resistencia"
    L = [f"🧱 NIVEL DEFENDIDO · {lado} {fmt_miles(nivel['nivel'])}"]
    L.append(f"Precio {fmt_miles(precio)} a {nivel['cerca']}% del nivel · "
             f"aguante estimado {prob * 100:.0f}% (fallo ~{100 * (1 - prob):.0f}%)")
    L.append(f"Evidencia: {nivel['toques']} toques reales en 6h · calidad {nivel['calidad']}/10"
             + (f" · confluencia {nivel['confluencia']} temporalidades"
                if nivel.get("confluencia") else ""))
    if evidencia:
        L.append(f"Medido fuera de muestra: {evidencia['muestras']} casos desde "
                 f"{str(evidencia['inicio'])[:10]}, banda alta rindió {evidencia['real'] * 100:.0f}%")
    L.append("Solo aviso, no es orden ni entrada: el aguante se anula con cierre 4h más allá del nivel.")
    return "\n".join(L)


def registrar_pend_precision(est, nivel, ahora):
    pend = est.get("pend_precision") or []
    pend.append({"t": ahora.isoformat(), "nivel": nivel["nivel"], "lado": nivel["lado"],
                 "prob": nivel["prob"], "toques": nivel["toques"], "calidad": nivel["calidad"]})
    est["pend_precision"] = pend[-60:]
    ult = est.get("precision_ult") or {}
    ult[f"{nivel['nivel']:.0f}:{nivel['lado']}"] = ahora.isoformat()
    est["precision_ult"] = ult


def evaluar_precision(est, ahora, velas=None):
    """Mide los avisos vencidos (>=4h) con la MISMA definicion del motor: el nivel
    aguanto si ningun cierre 5m cayo 0,5% mas alla del nivel en 4h."""
    pend = est.get("pend_precision") or []
    if not pend:
        return
    if velas is None:
        try:
            velas = klines("5m", 70)
        except Exception:
            return
    vivas = []
    barras = int(PRECISION_EVAL_HORAS * 60 / 5)
    for p in pend:
        try:
            t0 = datetime.datetime.fromisoformat(p["t"])
        except Exception:
            continue
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=datetime.timezone.utc)
        if (ahora - t0).total_seconds() / 3600 < PRECISION_EVAL_HORAS:
            vivas.append(p)
            continue
        nivel = float(p.get("nivel") or 0)
        if nivel <= 0:
            continue
        ventana = [v for v in velas
                   if t0 < v["t"] <= t0 + datetime.timedelta(hours=PRECISION_EVAL_HORAS)]
        if len(ventana) < barras:
            vivas.append(p)
            continue
        lado = str(p.get("lado") or "").lower()
        if lado.startswith("sop"):
            aguanto = all(v["c"] >= nivel * 0.995 for v in ventana)
        else:
            aguanto = all(v["c"] <= nivel * 1.005 for v in ventana)
        log = est.get("precision_log") or []
        log.append({"t": ahora.isoformat(), "nivel": nivel, "lado": p.get("lado"),
                    "prob": p.get("prob"), "r": 1 if aguanto else 0})
        est["precision_log"] = log[-200:]
    est["pend_precision"] = vivas[-60:]


def deriva_regimen(path=None):
    """Estado de deriva del validador (alert/watch/ok/sin_datos). Tolerante.

    Si la deriva esta en alerta, el bot NO publica probabilidades medidas:
    el regimen cambio y la muestra vieja ya no describe el presente.
    """
    try:
        with open(path or VALIDATION_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        drift = d.get("drift") if isinstance(d.get("drift"), dict) else {}
        return str(drift.get("status") or "sin_datos")
    except Exception:
        return "sin_datos"


def precision_stats(est):
    """Precision medida de los avisos de precision (para /precision y dashboard)."""
    log = est.get("precision_log") or []
    if not log:
        return None
    n = len(log)
    ok_n = sum(1 for x in log if x.get("r") == 1)
    altos = [x for x in log if (x.get("prob") or 0) >= PRECISION_MIN_PROB]
    altos_ok = sum(1 for x in altos if x.get("r") == 1)
    return {"n": n, "aciertos": ok_n, "tasa": round(ok_n / n, 3) if n else None,
            "banda_alta_n": len(altos), "banda_alta_ok": altos_ok,
            "banda_alta_tasa": round(altos_ok / len(altos), 3) if altos else None}


def es_alerta_direccional(motivo):
    """True solo para textos que invitan a tomar direccion o traen un plan."""
    m = str(motivo or "").lower()
    if "no es entrada" in m or "no una entrada" in m or "sin plan" in m or "solo aviso" in m:
        return False
    marcas = (
        "señal fuerte", "cambio de dirección", "compra ", "venta ",
        "rechazo ", "tocando ", "toma de liquidez", "r:r", "stop ", "sl ",
    )
    return any(x in m for x in marcas)


def aplicar_gate_alerta(enviar, motivo, tipo, gate, forzado=None, gestion=None):
    """Devuelve (enviar, motivo, tipo, bloqueada). Puro y testeable."""
    if not enviar or tipo != "alerta":
        return enviar, motivo, tipo, False
    if forzado or gestion:
        return enviar, motivo, tipo, False
    if not isinstance(gate, dict) or gate.get("ok"):
        return enviar, motivo, tipo, False
    if not es_alerta_direccional(motivo):
        return enviar, motivo, tipo, False
    return False, f"silenciada por validacion: {gate.get('reason', 'sin evidencia')}", "nada", True


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
    base = MERCADO.get("base") or FAPI
    try:
        data = fetch(f"{base}/klines?symbol=BTCUSDT&interval={interval}&limit={limit}")
    except Exception:
        alt = VISION if base == FAPI else FAPI
        data = fetch(f"{alt}/klines?symbol=BTCUSDT&interval={interval}&limit={limit}", tries=2)
        MERCADO["base"] = alt
        FUENTE["nombre"] = "spot" if alt == VISION else "futuros"
    if not isinstance(data, list) or not data:
        raise ValueError("klines vacías o error API")
    data = [k for k in data if isinstance(k, (list, tuple)) and len(k) >= 6]
    if not data:
        raise ValueError("klines sin filas válidas")
    return [
        {
            "t": datetime.datetime.fromtimestamp(k[0] / 1000, datetime.timezone.utc),
            "o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
            "c": float(k[4]), "v": float(k[5]),
        }
        for k in data
    ]


def ticker24():
    base = MERCADO.get("base") or FAPI
    try:
        t = fetch(f"{base}/ticker/24hr?symbol=BTCUSDT")
    except Exception:
        alt = VISION if base == FAPI else FAPI
        t = fetch(f"{alt}/ticker/24hr?symbol=BTCUSDT", tries=2)
        MERCADO["base"] = alt
        FUENTE["nombre"] = "spot" if alt == VISION else "futuros"
    try:
        last = float(t.get("lastPrice"))
        chg = float(t.get("priceChangePercent"))
        hi = float(t.get("highPrice"))
        lo = float(t.get("lowPrice"))
    except Exception:
        raise ValueError("ticker24 sin claves")
    return {
        "last": last,
        "chg": chg,
        "hi": hi,
        "lo": lo,
        "vol": float(t.get("volume", 0) or 0),
    }


def sentiment():
    out = {"funding": None, "oi": None, "taker": None, "spread": None}
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
    try:
        b = fetch(f"{VISION}/ticker/bookTicker?symbol=BTCUSDT", tries=1)
        bid, ask = float(b["bidPrice"]), float(b["askPrice"])
        mid = (bid + ask) / 2
        if mid > 0:
            out["spread"] = round((ask - bid) / mid * 10000, 2)
    except Exception:
        pass
    return out


def regla_spread(spread_bps):
    """Ejecución por spread (Kaiko/Bybit): market/limit/pausa. Puro."""
    try:
        s = float(spread_bps)
    except Exception:
        return "s/d"
    if s <= 3:
        return "market ok"
    if s <= 5:
        return "mejor limit"
    return "pausa"


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
        trs.append(max(candles[i]["h"] - candles[i]["l"],
                       abs(candles[i]["h"] - pc),
                       abs(candles[i]["l"] - pc)))
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


def swings_idx(candles, k=2):
    """Swings con índice: [(i, máximo), ...], [(i, mínimo), ...]. Puro."""
    try:
        hs, ls = [], []
        n = len(candles or [])
        for i in range(k, n - k):
            try:
                if all(candles[i]["h"] >= candles[j]["h"] for j in range(i - k, i + k + 1) if j != i):
                    hs.append((i, candles[i]["h"]))
                if all(candles[i]["l"] <= candles[j]["l"] for j in range(i - k, i + k + 1) if j != i):
                    ls.append((i, candles[i]["l"]))
            except Exception:
                continue
        return hs, ls
    except Exception:
        return [], []


def find_swing_points(h, l, n=3):
    """Swing points estrictos (n velas a cada lado), estilo FractalTrader."""
    try:
        hs, ls = [], []
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
        clusters = []
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


MIN_RR_ALERTA = float(os.environ.get("VIGILANTE_MIN_RR", "2.0"))
MAX_STOP_ATR = float(os.environ.get("VIGILANTE_MAX_STOP_ATR", "1.6"))


def plan_trade(lado, precio, niv, atr, stop=None, min_rr=None, max_stop_atr=None):
    """Plan con riesgo definido para una alerta (no predice: acota el riesgo).

    lado: soporte|resistencia|long|short|rup_alcista|rup_bajista.
    Objetivo = siguiente nivel opuesto; si no hay, 2R.
    Solo es valido si rr >= MIN_RR_ALERTA y el stop <= MAX_STOP_ATR*ATR.
    Puro: sin red ni estado. Si no hay ATR devuelve None (modo compatible).
    """
    try:
        min_rr = MIN_RR_ALERTA if min_rr is None else float(min_rr)
        max_stop_atr = MAX_STOP_ATR if max_stop_atr is None else float(max_stop_atr)
        precio = float(precio)
        atr = float(atr or 0)
        if precio <= 0 or atr <= 0:
            return None
        res = sorted(float(x["precio"]) for x in (niv or {}).get("resistencias", [])
                     if isinstance(x, dict) and x.get("precio"))
        sup = sorted((float(x["precio"]) for x in (niv or {}).get("soportes", [])
                      if isinstance(x, dict) and x.get("precio")), reverse=True)
    except Exception:
        return None
    entrada = precio
    if lado in ("soporte", "long", "rup_alcista"):
        dir_ = "ALZA"
        if stop is None:
            ref = sup[0] if sup else precio - atr
            stop = ref - 0.5*atr
        obj = next((r for r in res if r > entrada + 0.1*atr), None)
    elif lado in ("resistencia", "short", "rup_bajista"):
        dir_ = "BAJA"
        if stop is None:
            ref = res[0] if res else precio + atr
            stop = ref + 0.5*atr
        obj = next((s for s in sup if s < entrada - 0.1*atr), None)
    else:
        return None
    try:
        stop = float(stop)
    except Exception:
        return None
    riesgo = abs(entrada - stop)
    if riesgo <= 1e-9:
        return None
    if obj is None:
        obj = entrada + 2*riesgo if dir_ == "ALZA" else entrada - 2*riesgo
    if (dir_ == "ALZA" and obj <= entrada) or (dir_ == "BAJA" and obj >= entrada):
        return None
    rr = abs(obj - entrada)/riesgo
    stop_pct = riesgo/entrada*100
    return {"dir": dir_, "entrada": round(entrada, 1), "stop": round(stop, 1),
            "objetivo": round(obj, 1), "rr": round(rr, 2),
            "stop_pct": round(stop_pct, 2),
            "valido": bool(rr >= min_rr and riesgo <= max_stop_atr*atr)}


def texto_plan(plan):
    """Linea compacta del plan. Vacía si no hay plan."""
    try:
        if not isinstance(plan, dict):
            return ""
        return (f"📐 {plan['dir']}: stop {fmt_miles(plan['stop'])} (-{plan['stop_pct']:.2f}%) · "
                f"objetivo {fmt_miles(plan['objetivo'])} · R:R {plan['rr']:.1f}")
    except Exception:
        return ""


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
                return {"dir": "ALZA", "nivel": round(l), "mid": round((l + cl) / 2),
                        "ref": round(cl), "ratio": round(ri, 3),
                        "fuerza": "fuerte" if fuerte else "media"}
            if rs >= RATIO_MIN and rs > ri and ri <= OPUESTA_MAX:
                if ms < MECHA_MIN_USDT or ms / cl * 100 < MECHA_MIN_PCT:
                    continue
                fuerte = rs >= 0.65 and rc <= 0.20
                return {"dir": "BAJA", "nivel": round(h), "mid": round((h + cl) / 2),
                        "ref": round(cl), "ratio": round(rs, 3),
                        "fuerza": "fuerte" if fuerte else "media"}
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
        "adx": adx(candles), "er": eficiencia(closes), "z": zscore(closes),
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


GRID_NIVELES = 500  # rejilla fija: max14/min14 caminan cada hora; sin snap cada pasada es un "nivel nuevo" y re-dispara cooldowns


def snap_nivel(v):
    """Ancla un nivel a la rejilla para que tenga identidad estable entre pasadas."""
    try:
        return int(round(float(v) / GRID_NIVELES) * GRID_NIVELES)
    except Exception:
        return v


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
        mem = est.get("mem_zonas")
        if not isinstance(mem, dict):
            mem = {}
        vig = est.get("vig_zona")
        if not isinstance(vig, dict):
            vig = {}
        for lado, nueva, es_res in (("res", res, True), ("sop", sop, False)):
            try:
                ant = float((vig.get(lado) or {}).get("nivel"))
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
                wherein = high is not None and high >= ant * 0.999 and (close is None or close <= ant)
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
            mem = dict(sorted(mem.items(), key=lambda kv: -((kv[1] or {}).get("hold", 0) + (kv[1] or {}).get("rompe", 0)))[:60])
        est["mem_zonas"] = mem
        est["vig_zona"] = vig
    except Exception:
        pass


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
        sups.append({"precio": h1["winL"], "origen": "min14 1H cercano",
                     "origenes": ["min14 1H cercano"], "n": 1})
    if not ress:
        ress.append({"precio": h1["winH"], "origen": "max14 1H cercano",
                     "origenes": ["max14 1H cercano"], "n": 1})
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


def clamp(x, a, b):
    return max(a, min(b, x))


def eficiencia(closes, n=30):
    """Efficiency Ratio de Kaufman (sin dependencias): |cambio neto| / camino.
    >0.5 el precio va a alguna parte (tendencia), <0.25 puro ruido (chop).
    None si no hay datos suficientes."""
    try:
        xs = list(closes[-n - 1:])
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


def fmt_miles(x):
    return f"{x:,.0f}".replace(",", ".")


def sesion_hora():
    """Sesión actual en UTC, alineada con `sesion_bucket` (Asia/Londres/NY/noche).
    Antes decía "fuera de sesion" durante Asia (00–08 UTC) y llamaba "solape" a
    toda la tarde. Ahora: Asia 00–08, Londres 08–13:30, solape 13:30–16:30,
    NY 16:30–21, noche 21–24."""
    now = datetime.datetime.now(datetime.timezone.utc)
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


# ---------------- Companero: tono, narrativa, memoria, comandos ------------

ABRIDORES = [
    "Oye, te cuento lo que veo",
    "Reporte desde la nube",
    "Pasaba por aquí y vi esto",
    "Actualización del mercado",
    "Te traigo noticias frescas",
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


def pivotes_micro(kl, k=5, tol=0.0015):
    """Niveles locales de corto plazo a partir de pivotes (por defecto 5m).
    Agrupa pivotes cercanos para que un triple toque sea UN nivel, no tres."""
    try:
        if not kl or len(kl) < 2 * k + 3:
            return []
        crudos = []
        for i in range(k, len(kl) - k):
            ventana = kl[i - k:i + k + 1]
            if kl[i]["h"] >= max(x["h"] for x in ventana):
                crudos.append(kl[i]["h"])
            if kl[i]["l"] <= min(x["l"] for x in ventana):
                crudos.append(kl[i]["l"])
        out = []
        for p in sorted(crudos):
            hit = next((o for o in out if abs(o["precio"] - p) / p <= tol), None)
            if hit is None:
                out.append({"precio": p, "n": 1})
            else:
                n = hit["n"]
                hit["precio"] = (hit["precio"] * n + p) / (n + 1)
                hit["n"] = n + 1
        return out
    except Exception:
        return []


def toques_en_nivel(kl, nivel, tol=0.0015, salida=0.003, sep=12):
    """Cuenta visitas DISTINTAS: entra en la zona, se aleja 0.3%, y vuelve
    al menos `sep` velas despues (1 h en 5m). Un rango pegado al nivel no cuenta."""
    try:
        n, dentro, last = 0, False, -999
        for i, x in enumerate(kl):
            en_zona = x["l"] <= nivel * (1 + tol) and x["h"] >= nivel * (1 - tol)
            if en_zona and not dentro and (i - last) >= sep:
                n += 1
                dentro = True
                last = i
            elif not en_zona and abs(x["c"] - nivel) / nivel >= salida:
                dentro = False
        return n
    except Exception:
        return 0


# Modelo logistico de "aguante" de un nivel tras 3+ toques.
# Entrenado con 394.256 velas de 5m (2023-01 a 2026-09), 3.009 eventos,
# objetivo: NO cerrar 0,5% mas alla del nivel en las siguientes 4h.
MODELO_TOQUES = {'version': 'toques-wf-1', 'target': 'hold_4h_0.5pct', 'trained_until': '2026-09-30 22:55:00+00:00', 'holdout_2026': {'auc': None, 'brier': 0.1237, 'skill': 0.0093, 'base': 0.8538, 'n': 212}, 'wf': {'folds': 11, 'muestras_oos': 7757, 'skill_medio': 0.0168, 'racha_positiva': 6, 'skill_folds': [0.0111, 0.0104, 0.0028, 0.019, 0.0304, 0.0231, -0.0055, 0.0204, 0.0348, 0.0132, 0.0251]}, 'features': ['dist', 'atr', 'ema200', 'rng', 'hourc', 'dow', 'x_atr48', 'x_atr144', 'x_atr288'], 'mean': [-0.00014471902899527983, 0.0013422890357383682, -0.00015422267700606877, 0.0015690369453809844, 0.0011800404585300068, -0.08165292068442347, 0.0013385479332434255, 0.0014126025893459204, 0.0014580719082939986], 'scale': [0.006663299240638484, 0.0009287107880874037, 0.007077131053340157, 0.0013562768488327192, 0.7156957839129136, 0.7213757356393746, 0.0007378356425407469, 0.0006942695553991874, 0.0006551650795141382], 'coef': [-0.0, 0.0, -0.0, -0.0, 0.09829794261377577, -0.19040384269895175, 0.0, -0.0, -0.2073024131403363], 'intercept': 1.5426070329136758}


def _ema_ultimo(vals, span):
    k = 2.0 / (span + 1.0)
    e = vals[0]
    for x in vals[1:]:
        e = x * k + e * (1.0 - k)
    return e


def _std_muestral(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def features_toque(kl, nivel, precio, ahora, lado):
    """Features del modelo de aguante, calculadas igual que en entrenamiento.
    `kl` son velas de 5m ya cerradas; `precio` es el precio actual."""
    try:
        n = len(kl)
        if n < 300 or nivel <= 0 or precio <= 0:
            return None
        c = [x["c"] for x in kl]
        h = [x["h"] for x in kl]
        l = [x["l"] for x in kl]
        o = [x["o"] for x in kl]
        v = [max(0.0, x["v"]) for x in kl]
        trs = []
        for i in range(1, n):
            trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
        atr = (sum(trs[-14:]) / max(1, min(14, len(trs)))) / precio
        atr48 = (sum(trs[-48:]) / max(1, min(48, len(trs)))) / precio
        atr144 = (sum(trs[-144:]) / max(1, min(144, len(trs)))) / precio
        atr288 = (sum(trs[-288:]) / max(1, min(288, len(trs)))) / precio
        gains, losses = [], []
        for i in range(1, n):
            d = c[i] - c[i - 1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        ag = sum(gains[:14]) / 14.0
        al = sum(losses[:14]) / 14.0
        for i in range(14, len(gains)):
            ag = (ag * 13.0 + gains[i]) / 14.0
            al = (al * 13.0 + losses[i]) / 14.0
        rsi = 100.0 - 100.0 / (1.0 + ag / (al + 1e-12))
        ema50 = _ema_ultimo(c, 50)
        ema200 = _ema_ultimo(c, 200)
        lv = [math.log1p(x) for x in v]
        w = lv[-96:]
        mu = sum(w) / len(w)
        volz = (lv[-1] - mu) / (_std_muestral(w) + 1e-12)
        rets = [math.log(c[i] / c[i - 1]) for i in range(1, n) if c[i - 1] > 0]
        rv12 = _std_muestral(rets[-12:])
        rv288 = _std_muestral(rets[-288:])
        # pivotes del mismo lado en las ultimas 72 velas (k=5)
        start = max(0, n - 82)
        sub = kl[start:]
        pivs = []
        for i in range(5, len(sub) - 5):
            if lado == "Soporte":
                if sub[i]["l"] <= min(sub[j]["l"] for j in range(i - 5, i + 6)):
                    pivs.append((start + i, sub[i]["l"]))
            elif sub[i]["h"] >= max(sub[j]["h"] for j in range(i - 5, i + 6)):
                pivs.append((start + i, sub[i]["h"]))
        cl72 = [(j, p) for (j, p) in pivs
                if j >= n - 72 and abs(p - nivel) / nivel <= 0.0015]
        if not cl72:
            return None
        first = cl72[0][0]
        npiv = len(cl72)
        span = (n - 1 - first) * 5.0 / 60.0
        if lado == "Soporte":
            bounce = max(h[first:n]) / nivel - 1.0
        else:
            bounce = 1.0 - min(l[first:n]) / nivel
        volpiv = (sum(v[j] for j, _ in cl72) / len(cl72)) / (sum(v[-96:]) / len(v[-96:]) + 1e-12)
        rango = h[-1] - l[-1]
        rng = rango / c[-1] if c[-1] else 0.0
        body = (c[-1] - o[-1]) / (rango + 1e-12)
        if lado == "Soporte":
            wick = (min(o[-1], c[-1]) - l[-1]) / (rango + 1e-12)
        else:
            wick = (h[-1] - max(o[-1], c[-1])) / (rango + 1e-12)
        hh = ahora.hour + ahora.minute / 60.0
        return {
            "npiv": float(npiv), "span": span, "bounce": bounce,
            "dist": (precio - nivel) / nivel, "atr": atr, "rsi": rsi,
            "ema50": precio / ema50 - 1.0 if ema50 else 0.0,
            "ema200": precio / ema200 - 1.0 if ema200 else 0.0,
            "x_atr48": atr48, "x_atr144": atr144, "x_atr288": atr288,
            "volz": volz, "volpiv": volpiv, "rng": rng, "body": body, "wick": wick,
            "rvratio": rv12 / (rv288 + 1e-12),
            "trend48": precio / c[-48] - 1.0 if n >= 48 and c[-48] else 0.0,
            "trend288": precio / c[-288] - 1.0 if n >= 288 and c[-288] else 0.0,
            "round500": 1.0 if abs(nivel / 500.0 - round(nivel / 500.0)) < 0.002 else 0.0,
            "round1000": 1.0 if abs(nivel / 1000.0 - round(nivel / 1000.0)) < 0.001 else 0.0,
            "hour": math.sin(2 * math.pi * hh / 24.0),
            "hourc": math.cos(2 * math.pi * hh / 24.0),
            "dow": math.sin(2 * math.pi * ahora.weekday() / 7.0),
            "dowc": math.cos(2 * math.pi * ahora.weekday() / 7.0),
            "side": 1.0 if lado == "Soporte" else 0.0,
        }
    except Exception:
        return None


def score_toque(f):
    """Probabilidad estimada de que el nivel aguante 4h (sin cierre 0,5% fuera)."""
    try:
        z = MODELO_TOQUES["intercept"]
        for name, mu, sd, co in zip(MODELO_TOQUES["features"], MODELO_TOQUES["mean"],
                                    MODELO_TOQUES["scale"], MODELO_TOQUES["coef"]):
            z += co * (f[name] - mu) / (sd + 1e-12)
        if z > 30:
            return 1.0
        if z < -30:
            return 0.0
        return 1.0 / (1.0 + math.exp(-z))
    except Exception:
        return None


def detectar_toques_multiples(kl, precio, ahora, est, niv=None, min_toques=3, horas=6,
                              cerca=0.003, por_hora=12):
    """Avisa cuando un nivel local se prueba varias veces seguidas.
    Es CONTEXTO, no entrada: sirve para ver defensa o desgaste del nivel.
    Si se pasa `niv`, exige que el nivel micro este cerca de la rejilla mayor
    (asi no avisa de cualquier ruido de 5m). Por defecto asume velas de 5m."""
    try:
        if not kl or not precio:
            return None
        mayores = []
        if isinstance(niv, dict):
            for _k in ("soportes", "resistencias"):
                for _x in (niv.get(_k) or []):
                    try:
                        mayores.append(float(_x["precio"]))
                    except Exception:
                        continue
        n_win = max(24, int(horas * por_hora))
        klw = kl[-n_win:]
        klp = kl[-max(2 * n_win, 144):]
        cands = []
        for nv in pivotes_micro(klp):
            p = nv["precio"]
            if nv.get("n", 1) < 3:  # nivel formado por al menos 3 pivotes
                continue
            if mayores and min(abs(p - m) / p for m in mayores) > 0.006:
                continue  # nivel micro lejos de la rejilla mayor = ruido
            if abs(precio - p) / precio > cerca:
                continue
            n = toques_en_nivel(klw, p)
            if n < min_toques:
                continue
            ult = None
            for x in reversed(klw):
                if x["l"] <= p * (1 + UMBRAL_TOQUE) and x["h"] >= p * (1 - UMBRAL_TOQUE):
                    ult = x
                    break
            if not ult:
                continue
            lado = "Soporte" if p <= precio else "Resistencia"
            # Si el ultimo toque cerro del otro lado, el nivel se rompio: no es defensa.
            if lado == "Soporte" and ult["c"] < p * (1 - UMBRAL_TOQUE):
                continue
            if lado == "Resistencia" and ult["c"] > p * (1 + UMBRAL_TOQUE):
                continue
            cands.append((n, abs(precio - p) / precio, p, lado))
        cands.sort(key=lambda z: (-z[0], z[1]))
        for n, _, p, lado in cands[:4]:
            feat = features_toque(kl, p, precio, ahora, lado)
            if not feat or feat.get("npiv", 0) < 3:
                continue
            sc = score_toque(feat)
            if sc is None:
                continue
            if not enfriar(est, f"toques:{int(p / 500) * 500}", 6, ahora):
                continue
            if sc >= 0.80:
                tier = "alto"
            elif sc >= 0.60:
                tier = "medio"
            else:
                tier = "frágil, posible ruptura"
            return (f"🧱 {lado} {fmt_miles(p)} probado {n} veces en {horas}h. "
                    f"Aguante 4h (0,5%): {sc * 100:.0f}% ({tier}). No es entrada.")
        return None
    except Exception:
        return None


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
    try:
        offset = int(offset or 0)
    except Exception:
        offset = 0
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
        res = data.get("result", []) if isinstance(data, dict) else []
        if res:
            try:
                new_off = max(new_off, int(res[-1].get("update_id", 0)) + 1)
            except Exception:
                pass
        for u in res:
            try:
                new_off = max(new_off, int(u.get("update_id", 0)) + 1)
            except Exception:
                pass
            m = u.get("message") or u.get("edited_message") or {}
            txt = (m.get("text") or "").strip()
            cid = (m.get("chat") or {}).get("id")
            if txt.startswith("/"):
                tk = txt.split()[0].split("@")[0].lower()
                msgs.append({"chat": cid, "texto": tk, "full": txt[:500],
                             "nombre": str(((m.get("from") or {}).get("first_name") or ""))[:30].replace("\n", " ")})
        return msgs, new_off
    except Exception:
        return [], offset


def responder_comando(cmd, ctx):
    """Solo responde al dueño (seguridad: verifica el chat). Devuelve (texto, dirty)."""
    chat_ok = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_ok or str((cmd or {}).get("chat")) != str(chat_ok):
        return None, False
    c = str((cmd or {}).get("texto") or "").split("@")[0].strip().lower() or "/ayuda"
    try:
        t = ctx["t"]
        dirb = ctx["dirb"]
        niv = ctx["niv"]
        fg = ctx["fg"]
        est = ctx["est"]
        ahora = ctx["ahora"]
        _rs = (niv.get("resistencias") or [])
        _ss = (niv.get("soportes") or [])
        if not _rs or not _ss:
            return ("Niveles en cálculo, prueba /precio en la próxima pasada.", False)
        res = _rs[0]
        sup = _ss[0]
    except Exception:
        return ("No entiendo el estado ahora mismo, prueba en la próxima pasada.", False)
    if c == "/precio":
        return (f"BTC ahora: {fmt_miles(t['last'])} ({t['chg']:+.2f}% 24h). "
                f"Rango del día: {fmt_miles(t['lo'])} - {fmt_miles(t['hi'])}.", False)
    if c == "/direccion":
        def _tf(x):
            return f"{x.get('tf', '?')} {x.get('tend', '?')} RSI {x.get('rsi', '?')} MACD {'+' if x.get('macd', 0) > 0 else '-'}"
        return (f"Dirección: {dirb['bias']} (confianza {dirb['confianza']}%). " +
                " | ".join(_tf(ctx[k]) for k in ("h1", "h4", "d1", "w1")) + ".", False)
    if c == "/niveles":
        return ("Soportes: " + " | ".join(fmt_miles(x['precio']) for x in niv['soportes']) +
                "\nResistencias: " + " | ".join(fmt_miles(x['precio']) for x in niv['resistencias']), False)
    if c == "/miedo":
        ff = f"{ctx['senti']['funding']:+.4f}%" if ctx['senti']['funding'] is not None else "n/d"
        tk = ctx['senti']['taker'] if ctx['senti']['taker'] is not None else "n/d"
        return (f"{fg['etiqueta']}: {fg['valor']}/100 (RSI 1D {ctx['d1']['rsi']}, funding {ff}, taker {tk}).", False)
    if c == "/noticias":
        ns = (ctx.get("notis") or [])[:3]
        if not ns:
            return ("Sin noticias relevantes ahora mismo.", False)
        base = "Top noticias:\n" + "\n".join(f"• [{n['score']}] {n['titulo']}" for n in ns)
        pr = ctx.get("pres")
        if pr:
            base += f"\nPresión: {pr['txt']}."
        return (base, False)
    if c == "/eventos":
        evs = ctx["evs"][:3]
        if not evs:
            return ("Sin eventos fuertes esta semana.", False)
        return ("Próximos eventos:\n" + "\n".join(
            f"• {e['titulo']} ({e['cuando'].strftime('%a %d %H:%M')} UTC)" + (
                f"\n  📊 {linea_estudio(est, e['titulo'])}" if linea_estudio(est, e['titulo']) else "")
            for e in evs), False)
    if c == "/precision":
        _pp = precision_plan(est)
        if _pp:
            _pa, _pb = _pp
            base = (f"Precisión (dirección del plan): ALZA {prec_str(_pa)} · "
                    f"BAJA {prec_str(_pb)}.")
        else:
            base = (f"Precisión (histórico por sesgo): ALZA {prec_str(est.get('alza', []))} · "
                    f"BAJA {prec_str(est.get('baja', []))}. Aún sin muestras de plan.")
        aut = ctx.get("aut")
        if aut:
            base += (f"\nAuto: mejor {aut['mejor'][0]} ({aut['mejor'][1]}%) · "
                     f"peor {aut['peor'][0]} ({aut['peor'][1]}%) · n={aut['n']}.")
        cal = calibrar(est)
        if cal:
            base += "\nCalib: " + ", ".join(f"{s}x{f}" for s, f in sorted(cal.items())) + "."
        tc = tabla_calibracion(est.get("eval_log", []))
        if tc:
            cub = ", ".join(f"{k}:{v[1]}%({v[0]})" for k, v in sorted(tc["cubetas"].items()))
            base += f"\nConciencia: cuando digo 40s/50s/60+ acierto {cub} · Brier {tc['brier']} (0 perfecto) · n={tc['n']}."
        return (base, False)
    if c == "/sombra":
        try:
            slog = [e for e in (est.get("eval_sombra", []) or []) if isinstance(e, dict)]
            n = len(slog)
            if not n:
                return ("Sombra: sin evaluaciones aún (mide toda señal con sesgo, sin operar).", False)
            ok = sum(1 for e in slog if float(e.get("r", 0) or 0) > 0)
            pct = round(ok / n * 100) if n else 0
            base = f"Sombra: n={n} · acierto {pct}% ({ok}/{n})."
            try:
                tc = tabla_calibracion(slog)
            except Exception:
                tc = None
            if tc and tc.get("cubetas"):
                cub = ", ".join(f"{k}:{v[1]}%({v[0]})" for k, v in sorted(tc["cubetas"].items()))
                base += f"\nPor confianza: {cub}."
            return (base, False)
        except Exception:
            return ("Sombra: sin datos válidos aún.", False)
    if c == "/evals":
        try:
            elog_all = [e for e in (est.get("eval_log", []) or []) if isinstance(e, dict)]
            elog_plan = [e for e in elog_all if e.get("metodo") == "plan"]
            elog = elog_plan or elog_all
            n = len(elog)
            if not n:
                return ("Evals: sin evaluaciones aún.", False)
            etiqueta = "plan" if elog_plan else "histórico por sesgo"
            ok = sum(1 for e in elog if float(e.get("r", 0) or 0) > 0)
            pct = round(ok / n * 100) if n else 0
            base = f"Evals ({etiqueta}): n={n} · acierto {pct}% ({ok}/{n})."
            try:
                tc = tabla_calibracion(elog)
            except Exception:
                tc = None
            if tc and tc.get("cubetas"):
                cub = ", ".join(f"{k}:{v[1]}%({v[0]})" for k, v in sorted(tc["cubetas"].items()))
                base += f"\nPor confianza: {cub} · Brier {tc['brier']} (0 perfecto)."
            try:
                glog = [e for e in (est.get("eval_gate", []) or []) if isinstance(e, dict)]
                if glog:
                    gok = sum(1 for e in glog if float(e.get("r", 0) or 0) > 0)
                    gpct = round(gok / len(glog) * 100) if glog else 0
                    base += (f"\nGate (silenciadas, contrafactual): {gok}/{len(glog)} = {gpct}%."
                             " No se enviaron; solo auditan el filtro.")
            except Exception:
                pass
            base += "\nDesde este fix: direccion real del plan. Antes se media el sesgo."
            return (base, False)
        except Exception:
            return ("Evals: sin datos válidos aún.", False)
    if c == "/manos":
        sm = ctx.get("smart")
        if not sm:
            return ("Sin datos de flujos ahora.", False)
        try:
            return ((f"Instituciones {sm.get('inst', '?')}/100 · Minoristas {sm.get('ret', '?')}/100.\n" + str(sm.get("veredicto", "sin veredicto"))), False)
        except Exception:
            return ("Sin datos de flujos ahora.", False)
    if c == "/calidad":
        g = ctx.get("grade", "?")
        rg = ctx.get("regimen", "?")
        bl = " (blackout: sin señales nuevas)" if ctx.get("bloqueo") else ""
        return (f"Calidad: {g} · régimen {rg}{bl}. Opera solo las A.", False)
    if c in ("/motor", "/motor4h"):
        m = ctx.get("motor") or cargar_motor_nuevo()
        if not m:
            return ("Motor 4h: sin lectura fresca. El pipeline corre cada 15 min; revisa /motor.html.", False)
        base = f"Motor 4h: {m.get('action', '?')} · sesgo {m.get('bias') or '?'} · {m.get('age_min')} min."
        if m.get("trigger"):
            base += f"\nTrigger: {m['trigger']}"
        if m.get("invalidation"):
            base += f"\nInvalida: {m['invalidation']}"
        base += "\nEs contexto, no una orden: el motor no ejecuta."
        return (base, False)
    if c == "/detalle":
        return ("Te mando el parte completo ahora.", False)
    if c == "/alerta":
        parts = cmd.get("full", "").split()
        if len(parts) != 2:
            return ("Uso: /alerta 85000 (te aviso al tocarlo).", False)
        try:
            px = float(parts[1])
        except Exception:
            return ("Precio inválido.", False)
        if px <= 0:
            return ("Precio debe ser > 0.", False)
        if not (1000 <= px <= 1000000):
            return ("Precio fuera de rango sensato (1.000–1.000.000).", False)
        d = "sube" if px >= t["last"] else "baja"
        al = est.get("mis_alertas") or []
        if len(al) >= 20:
            return ("Tienes 20 alertas (máximo). Borra con /borrar.", False)
        al.append({"precio": px, "dir": d})
        est["mis_alertas"] = al
        verbo = "suba a" if d == "sube" else "baje a"
        return (f"Alerta creada: te aviso cuando BTC {verbo} {fmt_miles(px)}.", True)
    if c == "/alertas":
        al = est.get("mis_alertas") or []
        limpias = [a for a in al if isinstance(a, dict) and a.get("precio") and a.get("dir")]
        if not limpias:
            if al:
                return ("Tus alertas están corruptas. Usa /borrar y crea de nuevo.", False)
            return ("Sin alertas de precio. Crea con /alerta 85000.", False)
        try:
            txt = "\n".join(f"• {fmt_miles(float(a['precio']))} ({a['dir']})" for a in limpias)
        except Exception:
            return ("Tus alertas están corruptas. Usa /borrar y crea de nuevo.", False)
        return (("Tus alertas:\n" + txt), False)
    if c == "/borrar":
        est["mis_alertas"] = []
        return ("Alertas de precio borradas.", True)
    if c == "/opere":
        parts = cmd.get("full", "").split()
        if len(parts) != 5:
            return ("Uso: /opere LONG|SHORT entrada stop tp (ej: /opere LONG 83000 82500 84000).", False)
        d = parts[1].upper()
        if d not in ("LONG", "SHORT"):
            return ("Dirección: LONG o SHORT.", False)
        try:
            e, s, tp = float(parts[2]), float(parts[3]), float(parts[4])
        except Exception:
            return ("Números inválidos.", False)
        if not (e > 0 and s > 0 and tp > 0 and e != s):
            return ("Revisa precios (stop distinto de entrada).", False)
        if d == "LONG" and not (s < e):
            return ("En LONG el stop va bajo la entrada.", False)
        if d == "SHORT" and not (s > e):
            return ("En SHORT el stop va sobre la entrada.", False)
        ops = est.get("ops") or []
        if len(ops) >= MAX_OPS:
            return ("Tienes 20 operaciones abiertas (máximo). Cierra con /cerrar.", False)
        ops.append({"dir": d, "entrada": e, "stop": s, "tp": tp, "t": ahora.isoformat()})
        est["ops"] = ops
        return ((f"Registrada: {d} {fmt_miles(e)} (SL {fmt_miles(s)} / TP {fmt_miles(tp)}). "
                 "Te aviso al cerrar."), True)
    if c == "/voy":
        ops = est.get("ops") or []
        if not ops:
            return ("Sin operaciones abiertas.", False)
        lines = []
        for o in (ops or []):
            try:
                e, s = float(o["entrada"]), float(o["stop"])
                riesgo = abs(e - s) or 1
                rr = (t["last"] - e) / riesgo if o.get("dir") == "LONG" else (e - t["last"]) / riesgo
                lines.append(f"{o.get('dir', '?')} {fmt_miles(e)}: {rr:+.1f}R ahora (SL {fmt_miles(s)} / TP {fmt_miles(float(o.get('tp', s)))})")
            except Exception:
                continue
        return ("\n".join(lines) or "Sin operaciones válidas.", False)
    if c == "/diario":
        j = est.get("journal", [])
        if not j:
            return ("Diario vacío: registra con /opere LONG entrada stop tp.", False)
        w = sum(1 for x in j if x.get("r", 0) > 0)
        tr = round(sum(x.get("r", 0) for x in j), 1)
        return (f"Diario: {len(j)} ops · ganadas {w} ({round(w / len(j) * 100)}%) · total {tr:+.1f}R.", False)
    if c == "/papel":
        try:
            banco = float(est.get("banco", PAPER_BANCO))
        except Exception:
            banco = float(PAPER_BANCO)
        j = est.get("paper_cerradas", [])
        ops = est.get("paper_abiertas", [])
        if not j and not ops:
            return (f"Papel XLX: banco {PAPER_BANCO:.0f} USDT, lev {PAPER_LEV}x, sin operaciones aún. Abro solo con señales ALZA/BAJA de 35%+.", False)
        w = sum(1 for x in j if x.get("pnl", 0) > 0)
        wr = f"{round(w / len(j) * 100)}% ({w}/{len(j)})" if j else "s/d"
        tr = round(sum(x.get("r", 0) for x in j), 1) if j else 0
        txt = (f"Papel XLX: banco {fmt_miles(banco)} USDT ({banco - PAPER_BANCO:+.0f}) · lev {PAPER_LEV}x · cerradas {len(j)} · ganadas {wr} · total {tr:+.1f}R.")
        if racha_perdidas(est) >= 3:
            txt += " Penalizado: arriesga 0.5% (3+ pérdidas seguidas)."
        if ops:
            txt += "\nAbiertas:\n" + "\n".join(
                f"• {o['dir']} {fmt_miles(o['entrada'])} (SL {fmt_miles(o['stop'])} / TP {fmt_miles(o['tp'])} / LIQ {fmt_miles(o.get('liq', 0))})" for o in ops)
        return (txt, False)
    if c == "/cerrar":
        ops = est.get("ops", [])
        if not ops:
            return ("No hay operaciones abiertas.", False)
        j = est.get("journal", [])
        outs = []
        for o in ops:
            e, s = o["entrada"], o["stop"]
            riesgo = abs(e - s) or 1
            rr = (t["last"] - e) / riesgo if o["dir"] == "LONG" else (e - t["last"]) / riesgo
            j.append({"dir": o["dir"], "res": "MANUAL", "r": round(rr, 2), "t": ahora.isoformat()})
            outs.append(f"{o['dir']} cerrada en {fmt_miles(t['last'])} ({rr:+.1f}R)")
        est["ops"] = []
        est["journal"] = j[-50:]
        return ("\n".join(outs), True)
    if c == "/simula":
        parts = cmd.get("full", "").split()
        sims = est.get("sim_abiertas", [])
        if len(parts) == 1:
            cerr = est.get("sim_cerradas", [])
            w = sum(1 for x in cerr if x.get("r", 0) > 0)
            base = f"Simulador: {len(sims)} abiertas · {len(cerr)} cerradas ({w} ganadas)."
            if sims:
                base += "\n" + "\n".join(
                    f"• {o['dir']} {fmt_miles(o['entrada'])} (SL {fmt_miles(o['stop'])} / TP {fmt_miles(o['tp'])})" for o in sims[-5:])
            base += "\nUso: /simula LONG|SHORT entrada [stop tp] (sin dinero, solo aprendizaje)."
            return (base, False)
        if len(parts) not in (3, 5) or parts[1].upper() not in ("LONG", "SHORT"):
            return ("Uso: /simula LONG 83000 o /simula SHORT 83000 82500 84000.", False)
        if len(sims) >= 5:
            return ("Tienes 5 simuladas abiertas (máximo). Espera cierres.", False)
        d = parts[1].upper()
        try:
            e = float(parts[2])
            if len(parts) == 5:
                s, tp = float(parts[3]), float(parts[4])
            elif d == "LONG":
                s = niv["soportes"][0]["precio"]
                tp = e + 2 * (e - s)
            else:
                s = niv["resistencias"][0]["precio"]
                tp = e - 2 * (s - e)
        except Exception:
            return ("Números inválidos.", False)
        if not (e > 0 and s > 0 and tp > 0 and e != s):
            return ("Revisa los precios (stop distinto de entrada).", False)
        if d == "LONG" and not (s < e):
            return ("En LONG el stop va bajo la entrada.", False)
        if d == "SHORT" and not (s > e):
            return ("En SHORT el stop va sobre la entrada.", False)
        riesgo = abs(e - s) or 1
        rr = abs(tp - e) / riesgo
        sims.append({"dir": d, "entrada": e, "stop": s, "tp": tp, "t": ahora.isoformat()})
        est["sim_abiertas"] = sims
        return ((f"🔬 Simulada: {d} {fmt_miles(e)} (SL {fmt_miles(s)} / TP {fmt_miles(tp)}, {rr:.1f}R). "
                 "Sin dinero, solo aprendizaje. Te aviso al cerrar."), True)
    _nom = str((cmd or {}).get("nombre") or "").strip().replace("\n", " ")[:30]
    hola = f" Hola {_nom}." if _nom else " Hola."
    return ((hola + " Te respondo en cada pasada (máx ~30 min).\n"
             "Comandos: /precio /direccion /niveles /miedo /noticias /eventos /motor /precision /sombra /evals /manos "
             "/alerta /alertas /borrar /opere /voy /diario /cerrar /calidad /detalle /papel /simula"), False)


def racha_perdidas(est):
    """Perdidas seguidas en papel (para la penalizacion anti-tilt)."""
    n = 0
    for c in reversed(est.get("paper_cerradas", [])):
        if c.get("pnl", 0) < 0:
            n += 1
        else:
            break
    return n


def perdon_bloqueo(est, ahora):
    """Perdon por bloqueo: 3 dias seguidos con senal valida pero freno de pico
    -> pico=banco (castigo real, sin deadlock). True si perdono."""
    try:
        bp = est.get("bloq_pico") or {}
        hoy = ahora.strftime("%Y-%m-%d")
        ayer = (ahora - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        d = int(bp.get("dias", 0) or 0)
        if bp.get("fecha") == ayer:
            d += 1
        elif bp.get("fecha") != hoy:
            d = 1
        if d >= 3:
            est["banco_pico"] = float(est.get("banco", PAPER_BANCO))
            est["bloq_pico"] = {"fecha": hoy, "dias": 0}
            return True
        est["bloq_pico"] = {"fecha": hoy, "dias": d}
        return False
    except Exception:
        return False


def puede_papel(est, bias, conf, ahora):
    """El papel opera señales B (35%+): aprende sin spamear. Dedup 4h por direccion."""
    if bias not in ("ALZA", "BAJA") or conf < UMBRAL_PAPEL:
        return False
    pu = est.get("paper_ult") or {}
    try:
        return not (pu.get("dir") == bias and (ahora - datetime.datetime.fromisoformat(pu.get("t", ""))).total_seconds() / 3600 < DEDUP_HORAS)
    except Exception:
        return True


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
        base = "temporada BTC 🟠" if b >= 55 else ("zona mixta ⚪" if b >= 48 else "aires de altseason 🟣")
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
    "rsi=0": 0.456, "rsi=1": 0.523, "rsi=2": 0.586,
    "adx=0": 0.418, "adx=1": 0.573,
    "er=0": 0.562, "er=1": 0.5, "er=2": 0.501,
    "ses=Asia": 0.473, "ses=Londres": 0.617, "ses=NY": 0.533,
    "h1t=ALCISTA": 0.558, "h1t=BAJISTA": 0.437, "h1t=lateral": 0.56,
    "zt=0": 0.471, "zt=1": 0.583, "zt=2": 0.538}


def prob_reaccion(feats):
    """Puntaje 0..1 de reaccion probable (media de tablas). None si falla."""
    try:
        vals = [REAC_TAB.get(k + "=" + str((feats or {}).get(k)), REAC_BASE)
                for k in ("rsi", "adx", "er", "ses", "h1t", "zt")]
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
    trs = []
    for i in range(1, len(kl)):
        try:
            h, l, pc = float(kl[i]["h"]), float(kl[i]["l"]), float(kl[i - 1]["c"])
        except Exception:
            trs.append(None)
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if i >= n and all(x is not None for x in trs[i - n:i]):
            atr[i] = sum(trs[i - n:i]) / n
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
                zonas.append({"dir": "ALZA", "lo": lo, "hi": hi, "i": i,
                              "size": hi - lo, "atr": a})
        elif h2 < l0:  # FVG bajista
            lo, hi = h2, l0
            if hi - lo >= min_atr * a:
                zonas.append({"dir": "BAJA", "lo": lo, "hi": hi, "i": i,
                              "size": hi - lo, "atr": a})
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
    out = []
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
    return {"h1": fvgs_cercanos(kl_h1, precio),
            "h4": fvgs_cercanos(kl_h4, precio)}


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
                    cerca.append(f"FVG {_etq} {fmt_miles(z['lo'])}-{fmt_miles(z['hi'])} ({d:+.1f}%)")
        partes = dentro + cerca
        if not partes:
            return ""
        return "🧲 " + " · ".join(partes[:max_partes])
    except Exception:
        return ""


def kelly_half(rs, r_mult=2.0):
    """Half-Kelly dormido: sin 10+ cerradas devuelve None (riesgo base 1%).
    Acotado [0.25%, 2%] para no volverse loco en rachas."""
    try:
        rs = [float(x) for x in (rs or [])]
        if len(rs) < 10:
            return None
        pw = sum(1 for x in rs if x > 0) / len(rs)
        k = (pw - (1 - pw) / r_mult) / 2
        return max(0.0025, min(0.02, k))
    except Exception:
        return None


def sharpe(rs):
    """Sharpe por operacion (Rf=0): media / desviacion. None con <5 datos."""
    try:
        import math
        rs = [float(x) for x in (rs or [])]
        if len(rs) < 5:
            return None
        m = sum(rs) / len(rs)
        var = sum((x - m) ** 2 for x in rs) / len(rs)
        if var <= 0:
            return None
        return round(m / math.sqrt(var), 2)
    except Exception:
        return None


def abrir_papel(est, dirb, niv, precio, ahora):
    """Abre papel virtual XLX con frenos institucionales (devuelve la posicion o None):
    - drawdown -10% desde maximo: frena todo
    - -3% en el dia: frena el dia
    - 3+ perdidas seguidas: riesgo 0.5% en vez de 1%
    - SL mas alla de la liquidacion estimada (60x): no abre (te liquidarian antes)"""
    if dirb["bias"] not in ("ALZA", "BAJA"):
        return None
    try:
        banco = float(est.get("banco", PAPER_BANCO))
    except Exception:
        return None
    if banco <= 20:
        # REBORN medido: las abiertas se liquidan a `precio` y se registran
        # en paper_cerradas (res=REBORN) antes de resetear. Antes se vaciaban
        # sin rastro: perdida silenciosa de PnL y de historia.
        try:
            _px_rb = float(precio)
        except Exception:
            _px_rb = None
        if _px_rb and _px_rb > 0:
            try:
                _cerr = est.get("paper_cerradas", [])
                for _o in (est.get("paper_abiertas") or []):
                    try:
                        _ent = float(_o.get("entrada"))
                        _tam = float(_o.get("tam"))
                        _ri = float(_o.get("riesgo") or 0)
                        if _o.get("dir") == "SHORT":
                            _pnl = round((_ent - _px_rb) * _tam, 2)
                        else:
                            _pnl = round((_px_rb - _ent) * _tam, 2)
                        _cerr.append({"dir": _o.get("dir", "?"), "res": "REBORN",
                                       "pnl": _pnl,
                                       "r": round(_pnl / _ri, 2) if _ri else 0,
                                       "t": ahora.isoformat()})
                    except Exception:
                        continue
                est["paper_cerradas"] = _cerr[-100:]
            except Exception:
                pass
        banco = PAPER_BANCO
        est["banco"] = banco
        est["banco_pico"] = banco
        est["paper_dia"] = {"fecha": ahora.strftime("%Y-%m-%d"), "pnl": 0.0}
        est["paper_abiertas"] = []
        try:
            est.pop("paper_ult", None)
        except Exception:
            pass
    pico = float(est.get("banco_pico", banco))
    if banco > pico:
        pico = banco
        est["banco_pico"] = pico
    if pico > 0 and (pico - banco) / pico >= 0.10:
        if perdon_bloqueo(est, ahora):
            pico = banco
        else:
            return None
    hoy = ahora.strftime("%Y-%m-%d")
    pd = est.get("paper_dia") or {}
    if pd.get("fecha") != hoy:
        pd = {"fecha": hoy, "pnl": 0.0}
        est["paper_dia"] = pd
    if pd.get("pnl", 0) <= -0.03 * banco:
        return None
    if racha_perdidas(est) >= 3:
        riesgo_pct = 0.005
    else:
        k = kelly_half([c.get("r", 0) for c in est.get("paper_cerradas", [])])
        riesgo_pct = k if k is not None else PAPER_RIESGO
    if dirb["bias"] == "ALZA":
        stop = niv["soportes"][0]["precio"]
        tp = niv["resistencias"][0]["precio"]
        if tp <= precio:
            tp = precio + (precio - stop) * 2
        dire = "LONG"
    else:
        stop = niv["resistencias"][0]["precio"]
        tp = niv["soportes"][0]["precio"]
        if tp >= precio:
            tp = precio - (stop - precio) * 2
        dire = "SHORT"
    dist_stop = abs(precio - stop)
    if dist_stop <= 0:
        return None
    liq = round(precio * (1 - 1.0 / PAPER_LEV)) if dire == "LONG" else round(precio * (1 + 1.0 / PAPER_LEV))
    if dist_stop > abs(precio - liq):
        return None
    if dist_stop > 0.5 * abs(precio - liq):
        return None
    entrada = round(precio)
    dist_stop = abs(entrada - stop)
    if dist_stop <= 0:
        return None
    liq = round(entrada * (1 - 1.0 / PAPER_LEV)) if dire == "LONG" else round(entrada * (1 + 1.0 / PAPER_LEV))
    tam = (banco * riesgo_pct) / dist_stop
    try:
        if (tam * entrada) / PAPER_LEV > 10 * (dist_stop * tam):
            return None  # cap LIQ real: el LIQ de hoy pago 25.7x el riesgo; maximo 10x
    except Exception:
        return None
    pos = {"dir": dire, "entrada": entrada, "stop": stop, "tp": round(tp),
           "tam": tam, "riesgo": round(dist_stop * tam, 2), "lev": PAPER_LEV,
           "liq": liq, "t": ahora.isoformat()}
    if len(est.get("paper_abiertas", []) or []) >= MAX_PAPER_ABIERTAS:
        return None
    est["paper_abiertas"] = est.get("paper_abiertas", []) + [pos]
    try:
        est.pop("bloq_pico", None)
    except Exception:
        pass
    return pos


def cierre_papel(o, ref_h, ref_l, last):
    """Cierre de papel XLX: la LIQUIDACION manda sobre SL/TP.
    `ref_h`/`ref_l` son el rango de la última vela 1H CERRADA. Van como None
    cuando esa vela terminó ANTES de abrir la posición (no se puede cerrar una
    operación con el rango de una hora anterior a su entrada: daba SL/TP falsos).
    Devuelve (px, donde, pnl) o None si sigue abierta."""
    try:
        lev = float(o.get("lev") or PAPER_LEV)
        ent, tam = float(o["entrada"]), float(o["tam"])
        liq = float(o.get("liq") or (ent * (1 - 1.0 / lev) if o["dir"] == "LONG"
                                     else ent * (1 + 1.0 / lev)))
        if o["dir"] == "LONG":
            if (ref_l is not None and ref_l <= liq) or last <= liq:
                return liq, "LIQ", round(-(tam * ent) / lev, 2)
            if (ref_l is not None and ref_l <= o["stop"]) or last <= o["stop"]:
                return float(o["stop"]), "SL", round((float(o["stop"]) - ent) * tam, 2)
            if (ref_h is not None and ref_h >= o["tp"]) or last >= o["tp"]:
                return float(o["tp"]), "TP", round((float(o["tp"]) - ent) * tam, 2)
        else:
            if (ref_h is not None and ref_h >= liq) or last >= liq:
                return liq, "LIQ", round(-(tam * ent) / lev, 2)
            if (ref_h is not None and ref_h >= o["stop"]) or last >= o["stop"]:
                return float(o["stop"]), "SL", round((ent - float(o["stop"])) * tam, 2)
            if (ref_l is not None and ref_l <= o["tp"]) or last <= o["tp"]:
                return float(o["tp"]), "TP", round((ent - float(o["tp"])) * tam, 2)
        return None
    except Exception:
        return None


def ref_rango(kl_h1, t_iso):
    """Rango (h, l) de la última vela 1H cerrada, SOLO si esa vela empezó en/después
    de la entrada `t_iso`. Si la vela es anterior a la operación devuelve (None, None):
    así no se cierra una posición con el rango de una hora previa a su apertura."""
    try:
        if not kl_h1 or len(kl_h1) < 2:
            return None, None
        v = kl_h1[-2]
        if not isinstance(v, dict):
            return None, None
        vt = v.get("t")
        if t_iso and vt is not None:
            try:
                if vt < datetime.datetime.fromisoformat(t_iso):
                    return None, None
            except Exception:
                pass
        h = v.get("h")
        l = v.get("l")
        if h is None or l is None:
            return None, None
        return h, l
    except Exception:
        return None, None


def journal_check(ops, kl_h1, last):
    """Revisa operaciones abiertas con la ultima vela 1H cerrada + ticker.
    Devuelve (abiertas, cierres[{txt, r, dir, res}])."""
    msgs = []
    abiertas = []
    for o in ops:
        try:
            ref_h, ref_l = ref_rango(kl_h1, o.get("t"))
            if ref_h is None:
                ref_h = ref_l = last
            d, e, s, tp = o["dir"], o["entrada"], o["stop"], o["tp"]
            cerrada = None
            if d == "LONG":
                if ref_l <= s or last <= s:
                    cerrada = (s, "SL")
                elif ref_h >= tp or last >= tp:
                    cerrada = (tp, "TP")
            else:
                if ref_h >= s or last >= s:
                    cerrada = (s, "SL")
                elif ref_l <= tp or last <= tp:
                    cerrada = (tp, "TP")
            if cerrada:
                px, donde = cerrada
                riesgo = abs(e - s) or 1
                r = (px - e) / riesgo if d == "LONG" else (e - px) / riesgo
                msgs.append({"txt": f"Tu {d} {fmt_miles(e)} cerró en {donde} {fmt_miles(px)} ({r:+.1f}R)",
                             "r": round(r, 2), "dir": d, "res": donde})
            else:
                abiertas.append(o)
        except Exception:
            abiertas.append(o)  # corrupta pero visible: nunca se pierde en silencio
            continue
    return abiertas, msgs


def yahoo_cierres(sym):
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
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
        req = urllib.request.Request("https://api.exchange.coinbase.com/products/BTC-USD/ticker",
                                     headers={"User-Agent": "vigilante-cloud/3.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            cb = float(json.load(r)["price"])
        return round((cb - last) / last * 100, 3) if last else None
    except Exception:
        return None


def coinbase_analisis(last, vol_bin):
    """Coinbase (puerta institucional USA): premium vs Binance, peso de su
    volumen y desbalance del libro (muros). Todo gratis, sin llaves."""
    out = {"prem": None, "vol_share": None, "imb": None}
    try:
        tk = json.load(urllib.request.urlopen(urllib.request.Request(
            "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
            headers={"User-Agent": "vigilante-cloud/3.0"}), timeout=10))
        cb = float(tk["price"])
        out["prem"] = round((cb - last) / last * 100, 3) if last else None
        cv = float(tk.get("volume", 0) or 0)
        if vol_bin and vol_bin > 0:
            out["vol_share"] = round(cv / vol_bin * 100, 1)
        bk = json.load(urllib.request.urlopen(urllib.request.Request(
            "https://api.exchange.coinbase.com/products/BTC-USD/book?level=2",
            headers={"User-Agent": "vigilante-cloud/3.0"}), timeout=10))
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
            if estricto and not (c < o and pc is not None and pc >= sup and d >= UMBRAL_RUPTURA_MIN):
                return None
            return f"ruptura BAJISTA confirmada bajo {fmt_miles(sup)} (cierre 1H {hh} en {fmt_miles(c)}, {d:.2f}% debajo)"
        if res and c > res:
            d = (c - res) / res * 100
            if estricto and not (c > o and pc is not None and pc <= res and d >= UMBRAL_RUPTURA_MIN):
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
    if (any(c["h"] > hi * (1 + MIN_SWEEP) for c in ult3)
            and last < hi and abs(last - hi) / hi <= 0.004):
        extra = f" (×{n_hi})" if n_hi >= 3 else ""
        return {"lado": "max", "nivel": hi,
                "extremo": max(c["h"] for c in ult3), "cluster": n_hi,
                "texto": f"barrido sobre máximos {fmt_miles(hi)}{extra} con devolución (trampa para compradores)"}
    if (any(c["l"] < lo * (1 - MIN_SWEEP) for c in ult3)
            and last > lo and abs(last - lo) / lo <= 0.004):
        extra = f" (×{n_lo})" if n_lo >= 3 else ""
        return {"lado": "min", "nivel": lo,
                "extremo": min(c["l"] for c in ult3), "cluster": n_lo,
                "texto": f"barrido bajo mínimos {fmt_miles(lo)}{extra} con devolución (trampa para vendedores)"}
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
                if zp["precio"] > last and h1.get("tend") == "ALCISTA" and (
                        (er is not None and er >= 0.4) or rsi >= 60):
                    adv = " Va contra momentum 1H: tamaño pequeño o espera."
                elif zp["precio"] <= last and h1.get("tend") == "BAJISTA" and (
                        (er is not None and er >= 0.4) or rsi <= 40):
                    adv = " Va contra momentum 1H: tamaño pequeño o espera."
        except Exception:
            pass
        rc = ""
        try:
            if isinstance(h1, dict) and isinstance(a4, dict) and hora is not None:
                rsi = h1.get("rsi", 50)
                er = h1.get("er")
                f = {"rsi": 0 if rsi < 40 else (1 if rsi < 60 else 2),
                     "adx": 1 if (a4.get("adx", 0) or 0) >= 20 else 0,
                     "er": 0 if (er if er is not None else 0.2) < 0.15 else (1 if er < 0.4 else 2),
                     "ses": sesion_bucket(hora),
                     "h1t": h1.get("tend", "?"),
                     "zt": 0 if abs(h1.get("z") or 0) < 1.0 else (1 if abs(h1.get("z") or 0) < 2.0 else 2)}
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
            inv = (sops[0]["precio"] if sops else zp["precio"])
            return (f"Zona de referencia: a {dist * 100:.1f}% de {fmt_miles(zp['precio'])} "
                    f"({razones}) → 🛡 PISO: estás encima; si cae hasta ahí puede devolver hacia arriba. "
                    f"Se anula SOLO si 1H cierra bajo {fmt_miles(inv)}.{ctx}{adv}{rc}"
                    f" Zona de referencia, no una entrada.", str(zp["precio"]))
        inv = (ress[0]["precio"] if ress else zp["precio"])
        return (f"Zona de referencia: a {dist * 100:.1f}% de {fmt_miles(zp['precio'])} "
                f"({razones}) → 🧱 TECHO: estás debajo; si sube hasta ahí puede devolver hacia abajo. "
                f"Se anula SOLO si 1H cierra sobre {fmt_miles(inv)}.{ctx}{adv}{rc}"
                f" Zona de referencia, no una entrada.", str(zp["precio"]))
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
    zonas = []
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
    return {"arriba": arriba, "abajo": abajo,
            "iman": {"lado": lado, "pct": round(100 * (tb if lado == "abajo" else ta) / tot)}}


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
                    pg2 = fetch(base + "/aggTrades?symbol=BTCUSDT&limit=1000&fromId=%d"
                                % max(0, min(viejos) - 1000), tries=1)
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
    return {"nb": nb, "ns": ns, "buys": round(buys, 1), "sells": round(sells, 1),
            "big": round(big, 1), "txt": ver}


def imanes(last):
    """Imanes de precio: strikes con mas Open Interest en opciones Deribit
    (gratis) + ratio put/call."""
    try:
        req = urllib.request.Request(
            "https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option",
            headers={"User-Agent": "vigilante-cloud/3.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        oi = {}
        for ins in data.get("result", []):
            parts = (ins.get("instrument_name") or "").split("-")
            if len(parts) != 4:
                continue
            try:
                strike = float(parts[2])
            except Exception:
                continue
            o = oi.setdefault(strike, {"C": 0.0, "P": 0.0})
            if parts[3] in ("C", "P"):
                o[parts[3]] += float(ins.get("open_interest", 0) or 0)
        if not oi:
            return None
        calls = sum(v["C"] for v in oi.values())
        puts = sum(v["P"] for v in oi.values())
        top = sorted(oi.items(), key=lambda kv: kv[1]["C"] + kv[1]["P"], reverse=True)[:3]
        niveles = [{"strike": int(s), "oi": round(v["C"] + v["P"], 1)} for s, v in top]
        arriba = sorted(s for s in oi if s > last)
        abajo = sorted((s for s in oi if s < last), reverse=True)
        return {"top": niveles,
                "pc": round(puts / calls, 2) if calls else None,
                "up": int(arriba[0]) if arriba else None,
                "down": int(abajo[0]) if abajo else None}
    except Exception:
        return None


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


def sesion_bucket(hora):
    if 0 <= hora < 8:
        return "Asia"
    if 8 <= hora < 13:
        return "Londres"
    if 13 <= hora < 21:
        return "NY"
    return "noche"


def etiquetar_senal(senti, hora, dcvd):
    """Tags solo-medición para validar señales en papel (funding/OI/CVD/sesión).
    Puro, sin red, NO decide nada: solo etiqueta para futuro PF por régimen."""
    try:
        s = senti if isinstance(senti, dict) else {}
        return {"funding": s.get("funding"), "taker": s.get("taker"),
                "sesion": sesion_bucket(hora) if isinstance(hora, int) else "?",
                "cvd_div": dcvd if isinstance(dcvd, str) else ("sí" if dcvd else "no")}
    except Exception:
        return {"funding": None, "taker": None, "sesion": "?", "cvd_div": "no"}


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


DIRECCIONES_MEDIBLES = ("fuerte", "cambio", "toque", "ruptura", "estructura", "mecha", "liquidez")


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


def scoreboard(eval_log, min_n=1, solo_plan=False):
    """Acierto REAL por tipo de alerta, medido en vivo (eval_log).
    Devuelve filas (tipo, n, aciertos, pct), mejor primero. Sin promesas.
    `solo_plan=True` excluye el histórico viejo, que medía sesgo y no plan."""
    acc = {}
    for e in (eval_log or []):
        if not isinstance(e, dict):
            continue
        if solo_plan and e.get("metodo") != "plan":
            continue
        t = e.get("tipo") or "?"
        if t in ("?", "otro"):
            continue
        n, h = acc.get(t, (0, 0))
        acc[t] = (n + 1, h + (1 if e.get("r") else 0))
    rows = [(t, n, h, 100.0 * h / n) for t, (n, h) in acc.items() if n >= min_n]
    rows.sort(key=lambda x: (-x[3], -x[1]))
    return rows


def texto_scoreboard(eval_log, min_n=5, max_filas=6, solo_plan=False):
    """Linea(s) de scoreboard para Telegram. Vacío si no hay muestra."""
    rows = scoreboard(eval_log, min_n=min_n, solo_plan=solo_plan)
    if not rows:
        return ""
    partes = [f"{t} {h}/{n} ({p:.0f}%)" for t, n, h, p in rows[:max_filas]]
    total_n = sum(r[1] for r in rows)
    total_h = sum(r[2] for r in rows)
    cab = f"📊 Medido en vivo ({total_h}/{total_n} = {100.0*total_h/total_n:.0f}%)"
    return cab + "\n· " + "\n· ".join(partes)


def auto_stats(eval_log):
    """Auto-aprendizaje: en que sesion rinden mejor las senales (min 10 evaluadas)."""
    if len(eval_log) < 10:
        return None
    buckets = {}
    for e in eval_log:
        try:
            hh = datetime.datetime.fromisoformat(e["t"]).hour
        except Exception:
            continue
        buckets.setdefault(sesion_bucket(hh), []).append(e.get("r", 0))
    res = {b: (round(sum(v) / len(v) * 100), len(v)) for b, v in buckets.items() if len(v) >= 3}
    if not res:
        return None
    mejor = max(res, key=lambda b: res[b][0])
    peor = min(res, key=lambda b: res[b][0])
    return {"mejor": (mejor, res[mejor][0]), "peor": (peor, res[peor][0]), "n": len(eval_log)}


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


DIR_BULL = ("inflow", "inflows", "buy", "buys", "bought", "record", "demand", "adopt",
            "approval", "approve", "accumulat", "breakout", "rate cut", "cuts rates")
DIR_BEAR = ("outflow", "outflows", "sell", "sells", "sold", "lawsuit", "ban", "hack",
            "crash", "hike", "crackdown", "fraud", "charged", "fine", "bankrupt")


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


def acuerdo_tecnica(bias, valor):
    if abs(valor) < 25:
        return "noticias neutras: manda la técnica"
    if (bias == "ALZA") == (valor > 0):
        return f"viento a favor de la técnica ({bias})"
    return f"VIENTO EN CONTRA: técnica {bias} vs noticias"


def num_txt(x):
    if x is None:
        return None
    m = re.search(r'-?\d+\.?\d*', str(x).replace(',', ''))
    return float(m.group()) if m else None


def linea_escenario(e):
    """Escenario honesto para eventos con pronostico: que pasa si sale alto/bajo."""
    f = num_txt(e.get("forecast"))
    p = num_txt(e.get("previous"))
    if f is None or p is None:
        return ""
    t = e["titulo"].lower()
    base = f"escenario (esp {e['forecast']} vs prev {e['previous']})"
    if re.search(r'cpi|ppi|pce|nfp|non-farm|nonfarm|payroll|unemployment|jobless|fomc|rate|interest', t):
        return base + ": ALTO = baja | BAJO = sube"
    return base + ": la sorpresa manda la dirección"


def calibrar(est):
    """Auto-calibracion honesta: factor por sesion segun acierto medido.
    >=60% -> 0.9 (mas sensible), <=40% -> 1.15 (mas exigente), si no 1.0.
    Requiere 10+ evaluadas en la sesion. Acotado [0.7, 1.4] (nunca loco).
    Semilla NEUTRA a propósito: el replay 8m sugería NY/Londres sensibles y noche
    exigente, pero el replay 2 años lo contradijo (Londres 52.8%→32.8%, Asia 36.8%→40.5%).
    Las sesiones no son estables entre periodos: sin sesgo hasta que los datos vivos
    (10+ evaluadas) decidan. Ver HOJA_DE_RUTA entrenamiento 3."""
    fac = dict(SEMILLA_SESION)
    log = est.get("eval_log", [])
    if len(log) < 10:
        return fac
    buckets = {}
    for e in log[-60:]:
        try:
            hh = datetime.datetime.fromisoformat(e["t"]).hour
        except Exception:
            continue
        buckets.setdefault(sesion_bucket(hh), []).append(e.get("r", 0))
    fac = {}
    for s, v in buckets.items():
        if len(v) < 10:
            continue
        hr = sum(v) / len(v)
        if hr >= 0.60:
            fac[s] = 0.9
        elif hr <= 0.40:
            fac[s] = 1.15
        else:
            fac[s] = 1.0
    for s in fac:
        fac[s] = max(0.7, min(1.4, fac[s]))
    return fac


def hay_veto(bias, prem, dxy):
    """Veto institucional: premium USA + dolar en contra de la direccion."""
    if bias == "ALZA" and prem is not None and prem < -0.03 and dxy > 0.2:
        return True
    if bias == "BAJA" and prem is not None and prem > 0.03 and dxy < -0.2:
        return True
    return False


def score_senal(dirb, h1, h4, regimen, confl=0):
    """Calidad A/B/C/D: confianza + regimen + volumen.
    NOTA: la confluencia (confl) NO mueve el grado. Se probo en 5000 velas 1H/4H
    y no mejoro el acierto (en 4H lo empeoro). Se deja solo como INFO (fuentes).
    """
    if dirb["bias"] not in ("ALZA", "BAJA"):
        return "—"
    c = dirb["confianza"]
    g = "A" if c >= 65 else ("B" if c >= 55 else ("C" if c >= 45 else "D"))
    if regimen == "rango" and g == "A":
        g = "B"
    if h1["volRel"] < 80 and g in ("A", "B"):
        g = chr(ord(g) + 1)
    return g


def familia_evento(titulo):
    """Agrupa eventos por familia para el estudio (CPI, FOMC...)."""
    try:
        tl = str(titulo or "")
        for fam, pats in (("CPI", ("CPI", "IPC")), ("PPI", ("PPI",)),
                          ("FOMC", ("FOMC", "FED ", "POWELL", "TASA", "RATE DECISION")),
                          ("NFP", ("NFP", "NON-FARM", "NOMINAS", "PAYROLL", "EMPLEO")),
                          ("PIB", ("PIB", "GDP")), ("VENTAS", ("VENTAS", "RETAIL"))):
            if any(p in tl.upper() for p in pats):
                return fam
        return "OTRO"
    except Exception:
        return "OTRO"


def estudiar_eventos(est, hist, evs, ahora):
    """Aprende de eventos pasados: mide |movimiento| 2h post-evento con el
    propio historial. Sin historia no inventa (arranca frío, lo dice)."""
    try:
        evs = evs or []
        hechas = est.get("ev_study_keys", [])
        nuevas = 0
        for e in evs:
            try:
                cu = e.get("cuando")
                if getattr(cu, "tzinfo", None) is None:
                    continue
                if (ahora - cu).total_seconds() / 3600 < 2:
                    continue
                key = str(getattr(cu, "isoformat", lambda: str(cu))()) + "|" + str(e.get("titulo", ""))
                if key in hechas:
                    continue
                pre = [h for h in hist if isinstance(h, dict) and h.get("t", "") <= cu.isoformat() and h.get("precio")]
                post = [h for h in hist if isinstance(h, dict) and cu.isoformat() < h.get("t", "") <= (cu + datetime.timedelta(hours=2)).isoformat() and h.get("precio")]
                if not pre or not post:
                    continue
                mv = abs(post[-1]["precio"] - pre[-1]["precio"]) / pre[-1]["precio"] * 100
                fam = familia_evento(e.get("titulo", ""))
                stu = est.get("ev_study", {})
                stu.setdefault(fam, []).append(round(mv, 2))
                est["ev_study"] = {k: v[-30:] for k, v in stu.items()}
                hechas.append(key)
                nuevas += 1
            except Exception:
                continue
        if nuevas:
            est["ev_study_keys"] = hechas[-100:]
        return nuevas
    except Exception:
        return 0


def linea_estudio(est, titulo):
    """'CPI suele mover ±0.8% (n=5)'. '' si hay menos de 3 casos."""
    try:
        arr = (est.get("ev_study", {}) or {}).get(familia_evento(titulo), [])
        if len(arr) < 3:
            return ""
        return f"{familia_evento(titulo)} suele mover ±{sum(arr) / len(arr):.2f}% (n={len(arr)})"
    except Exception:
        return ""


def preaviso(est, evs, ahora, hoy=None):
    """Aviso único 15–60 min antes de un evento High (con su historial medido).
    Devuelve texto o None. Puro: NO marca; la marca la pone marcar_preaviso()
    solo tras envío real (evita perder el aviso si no hay señal principal)."""
    try:
        if hoy is None:
            hoy = ahora.strftime("%Y-%m-%d")
        for e in evs or []:
            if e.get("impact") != "High":
                continue
            try:
                dt = (e["cuando"] - ahora).total_seconds() / 60
            except Exception:
                continue
            if not (15 <= dt <= 60):
                continue
            key = str(e["cuando"]) + "|" + str(e.get("titulo", ""))
            if (est.get("preavisos", {}) or {}).get(key) == hoy:
                continue
            stu = linea_estudio(est, e.get("titulo", ""))
            return (f"⚠️ {e['titulo']} en {cuenta_regresiva(e['cuando'], ahora)}"
                    + (f" ({stu})" if stu else "") +
                    ": cierro la boca ±30 min (blackout). Cuida el apalancamiento.")
        return None
    except Exception:
        return None


def marcar_preaviso(est, evs, ahora, hoy=None):
    """Marca el preaviso como enviado (solo tras envío real). Jamás lanza."""
    try:
        try:
            if hoy is None:
                hoy = ahora.strftime("%Y-%m-%d")
        except Exception:
            return False
        marcado = False
        for e in evs or []:
            try:
                if e.get("impact") != "High":
                    continue
                dt = (e["cuando"] - ahora).total_seconds() / 60
            except Exception:
                continue
            if not (15 <= dt <= 60):
                continue
            try:
                key = str(e["cuando"]) + "|" + str(e.get("titulo", ""))
                est.setdefault("preavisos", {})[key] = hoy
                marcado = True
            except Exception:
                continue
        return marcado
    except Exception:
        return False


def blackout(evs, ahora):
    """Bloqueo institucional: sin senales nuevas cerca de evento High."""
    for e in evs:
        if e.get("impact") != "High":
            continue
        try:
            dt = (e["cuando"] - ahora).total_seconds() / 60
        except Exception:
            continue
        if -BLACKOUT_MIN <= dt <= BLACKOUT_MIN:
            lado = cuenta_regresiva(e["cuando"], ahora) if dt > 0 else f"hace {int(-dt)}m"
            return True, f"{e['titulo']} ({lado})"
    return False, ""


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


# ---------------- Estado / historial / precision ----------------

def cambio(est, clave, valor, eps):
    """True si el valor cambió vs el último parte (y lo guarda).
    Con texto compara exacto; con numeros usa tolerancia eps."""
    try:
        prev = (est.get("deltas") or {}).get(clave)
    except Exception:
        prev = None
    est.setdefault("deltas", {})[clave] = valor
    if prev is None:
        return True
    try:
        return abs(float(valor) - float(prev)) > eps
    except Exception:
        return valor != prev


def enfriar(est, clave, horas, ahora=None):
    """Anti-spam: True solo si la categoria no aviso en las ultimas `horas`
    (y deja marca). Lo importante pasa; lo repetido se calla."""
    try:
        t0 = (est.get("cools") or {}).get(clave)
        ref = ahora or datetime.datetime.now(datetime.timezone.utc)
        if t0 and (ref - datetime.datetime.fromisoformat(t0)).total_seconds() / 3600 < horas:
            return False
    except Exception:
        pass
    try:
        ref = ahora or datetime.datetime.now(datetime.timezone.utc)
        est.setdefault("cools", {})[clave] = ref.isoformat()
    except Exception:
        pass
    return True


def cargar_estado():
    est = {"ultimo_bias": "?", "ultima_conf": 0, "ultimo_precio": 0,
           "ultimo_run": "", "ultimo_resumen": "", "ultimo_resumen_noche": "",
           "alza": [], "baja": [], "pendientes": [], "offset": 0, "runs": 0, "vistas": []}
    try:
        with open(ESTADO_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
            if isinstance(d, dict):
                est.update(d)
    except Exception:
        pass
    try:
        est["offset"] = int(est.get("offset") or 0)
    except Exception:
        est["offset"] = 0
    hist = []
    try:
        with open(HIST_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    h = json.loads(line)
                except Exception:
                    continue
                if isinstance(h, dict):
                    hist.append(h)
    except Exception:
        pass
    return est, hist


def _podar_estado(est):
    """Poda con cota dura todo lo que crece por pasada."""
    try:
        if isinstance(est.get("cools"), dict) and len(est["cools"]) > 200:
            est["cools"] = dict(sorted(est["cools"].items(),
                key=lambda kv: str(kv[1] or ""))[-200:])
        if isinstance(est.get("pilas"), dict) and len(est["pilas"]) > 200:
            est["pilas"] = dict(list(est["pilas"].items())[-200:])
        if isinstance(est.get("preavisos"), dict) and len(est["preavisos"]) > 100:
            est["preavisos"] = dict(list(est["preavisos"].items())[-100:])
        for k, n in (("pend_todo", MAX_PEND_TODO), ("eval_todo", MAX_EVAL_TODO),
                     ("pend_sombra", MAX_PEND_TODO), ("eval_sombra", MAX_EVAL_TODO),
                     ("pendientes", MAX_PEND_TODO), ("eval_log", MAX_EVAL_TODO),
                     ("pend_gate", MAX_PEND_TODO), ("eval_gate", MAX_EVAL_TODO),
                     ("alza_gate", 50), ("baja_gate", 50),
                     ("paper_abiertas", MAX_PAPER_ABIERTAS), ("ops", MAX_OPS),
                     ("journal", 50), ("sim_cerradas", 20), ("paper_cerradas", 100)):
            v = est.get(k)
            if isinstance(v, list) and len(v) > n:
                est[k] = v[-n:]
        d = est.get("deltas")
        if isinstance(d, dict) and len(d) > MAX_DELTAS:
            est["deltas"] = dict(list(d.items())[-MAX_DELTAS:])
    except Exception:
        pass
    return est


def guardar_estado(est, hist):
    _podar_estado(est)
    hist = hist[-MAX_HIST:]
    tmp_e = ESTADO_FILE + ".tmp"
    with open(tmp_e, "w", encoding="utf-8") as fh:
        json.dump(est, fh)
    os.replace(tmp_e, ESTADO_FILE)
    tmp_h = HIST_FILE + ".tmp"
    with open(tmp_h, "w", encoding="utf-8") as fh:
        for h in hist:
            fh.write(json.dumps(h) + "\n")
    os.replace(tmp_h, HIST_FILE)


def prec_str(lista):
    if len(lista) < MIN_SENALES:
        return f"pocas ({len(lista)})" if lista else "s/d"
    ok = sum(lista)
    return f"{round(ok / len(lista) * 100)}% ({ok}/{len(lista)})"


def precision_plan(est):
    """Acierto por direccion del PLAN, no por sesgo. None si aun no hay muestra.

    Se apoya en `eval_log` (metodo=plan, dir=ALZA/BAJA). El historico viejo
    no tiene `metodo` y se queda fuera para no repetir el error anterior.
    """
    try:
        log = [e for e in (est.get("eval_log", []) or [])
               if isinstance(e, dict) and e.get("metodo") == "plan"
               and e.get("dir") in ("ALZA", "BAJA")]
        if not log:
            return None
        return ([1 if e.get("r") else 0 for e in log if e.get("dir") == "ALZA"],
                [1 if e.get("r") else 0 for e in log if e.get("dir") == "BAJA"])
    except Exception:
        return None


def resumen_medicion(est):
    """Linea corta: que se midio de verdad (plan enviado y gate silenciado)."""
    def _fila(log, etiqueta):
        n = len(log)
        if not n:
            return ""
        h = sum(1 for e in log if float(e.get("r", 0) or 0) > 0)
        return f"{etiqueta} {h}/{n} ({round(100 * h / n)}%)"
    try:
        plan = [e for e in (est.get("eval_log", []) or [])
                if isinstance(e, dict) and e.get("metodo") == "plan"]
        gate = [e for e in (est.get("eval_gate", []) or []) if isinstance(e, dict)]
        partes = [p for p in (_fila(plan, "enviadas"), _fila(gate, "silenciadas")) if p]
        return " · ".join(partes) if partes else "aún sin muestras evaluadas"
    except Exception:
        return "aún sin muestras evaluadas"


def tabla_calibracion(eval_log):
    """Mini-conciencia: por cubeta de confianza, ¿cuánto acierto?
    + Brier (0 perfecto, 0.25 inútil). None si <5 evaluadas."""
    try:
        log = [e for e in (eval_log or []) if isinstance(e, dict)]
        if len(log) < 5:
            return None
        brier = sum(((float(e.get("conf", 50)) / 100) - float(e.get("r", 0))) ** 2
                    for e in log) / len(log)
        cubs = {}
        for e in log:
            c = float(e.get("conf", 50))
            k = "40s" if c < 50 else ("50s" if c < 60 else "60+")
            a, b = cubs.get(k, [0, 0])
            cubs[k] = [a + 1, b + float(e.get("r", 0))]
        return {"n": len(log), "brier": round(brier, 3),
                "cubetas": {k: (n, round(100 * w / n)) for k, (n, w) in sorted(cubs.items())}}
    except Exception:
        return None


RUNBOOK_URL = "https://github.com/LuiferX/vigilante-btc/blob/main/README.md"
DASH_URL = "https://luiferx.github.io/vigilante-btc/"


def tca_linea(arrival, px, fee_bps=20.0):
    """Costo en cristiano: de dónde viene el precio y cuánto te come operar. Puro."""
    try:
        _fee = float(fee_bps)
        if not (0 < _fee < 100):
            return "Ref s/d (sin precio previo)"
    except Exception:
        return "Ref s/d (sin precio previo)"
    try:
        if arrival is None or px is None:
            return "Ref s/d (sin precio previo)"
        arrival, px = float(arrival), float(px)
        if arrival <= 0 or px <= 0:
            return "Ref s/d (sin precio previo)"
        mov = (px - arrival) / arrival * 100
        return ("Ref %s → ahora %s (%+.2f%%) · operar te cuesta ~%.2f%% ida+vuelta"
                % (fmt_miles(arrival), fmt_miles(px), mov, _fee / 100))
    except Exception:
        return "Ref s/d (sin precio previo)"


def linea_runbook():
    """Una línea con runbook + página + comando de diagnóstico. Puro."""
    return ("Runbook: %s | Page: %s | diag: gh run view --repo LuiferX/vigilante-btc"
            % (RUNBOOK_URL, DASH_URL))


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
        return {"ok": bool(velas) and malas == 0 and gaps == 0,
                "n": len(velas), "malas": malas, "gaps": gaps}
    except Exception:
        return {"ok": False, "n": 0, "malas": 0, "gaps": 0}


def latido_tarde(ultimo_run_iso, ahora_iso, max_min=15):
    """Watchdog puro: True si el último run supera max_min. Sin efectos."""
    try:
        t0 = datetime.datetime.fromisoformat(ultimo_run_iso)
        t1 = datetime.datetime.fromisoformat(ahora_iso)
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=datetime.timezone.utc)
        if t1.tzinfo is None:
            t1 = t1.replace(tzinfo=datetime.timezone.utc)
        return (t1 - t0).total_seconds() / 60 > max_min
    except Exception:
        return False


def evaluar_mfe(est, ahora, velas=None, pend_key="pendientes", log_key="eval_log",
                alza_key="alza", baja_key="baja", metodo="plan"):
    """Evalua pendientes vencidas (>=8h) por MFE/MAE sobre velas 1H:
    exito si el objetivo 2R se toca antes que el stop 1R.
    En la misma vela manda el stop (conservador). Sin toques: fallback por cierre.
    Guarda vector de resultado (mfe/mae) para futura correlacion.

    `metodo="gate"` permite medir tambien las alertas que el gate silencio,
    sin mezclarlas con las que si se enviaron."""
    pends = est.get(pend_key, [])
    if not pends:
        return
    if velas is None:
        try:
            velas = klines("1h", 220)
        except Exception:
            return
    nuevas = []
    for p in pends:
        try:
            t0 = datetime.datetime.fromisoformat(p["t"])
        except Exception:
            continue
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=datetime.timezone.utc)
        if (ahora - t0).total_seconds() / 3600 < EVAL_HORAS:
            nuevas.append(p)
            continue
        entry = p["precio"]
        try:
            risk = float(p.get("risk") or 0)
        except Exception:
            risk = 0.0
        if not (risk > 0):
            risk = max(entry * UMBRAL_MOV, 1)
        direc = p.get("dir")
        if direc not in ("ALZA", "BAJA"):
            direc = direccion_alerta(p.get("motivo", ""), p.get("bias"))
        if direc not in ("ALZA", "BAJA"):
            direc = p.get("bias")
        if direc == "ALZA":
            tp, sl = entry + 2 * risk, entry - risk
        elif direc == "BAJA":
            tp, sl = entry - 2 * risk, entry + risk
        else:
            continue
        ventana = [v for v in velas if t0 < v["t"] <= t0 + datetime.timedelta(hours=8)]
        hit = None
        mfe = mae = 0.0
        for v in ventana:
            if direc == "ALZA":
                mfe = max(mfe, (v["h"] - entry) / entry)
                mae = max(mae, (entry - v["l"]) / entry)
                toca_tp = v["h"] >= tp
                toca_sl = v["l"] <= sl
            else:
                mfe = max(mfe, (entry - v["l"]) / entry)
                mae = max(mae, (v["h"] - entry) / entry)
                toca_tp = v["l"] <= tp
                toca_sl = v["h"] >= sl
            if toca_sl and toca_tp:
                hit = 0
                break
            if toca_tp:
                hit = 1
                break
            if toca_sl:
                hit = 0
                break
        if hit is None:
            if not ventana:
                nuevas.append(p)
                continue
            cierre = ventana[-1]["c"]
            mov = (cierre - entry) / entry
            if direc == "ALZA":
                hit = 1 if mov >= risk / entry else 0
            else:
                hit = 1 if mov <= -risk / entry else 0
        if direc == "ALZA":
            est[alza_key] = (est.get(alza_key, []) + [hit])[-50:]
        else:
            est[baja_key] = (est.get(baja_key, []) + [hit])[-50:]
        # Un pendiente viejo sin `dir` ni `motivo` se creo midiendo sesgo, no
        # plan. Se conserva para no perder historia, pero no entra al scoreboard
        # nuevo (solo_plan=True).
        _metodo_p = metodo
        if metodo == "plan" and not p.get("dir") and not p.get("motivo"):
            _metodo_p = "sesgo_legacy"
        log = est.get(log_key, [])
        log.append({"b": p.get("bias"), "dir": direc, "r": hit, "t": ahora.isoformat(),
                    "conf": p.get("conf", 0), "mfe": round(mfe, 4), "mae": round(mae, 4),
                    "tipo": p.get("tipo") or "?", "metodo": _metodo_p})
        est[log_key] = log[-200:]
    est[pend_key] = nuevas[-100:]


def registrar_pend_gate(est, ahora, precio, dirb, dir_alerta, tipo, motivo,
                        gate_reason, umbral, h1, h4, senti, fg):
    """Guarda una alerta silenciada para medirla despues. No la envia.

    Dedup 4h por direccion. Devuelve True si la registro. Es contrafactual:
    `eval_gate` nunca se mezcla con el scoreboard de alertas enviadas.
    """
    if dir_alerta not in ("ALZA", "BAJA"):
        return False
    for p in est.get("pend_gate", []):
        try:
            _pd = p.get("dir") or direccion_alerta(p.get("motivo", ""), p.get("bias")) or p.get("bias")
            if _pd == dir_alerta and (ahora - datetime.datetime.fromisoformat(p["t"])).total_seconds() / 3600 < DEDUP_HORAS:
                return False
        except Exception:
            continue
    try:
        _conf = dirb.get("confianza", 0)
    except Exception:
        _conf = 0
    try:
        _risk = round(float(umbral) * float(precio), 1)
    except Exception:
        _risk = 0.0
    est["pend_gate"] = est.get("pend_gate", []) + [
        {"t": ahora.isoformat(), "precio": round(precio),
         "bias": dirb.get("bias") if isinstance(dirb, dict) else None,
         "dir": dir_alerta, "conf": _conf, "tipo": tipo, "motivo": str(motivo or "")[:200],
         "gate": gate_reason, "risk": _risk,
         "feat": {"rsi": (h1 or {}).get("rsi"), "adx": (h4 or {}).get("adx", 0),
                  "fund": (senti or {}).get("funding"), "taker": (senti or {}).get("taker"),
                  "fg": (fg or {}).get("valor")}}]
    return True


def abrir_todo(est, bias, conf, precio, umbral, ahora):
    """Todo: registra CADA pasada (hable o calle) para medir si callar fue correcto.
    No alerta, no opera, no toca nada vivo. Dedup 1h por sesgo."""
    try:
        if bias not in ("ALZA", "BAJA", "LATERAL"):
            return False
        pu = est.get("todo_ult") or {}
        try:
            if pu.get("dir") == bias and (ahora - datetime.datetime.fromisoformat(pu.get("t", ""))).total_seconds() / 3600 < 1:
                return False
        except Exception:
            pass
        try:
            precio = float(precio)
            if not (precio > 0):
                return False
        except Exception:
            return False
        try:
            conf = float(conf)
        except Exception:
            conf = 0.0
        ps = est.get("pend_todo", [])
        ps.append({"t": ahora.isoformat(), "precio": round(precio),
                   "bias": bias, "conf": conf,
                   "risk": round(umbral * precio, 1)})
        est["pend_todo"] = ps[-MAX_PEND_TODO:]
        est["todo_ult"] = {"dir": bias, "t": ahora.isoformat()}
        return True
    except Exception:
        return False


def evaluar_todo(est, ahora, velas=None):
    """Evalúa todo vencido (>=8h). ALZA/BAJA igual que sombra; LATERAL acierta
    si NO hubo movimiento 2R a ningún lado (callar fue correcto).
    Guarda en eval_todo, jamás en vivo. Puro en fallos."""
    try:
        pends = est.get("pend_todo", [])
        if not pends:
            return
        if velas is None:
            try:
                velas = klines("1h", 220)
            except Exception:
                return
        nuevas = []
        for p in pends:
            try:
                t0 = datetime.datetime.fromisoformat(p["t"])
            except Exception:
                continue
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=datetime.timezone.utc)
            if (ahora - t0).total_seconds() / 3600 < EVAL_HORAS:
                nuevas.append(p)
                continue
            try:
                entry = float(p["precio"])
                if not (entry > 0):
                    continue
            except Exception:
                continue
            try:
                risk = float(p.get("risk") or 0)
            except Exception:
                risk = 0.0
            if not (risk > 0):
                risk = max(entry * UMBRAL_MOV, 1)
            try:
                ventana = [v for v in velas if t0 < v["t"] <= t0 + datetime.timedelta(hours=8)]
            except Exception:
                continue
            try:
                mfe = mae = 0.0
                toca_tp = toca_sl = False
                # MFE/MAE direccionales (favor/contra), igual que sombra/mfe:
                # antes ambos se calculaban en sentido ALZA tambien para BAJA.
                for v in ventana:
                    if p["bias"] == "BAJA":
                        mfe = max(mfe, (entry - v["l"]) / entry)
                        mae = max(mae, (v["h"] - entry) / entry)
                    else:
                        mfe = max(mfe, (v["h"] - entry) / entry)
                        mae = max(mae, (entry - v["l"]) / entry)
                ru = risk / entry
                if p["bias"] == "ALZA":
                    tp, sl = entry + 2 * risk, entry - risk
                    for v in ventana:
                        if v["l"] <= sl:
                            toca_sl = True
                            break
                        if v["h"] >= tp:
                            toca_tp = True
                            break
                    hit = 1 if toca_tp else 0
                elif p["bias"] == "BAJA":
                    tp, sl = entry - 2 * risk, entry + risk
                    for v in ventana:
                        if v["h"] >= sl:
                            toca_sl = True
                            break
                        if v["l"] <= tp:
                            toca_tp = True
                            break
                    hit = 1 if toca_tp else 0
                else:
                    hit = 1 if (mfe < 2 * ru and mae < 2 * ru) else 0
                if not ventana:
                    nuevas.append(p)
                    continue
                log = est.get("eval_todo", [])
                log.append({"b": p["bias"], "r": hit, "t": ahora.isoformat(),
                            "conf": p.get("conf", 0), "mfe": round(mfe, 4), "mae": round(mae, 4)})
                est["eval_todo"] = log[-MAX_EVAL_TODO:]
            except Exception:
                continue
        est["pend_todo"] = nuevas[-MAX_PEND_TODO:]
    except Exception:
        pass


def abrir_sombra(est, bias, conf, precio, umbral, ahora):
    """Sombra: registra TODA señal con sesgo (sin piso de conf) solo para medir.
    No alerta, no opera papel, no toca alza/baja/eval_log. Dedup 4h por direccion."""
    try:
        if bias not in ("ALZA", "BAJA"):
            return False
        try:
            precio = float(precio)
        except Exception:
            return False
        if not (precio > 0):
            return False
        try:
            conf = float(conf)
        except Exception:
            conf = 0.0
        pu = est.get("sombra_ult") or {}
        try:
            if pu.get("dir") == bias and (ahora - datetime.datetime.fromisoformat(pu.get("t", ""))).total_seconds() / 3600 < DEDUP_HORAS:
                return False
        except Exception:
            pass
        ps = est.get("pend_sombra", [])
        ps.append({"t": ahora.isoformat(), "precio": round(precio),
                   "bias": bias, "conf": conf,
                   "risk": round(umbral * precio, 1)})
        est["pend_sombra"] = ps[-MAX_PEND_TODO:]
        est["sombra_ult"] = {"dir": bias, "t": ahora.isoformat()}
        return True
    except Exception:
        return False


def evaluar_sombra(est, ahora, velas=None):
    """Evalúa sombra vencida (>=8h) con la MISMA regla MFE que evaluar_mfe,
    pero guarda en eval_sombra (jamás en alza/baja/eval_log). Pura en fallos."""
    try:
        pends = est.get("pend_sombra", [])
        if not pends:
            return
        if velas is None:
            try:
                velas = klines("1h", 220)
            except Exception:
                return
        nuevas = []
        for p in pends:
            try:
                t0 = datetime.datetime.fromisoformat(p["t"])
            except Exception:
                continue
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=datetime.timezone.utc)
            if (ahora - t0).total_seconds() / 3600 < EVAL_HORAS:
                nuevas.append(p)
                continue
            try:
                entry = float(p["precio"])
                if not (entry > 0):
                    continue
            except Exception:
                continue
            try:
                risk = float(p.get("risk") or 0)
            except Exception:
                risk = 0.0
            if not (risk > 0):
                risk = max(entry * UMBRAL_MOV, 1)
            if p["bias"] == "ALZA":
                tp, sl = entry + 2 * risk, entry - risk
            elif p["bias"] == "BAJA":
                tp, sl = entry - 2 * risk, entry + risk
            else:
                continue
            ventana = [v for v in velas if t0 < v["t"] <= t0 + datetime.timedelta(hours=8)]
            try:
                hit = None
                mfe = mae = 0.0
                for v in ventana:
                    if p["bias"] == "ALZA":
                        mfe = max(mfe, (v["h"] - entry) / entry)
                        mae = max(mae, (entry - v["l"]) / entry)
                        toca_tp = v["h"] >= tp
                        toca_sl = v["l"] <= sl
                    else:
                        mfe = max(mfe, (entry - v["l"]) / entry)
                        mae = max(mae, (v["h"] - entry) / entry)
                        toca_tp = v["l"] <= tp
                        toca_sl = v["h"] >= sl
                    if toca_sl and toca_tp:
                        hit = 0
                        break
                    if toca_tp:
                        hit = 1
                        break
                    if toca_sl:
                        hit = 0
                        break
                if hit is None:
                    if not ventana:
                        nuevas.append(p)
                        continue
                    cierre = ventana[-1]["c"]
                    mov = (cierre - entry) / entry
                    if p["bias"] == "ALZA":
                        hit = 1 if mov >= risk / entry else 0
                    else:
                        hit = 1 if mov <= -risk / entry else 0
                log = est.get("eval_sombra", [])
                log.append({"b": p["bias"], "r": hit, "t": ahora.isoformat(),
                            "conf": p.get("conf", 0), "mfe": round(mfe, 4), "mae": round(mae, 4)})
                est["eval_sombra"] = log[-MAX_EVAL_TODO:]
            except Exception:
                continue
        est["pend_sombra"] = nuevas[-MAX_PEND_TODO:]
    except Exception:
        pass


def gestion_sl(op, last, atr_h1, regimen):
    """Gestion real de una op abierta: (R, accion, nuevo_sl).
    BE si R>=+1 con SL en perdida; TRAIL (+1R trabado) si R>=+1.5,
    paso minimo 0.25*ATR y NO en rango. Puro, sin red."""
    try:
        d = (op or {}).get("dir")
        e = float(op["entrada"])
        s = float(op["stop"])
        last = float(last)
        atr = float(atr_h1)
        try:
            risk = float((op or {}).get("risk0") or abs(e - s))
        except Exception:
            risk = abs(e - s)
        if not (risk > 0):
            try:
                if not (op or {}).get("risk0") and abs(e - s) > 0:
                    op["risk0"] = abs(e - s)
                    risk = abs(e - s)
            except Exception:
                pass
        if not (risk > 0) or not (atr > 0):
            return (None, None, None)
        if d == "LONG":
            r = (last - e) / risk
            en_perdida = s < e
            if r >= 1.0 and en_perdida and not op.get("be_done"):
                return (round(r, 2), "BE", round(e))
            if r >= 1.5 and regimen != "rango":
                cand = e + risk
                if cand - s >= 0.25 * atr:
                    return (round(r, 2), "TRAIL", round(cand))
        elif d == "SHORT":
            r = (e - last) / risk
            en_perdida = s > e
            if r >= 1.0 and en_perdida and not op.get("be_done"):
                return (round(r, 2), "BE", round(e))
            if r >= 1.5 and regimen != "rango":
                cand = e - risk
                if s - cand >= 0.25 * atr:
                    return (round(r, 2), "TRAIL", round(cand))
        else:
            return (None, None, None)
        return (round(r, 2), None, None)
    except Exception:
        return (None, None, None)


def decidir_alerta(precio, niv, dirb, est, ahora, forzado=None, mov1h=None, regimen=None, bloqueo=False, motivo_bloq="", mov_ny=None, liq=None, pila=None, umbral_fuerte=UMBRAL_CONF_FUERTE, umbral_cambio=UMBRAL_CONF_CAMBIO, mov30=None, rup=None, qb=None, sl=None, gestion=None, mecha=None, slm=None, estir=None, foot=None, umbral=None, atr=None, liq_plan=None, chop=False):
    """Devuelve (enviar, motivo, tipo). Tipos: alerta, preny, manana, madrugada, noche, nada."""
    try:
        res = niv["resistencias"][0]
        sup = niv["soportes"][0]
        bias, conf = dirb["bias"], float(dirb["confianza"])
        _chop = bool(chop)
    except Exception:
        return False, "estado incompleto", "nada"
    try:
        dist_res = (res["precio"] - precio) / precio if res["precio"] > 0 else 1
        dist_sup = (precio - sup["precio"]) / precio if precio > 0 else 1
    except Exception:
        dist_res, dist_sup = 1, 1
    prev = est.get("ultimo_bias", "?")
    # Filtro de volatilidad (opt-in): si FEE/umbral > 0.25, los fees comen la senal.
    _vol_filtrado = (FILTRO_VOL and umbral and umbral > 0
                     and (FEE_PCT / umbral) > 0.25)
    if forzado:
        return True, forzado, "alerta"
    if gestion:
        return True, gestion, "alerta"
    hoy = ahora.strftime("%Y-%m-%d")
    hh = ahora.hour + ahora.minute / 60

    def _reporte_programado():
        if 13 <= hh < 13.5 and est.get("ultimo_preny") != hoy:
            return True, "REPORTE PRE-NY (30 min para la apertura)", "preny"
        if ahora.hour == 7 and est.get("ultimo_madrugada") != hoy:
            return True, "Resumen nocturno (mientras dormías)", "madrugada"
        if 8 <= hh < 9 and est.get("ultimo_resumen") != f"{hoy}-manana":
            return True, "Buenos días, plan del día (Londres)", "manana"
        if 2 <= hh < 3 and est.get("ultimo_resumen_noche") != hoy:
            return True, "Buenas noches, resumen del día", "noche"
        return None

    if bloqueo:
        # B3: el blackout cancela señales NUEVAS, no los reportes fijos del día
        _prog = _reporte_programado()
        if _prog:
            return _prog
        return False, f"blackout ({motivo_bloq})", "nada"
    if _vol_filtrado:
        # No envia la senal direccional, pero el resto de alertas (brusco, ritmo, etc.) siguen.
        pass
    if (not _vol_filtrado and prev != "?" and prev != bias
            and bias in ("ALZA", "BAJA") and conf >= umbral_cambio and enfriar(
            est, "fuerte:" + bias, 4, ahora)):
        return True, f"Cambio de dirección: {prev} → {bias}", "alerta"
    if (not _vol_filtrado and bias in ("ALZA", "BAJA") and conf >= umbral_fuerte and enfriar(
            est, "fuerte:" + bias, 4, ahora)):
        return True, f"Señal fuerte {bias} (confianza {conf}%)", "alerta"
    # Un movimiento = un aviso. Medido en produccion (historial real): 16 de 36
    # avisos de movimiento eran el MISMO movimiento repetido con minutos de
    # diferencia. brusco y ritmo comparten ventana por direccion: el que dispara
    # primero consume el enfriamiento del otro. VIGILANTE_RUIDO_UNIFICADO=0 apaga.
    _ruido_unif = os.environ.get("VIGILANTE_RUIDO_UNIFICADO", "1") not in ("", "0", "false", "False")
    if mov1h is not None and abs(mov1h) >= UMBRAL_BRUSCO and enfriar(
            est, "brusco:" + ("sube" if mov1h > 0 else "baja"), 4, ahora) and (
            not _ruido_unif or mov30 is None or abs(mov30) < UMBRAL_RITMO
            or ("sube" if mov30 > 0 else "baja") != ("sube" if mov1h > 0 else "baja")
            or enfriar(est, "ritmo:" + ("sube" if mov1h > 0 else "baja"), 4, ahora)):
        return True, f"Movimiento brusco de {mov1h:+.2f}% en 1 h", "alerta"
    if mov30 is not None and abs(mov30) >= UMBRAL_RITMO and enfriar(
            est, "ritmo:" + ("sube" if mov30 > 0 else "baja"), 4, ahora) and (
            not _ruido_unif or mov1h is None or abs(mov1h) < UMBRAL_BRUSCO
            or ("sube" if mov30 > 0 else "baja") != ("sube" if mov1h > 0 else "baja")
            or enfriar(est, "brusco:" + ("sube" if mov30 > 0 else "baja"), 4, ahora)):
        return True, f"Ritmo acelerado {mov30:+.2f}% en 30 min", "alerta"
    if isinstance(estir, str) and estir and (bias not in ("ALZA", "BAJA") or conf < 45) and enfriar(est, "estir:" + ("bajo" if estir.startswith("bajo") else "alto"), 4, ahora):
        return True, f"Estirado {estir} (toma parcial, rebote probable — no es entrada)", "alerta"
    if rup:
        try:
            mm = re.search(r"(?:bajo|sobre)\s+([\d.]+)", rup)
            rkey = "ruptura:" + (mm.group(1) if mm else rup)
        except Exception:
            rkey = "ruptura:?"
        try:
            _rb = "ALCISTA" in rup
            _contra = (_rb and bias == "BAJA") or (not _rb and bias == "ALZA")
        except Exception:
            _rb, _contra = True, False
        _plan = plan_trade("rup_alcista" if _rb else "rup_bajista", precio, niv, atr) if atr else None
        # Medido en 5000 velas: ruptura contra el sesgo = 25% a 2R (-0.20R),
        # a favor = 33%. Si va contra, no hay sesgo o el mercado es chop, se
        # avisa como CONTEXTO y no se adjunta plan: no es una entrada.
        _ctx = _contra or bias not in ("ALZA", "BAJA") or _chop
        if _ctx:
            _plan = None
        if (_ctx or not atr or (_plan and _plan["valido"])) and enfriar(est, rkey, 12, ahora):
            if _chop:
                _aviso = " (contexto: chop, no es entrada)"
            elif _contra:
                _aviso = " (contexto: ruptura contra el sesgo, no es entrada)"
            elif _ctx:
                _aviso = " (contexto: sin sesgo direccional, no es entrada)"
            else:
                _aviso = ""
            _fut = fuentes_nivel(res if _rb else sup)
            _fut = (f" [nivel: {_fut}]" if _fut else "")
            _pt = (" · " + texto_plan(_plan)) if _plan else ""
            return True, rup + _fut + _aviso + _pt, "alerta"
    if liq:
        contra = ("sobre" in liq and bias == "ALZA") or ("sobre" not in liq and bias == "BAJA")
        lado = "max" if "sobre" in liq else "min"
        try:
            _mliq = re.search(r"([\d.]+)", str(liq))
            _kliq = "liq:" + lado + ":" + (_mliq.group(1).replace(".", "") if _mliq else "?")
        except Exception:
            _kliq = "liq:" + lado
        if not contra and enfriar(est, _kliq, 4, ahora):
            if "sobre" in liq:
                ref = f"desvanecer hacia {fmt_miles(niv['soportes'][0]['precio'])} (referencia)"
            else:
                ref = f"desvanecer hacia {fmt_miles(niv['resistencias'][0]['precio'])} (referencia)"
            _pl = ""
            if _chop:
                _pl = " · chop: contexto, no perseguir"
            elif isinstance(liq_plan, dict):
                if liq_plan.get("valido"):
                    _pl = " · " + texto_plan(liq_plan)
                else:
                    _pl = f" · sin plan válido (R:R {liq_plan.get('rr', 0):.1f}) — solo aviso"
            return True, "Toma de liquidez: " + liq + f". Quien la persigue suele quedar atrapado → {ref}." + _pl, "alerta"
    if mov_ny is not None and abs(mov_ny) >= UMBRAL_DIA_NY and enfriar(est, "diadc", 24, ahora):
        return True, f"La sesión NY mueve {mov_ny:+.2f}% hoy", "alerta"
    if pila:
        try:
            try:
                _mm = re.search(r"de\s+([\d.]+)", str(pila))
                _zz = _mm.group(1).replace(".", "") if _mm else str(pila)[:80]
                _pk = "pila:" + str(_zz)
            except Exception:
                _pk = "pila:?"
            if enfriar(est, _pk, 24, ahora):
                return True, pila, "alerta"
        except Exception:
            try:
                return True, pila, "alerta"
            except Exception:
                pass
    if isinstance(qb, dict) and qb.get("dir") in ("ALZA", "BAJA") and bias == qb["dir"] and conf >= UMBRAL_CONF_SENAL:
        try:
            _stop = sl[0] if isinstance(sl, (list, tuple)) and sl else None
            _plan = plan_trade("long" if qb["dir"] == "ALZA" else "short", precio, niv, atr, stop=_stop) if (atr and _stop and not _chop) else None
            _pasa = True if _chop else ((not atr) or bool(_plan and _plan["valido"]))
            if _pasa and enfriar(est, "qb:" + qb["dir"], 4, ahora):
                verbo = "COMPRA" if qb["dir"] == "ALZA" else "VENTA"
                extra = (f" · {texto_plan(_plan)}" if _plan else
                         (f" · SL {fmt_miles(_stop)}" if _stop is not None else ""))
                lejos = " (SL lejos, tamaño pequeño)" if isinstance(sl, (list, tuple)) and len(sl) > 2 and sl[2] else ""
                _chopn = " (chop: contexto, no entrada)" if _chop else ""
                return True, f"{verbo} {qb.get('tipo', 'BOS')} sobre {fmt_miles(qb.get('nivel', precio))}{extra}{lejos}{_chopn}", "alerta"
        except Exception:
            pass
    if isinstance(mecha, dict) and mecha.get("dir") in ("ALZA", "BAJA") and bias == mecha["dir"] and conf >= UMBRAL_CONF_SENAL and regimen == "tendencia":
        try:
            _stopm = slm[0] if isinstance(slm, (list, tuple)) and slm else None
            _planm = plan_trade("long" if mecha["dir"] == "ALZA" else "short", precio, niv, atr, stop=_stopm) if (atr and _stopm and not _chop) else None
            _pasam = True if _chop else ((not atr) or bool(_planm and _planm["valido"]))
            if _pasam and enfriar(est, "mecha:" + mecha["dir"], 4, ahora):
                verbo = "RECHAZO ALZA" if mecha["dir"] == "ALZA" else "RECHAZO BAJA"
                extra = (f" · {texto_plan(_planm)}" if _planm else
                         (f" · SL {fmt_miles(_stopm)}" if _stopm is not None else ""))
                lejos = " (SL lejos, tamaño pequeño)" if isinstance(slm, (list, tuple)) and len(slm) > 2 and slm[2] else ""
                _chopm = " (chop: contexto, no entrada)" if _chop else ""
                return True, f"{verbo} {fmt_miles(mecha.get('nivel', precio))}→{fmt_miles(precio)}{extra}{lejos}{_chopm}", "alerta"
        except Exception:
            pass
    if min(dist_res, dist_sup) <= UMBRAL_TOQUE:
        lado = f"la resistencia de {fmt_miles(res['precio'])}" if dist_res <= dist_sup else f"el soporte de {fmt_miles(sup['precio'])}"
        nivel = res["precio"] if dist_res <= dist_sup else sup["precio"]
        fade_ok = True if bias == "LATERAL" else ((bias == "BAJA") if dist_res <= dist_sup else (bias == "ALZA"))
        _plan = plan_trade("resistencia" if dist_res <= dist_sup else "soporte", precio, niv, atr) if (atr and not _chop) else None
        _pasa_toque = True if _chop else ((not atr) or bool(_plan and _plan["valido"]))
        if _pasa_toque and not (conf < 45 and (regimen or "tendencia") == "rango") and fade_ok and enfriar(
                est, f"toque:{nivel}", 10, ahora):
            _pt = (" · " + texto_plan(_plan)) if _plan else (" · chop: contexto, no entrada" if _chop else "")
            _fut = fuentes_nivel(res if dist_res <= dist_sup else sup)
            _fut = (f" [fuentes: {_fut}]" if _fut else "")
            return True, f"Tocando {lado}" + ficha_zona(est, nivel) + _fut + _pt, "alerta"
    _prog = _reporte_programado()
    if _prog:
        return _prog
    return False, "sin señal (rango, sin cambios)", "nada"


def build_parte(t, h1, h4, d1, w1, niv, dirb, prox, senti, fg, est, motivo, tipo, notis, evs, ahora, extras):
    res = niv["resistencias"][0]
    sup = niv["soportes"][0]
    horas_res = round((res["precio"] - t["last"]) / h1["atr"], 1) if h1["atr"] > 0 else None
    horas_sup = round((t["last"] - sup["precio"]) / h1["atr"], 1) if h1["atr"] > 0 else None
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%d/%m %H:%M UTC")
    icon = {"ALCISTA": "🟢", "BAJISTA": "🔴", "lateral": "🟡"}
    if dirb["bias"] == "ALZA":
        accion = f"busca cierre 1H SOBRE {fmt_miles(res['precio'])}"
    elif dirb["bias"] == "BAJA":
        accion = f"busca cierre 1H BAJO {fmt_miles(sup['precio'])}"
    else:
        accion = f"espera ruptura {fmt_miles(sup['precio'])}-{fmt_miles(res['precio'])}"
    if tipo == "alerta":
        # Parte CORTO: solo lo que se lee (motivo + veredicto + accion + niveles).
        try:
            C = []
            _mot = str(motivo or "").strip()
            if not _mot:
                return ""
            C.append("🚨 " + _mot)
            _grade = extras.get('grade') or "?"
            C.append(f"{dirb['bias']} {dirb['confianza']}% · calidad {_grade} · {fmt_miles(t['last'])} ({t['chg']:+.2f}%)")
            C.append(f"🎯 {accion}")
            C.append(f"Piso {fmt_miles(sup['precio'])} · Techo {fmt_miles(res['precio'])}")
            _fvg_txt = texto_fvg(extras.get("fvg"), t["last"], max_dist=0.6)
            if _fvg_txt:
                C.append(_fvg_txt)
            if extras.get("fflag"):
                C.append("⚠️ " + str(extras["fflag"]))
            if extras.get("mov_ny") is not None:
                try:
                    C.append(f"NY {extras['mov_ny']:+.2f}% desde apertura")
                except Exception:
                    pass
            try:
                _sp = (senti or {}).get("spread")
                if _sp is not None:
                    C.append(f"Spread {_sp}bps → {regla_spread(_sp)}")
            except Exception:
                pass
            vistos = {accion}
            for p in (extras.get("plan") or [])[:2]:
                try:
                    _ps = str(p or "").strip()
                    if not _ps or _ps in vistos:
                        continue
                    vistos.add(_ps)
                    C.append("• " + _ps)
                except Exception:
                    pass
            try:
                _tca = tca_linea(extras.get("arrival"), t["last"])
                if _tca and "s/d" not in _tca:
                    C.append(_tca)
            except Exception:
                pass
            return "\n".join(C)
        except Exception:
            try:
                return "\n".join(C) if C else str(motivo)
            except Exception:
                return str(motivo)

    icono_tipo = {"alerta": "🚨", "preny": "📊", "manana": "☀️", "madrugada": "🌙", "noche": "🌙"}.get(tipo, "🤖")
    L = []
    L.append(icono_tipo + " " + motivo)
    L.append("💬 " + str(extras.get("intro") or "").strip())
    L.append("━━━━━ 🧭 VEREDICTO ━━━━━")
    L.append(f"{dirb['bias']} {dirb['confianza']}% · calidad {extras.get('grade', '?')} · {fmt_miles(t['last'])} ({t['chg']:+.2f}%)")
    L.append(f"🎯 {accion}")
    L.append("")
    L.append(f"🤖 VIGILANTE BTC {VERSION} | {now} | {sesion_hora()} | datos {FUENTE['nombre']}")
    L.append(f"📈 max {fmt_miles(t['hi'])} / min {fmt_miles(t['lo'])}")
    L.append("")
    L.append(f"🧭 MARCOS: {dirb['bias']} ({dirb['confianza']}%) · régimen {extras.get('regimen', '?')} · ADX 4H {h4.get('adx', '?')}")
    if extras.get("motor"):
        L.append("📐 " + linea_motor(extras["motor"]))
    if extras.get("confl", 0) >= 2:
        L.append(f"🧩 Confluencia: {extras['confl']} fuentes en el nivel más cercano")
    L.append("  " + "  ".join(f"{x['tf']}{icon.get(x['tend'], '🟡')}(s{x['score']:+d})" for x in (h1, h4, d1, w1)))
    L.append("")
    L.append("📖 " + str(extras.get("narrativa") or "").strip())
    L.append("")
    s_txt = "  |  ".join(f"{fmt_miles(x['precio'])} ({x['origen']})" for x in niv["soportes"])
    r_txt = "  |  ".join(f"{fmt_miles(x['precio'])} ({x['origen']})" for x in niv["resistencias"])
    L.append(f"🟢 SOPORTES: {s_txt}")
    L.append(f"🔴 RESISTENCIAS: {r_txt}")
    _fvg_txt = texto_fvg(extras.get("fvg"), t["last"])
    if _fvg_txt:
        L.append(_fvg_txt)
    for m in (extras.get("memoria") or [])[:3]:
        _m = str(m or "").strip()
        if _m:
            L.append("🧠 " + _m)
    if extras.get("fflag"):
        L.append("⚠️ Funding extremo: " + extras["fflag"])
    L.append("")
    if extras.get("mov_ny") is not None:
        try:
            L.append(f"🕯 NY: {float(extras['mov_ny']):+.2f}% desde la apertura")
        except Exception:
            pass
    for n in (extras.get("nuevas") or [])[:2]:
        if not isinstance(n, dict):
            continue
        _t = str(n.get("titulo") or "").strip()
        if not _t:
            continue
        L.append(f"🆕 [{n.get('score', '?')}] {_t}")
    _plan = [str(p or "").strip() for p in (extras.get("plan") or [])]
    _plan = [p for p in _plan if p]
    if _plan:
        L.append("")
        L.append("🎯 PLAN (qué esperar para entrar):")
        for p in _plan:
            L.append("   • " + p)
    L.append("")
    if dirb["bias"] == "ALZA":
        L.append(f"⏱ Objetivo SOBRE {fmt_miles(res['precio'])} a ~{horas_res} h | ⏰ {prox} | 4H en {h4['cierreEnMin']} min")
    elif dirb["bias"] == "BAJA":
        L.append(f"⏱ Objetivo BAJO {fmt_miles(sup['precio'])} a ~{horas_sup} h | ⏰ {prox} | 4H en {h4['cierreEnMin']} min")
    else:
        L.append(f"⏱ Rango activo | ⏰ {prox} | 4H en {h4['cierreEnMin']} min")
    coil = [x["tf"] for x in (h1, h4, d1, w1) if x["compresion"] < 0.5]
    if coil:
        L.append(f"🌀 Compresión: {', '.join(coil)} (mercado quieto)")
    L.append(f"🌡 Volatilidad {h1['regLabel']} ({h1['regPct']}%)")
    L.append("")
    L.append("━━━━━ 📊 MERCADO (solo cambios) ━━━━━")
    hubo = False
    fg_icon = "😱" if fg["valor"] < 25 else ("😨" if fg["valor"] < 45 else ("😐" if fg["valor"] < 55 else ("🙂" if fg["valor"] < 75 else "🤑")))
    if cambio(est, "fg", fg["valor"], 3):
        L.append(f"{fg_icon} MIEDO/CODICIA: {fg['etiqueta']} {fg['valor']}/100")
        hubo = True
    sent = []
    if senti["funding"] is not None:
        sent.append(f"funding {senti['funding']:+.4f}%")
    if senti["oi"] is not None:
        sent.append(f"OI {fmt_miles(senti['oi'] * t['last'])}$")
    if senti["taker"] is not None:
        sent.append(f"taker L/S {senti['taker']}")
    if sent:
        cf = senti["funding"] is not None and cambio(est, "fund", senti["funding"], 0.005)
        ct = senti["taker"] is not None and cambio(est, "taker", senti["taker"], 0.05)
        if cf or ct:
            L.append("⚡ FUTUROS: " + " | ".join(sent) + extras.get("senti_viejo", ""))
            hubo = True
    if extras.get("macro") and extras["macro"].get("mx"):
        mx = extras["macro"]["mx"]
        dxy = mx.get("dxy")
        spx = mx.get("spx")
        if dxy and spx:
            cd = cambio(est, "dxy", dxy["chg"], 0.1)
            cs = cambio(est, "spx", spx["chg"], 0.1)
            if cd or cs:
                L.append(f"💵 DÓLAR: {dxy['px']} ({dxy['chg']:+.2f}%) | BOLSA SPX: {spx['px']} ({spx['chg']:+.2f}%)" + extras.get("macro_viejo", ""))
                L.append("🌍 " + extras["macro"]["lectura"])
                hubo = True
    sm = extras.get("smart")
    if sm:
        ci = cambio(est, "inst", sm["inst"], 5)
        cr = cambio(est, "ret", sm["ret"], 5)
        if ci or cr:
            L.append(f"🏛️ INSTITUCIONES {sm['inst']}/100 | 🧍 MINORISTAS {sm['ret']}/100")
            L.append("⚔️ " + sm["veredicto"])
            for dd in sm.get("det", [])[:2]:
                L.append("   • " + dd)
            hubo = True
    cb = extras.get("cb")
    if cb and cb.get("prem") is not None:
        vs = f"{cb['vol_share']}%" if cb.get("vol_share") is not None else "n/d"
        ib = f"{cb['imb']:+.1f}%" if cb.get("imb") is not None else "n/d"
        cp = cambio(est, "prem", cb["prem"], 0.02)
        cb2 = cb.get("imb") is not None and cambio(est, "imb", cb["imb"], 5)
        if cp or cb2:
            L.append(f"🏦 COINBASE: premium {cb['prem']:+.3f}% | vol {vs} de Binance | libro {ib}")
            L.append("   → " + cb_veredicto(cb))
            hubo = True
    bal = extras.get("bal")
    if bal and (bal.get("nb", 0) + bal.get("ns", 0)) > 0 and cambio(est, "bal", bal["txt"], 0):
        L.append(f"🐋 BALLENAS: {bal['ns']} sells {fmt_miles(bal['sells'])} BTC vs {bal['nb']} buys {fmt_miles(bal['buys'])} BTC → {bal['txt']}")
        hubo = True
    ima = extras.get("ima")
    if ima and ima.get("top"):
        tops = " | ".join(f"{fmt_miles(x['strike'])} ({fmt_miles(x['oi'])} BTC)" for x in ima["top"])
        pc = f" P/C {ima['pc']}" if ima.get("pc") is not None else ""
        clave_ima = tops + pc
        if cambio(est, "ima", clave_ima, 0):
            L.append(f"🧲 IMANES: {tops}{pc}")
            if ima.get("up") and ima.get("down"):
                L.append(f"   → imán cercano arriba {fmt_miles(ima['up'])} / abajo {fmt_miles(ima['down'])}")
            elif ima.get("up"):
                L.append(f"   → imán cercano arriba {fmt_miles(ima['up'])}")
            hubo = True
    oro = extras.get("oro")
    if oro and cambio(est, "orodiff", oro["diff"], 0.3):
        L.append(f"🥇 ORO {oro['oro']:+.2f}% vs BTC {t['chg']:+.2f}%: {oro['lectura']}")
        hubo = True
    lsr = extras.get("lsr")
    if lsr and cambio(est, "lsr", lsr["ratio"], 0.05):
        L.append(f"📊 CUENTAS long/short {lsr['ratio']}: {lsr['lectura']}")
        hubo = True
    cv = extras.get("cvd_v")
    if cv and cambio(est, "cvd", cv["lectura"], 0):
        L.append(f"🌊 CVD {cv['cvd']:+.1f} BTC vs precio {cv['dpx']:+.2f}%: {cv['lectura']}")
        hubo = True
    lm = extras.get("liqmap")
    if lm and cambio(est, "liqmap", str(lm.get("arriba")) + str(lm.get("abajo")), 0):
        arrib = " | ".join(f"{fmt_miles(x['precio'])} ({x['dist']:+.2f}%)" for x in lm.get("arriba", [])[:2])
        abaj = " | ".join(f"{fmt_miles(x['precio'])} ({x['dist']:+.2f}%)" for x in lm.get("abajo", [])[:2])
        if arrib or abaj:
            L.append(f"🌊 LIQUIDEZ: arriba {arrib or '—'} / abajo {abaj or '—'}")
            hubo = True
        im = lm.get("iman") or {}
        if im.get("lado"):
            L.append(f"   → imán de stops: {im['lado'].upper()} ({im.get('pct', '?')}%)")
        hubo = True
    pc = extras.get("poc")
    if isinstance(pc, dict) and cambio(est, "poc", pc.get("poc", 0), 50):
        try:
            cerca = abs(t["last"] - pc["poc"]) / t["last"] * 100
            tag = "pegado al " if cerca <= 0.3 else ""
            L.append(f"🎯 POC {tag}{fmt_miles(pc['poc'])} (área {fmt_miles(pc['val'])}–{fmt_miles(pc['vah'])})")
            hubo = True
        except Exception:
            pass
    dm = extras.get("dom")
    if isinstance(dm, dict) and dm.get("btc") is not None:
        prevd = None
        try:
            prevd = (est.get("deltas") or {}).get("dom_btc")
        except Exception:
            pass
        if cambio(est, "dom_btc", dm["btc"], 0.3):
            L.append(f"👑 DOMINANCIA BTC {dm['btc']}% (ETH {dm.get('eth', '?')}%) → {veredicto_dom(dm['btc'], prevd)}")
            hubo = True
    pr = extras.get("pres")
    if pr and cambio(est, "pres", pr["valor"], 10):
        L.append(f"📰 IMPACTO: {pr['txt']} → {acuerdo_tecnica(dirb['bias'], pr['valor'])}")
        hubo = True
    if not hubo:
        L.append("(mercado sin cambios desde tu último parte)")
    aut = extras.get("aut")
    if aut:
        L.append(f"🧠 AUTO: mejor {aut['mejor'][0]} ({aut['mejor'][1]}%) · peor {aut['peor'][0]} ({aut['peor'][1]}%) · n={aut['n']}")
    L.append("━━━━━ 📚 CONTEXTO ━━━━━")
    L.append("📰 NOTICIAS NUEVAS (no vistas):")
    _vistas = extras.get("vistas") or []
    _notis = notis or []
    frescas = [n for n in _notis if isinstance(n, dict) and str(n.get("titulo") or "").strip() and n.get("titulo") not in _vistas][:3]
    if frescas:
        for n in frescas:
            icono = '🔴' if n['score'] >= 9 else '🟡'
            L.append(f"  {icono} [{n['score']}] {n['titulo']}")
            L.append(f"     → {explicar_noticia(n.get('tags') or [])} · impacto {impacto_noticia(n.get('score') or 0)}")
    else:
        L.append("  (sin noticias nuevas desde tu último parte)")
    L.append("")
    L.append("🗓 PROXIMOS EVENTOS EE.UU.:")
    if evs:
        for e in evs[:3]:
            cuando_s = e['cuando'].strftime('%a %d %H:%M UTC')
            L.append(f"  📌 {e['titulo']} ({cuando_s}, {cuenta_regresiva(e['cuando'], ahora)})")
            L.append(f"     → {explicar_evento(e['titulo'])} · impacto {impacto_evento(e['impact'])}")
            sc = linea_escenario(e)
            if sc:
                L.append(f"     → {sc}")
    else:
        L.append("  (sin eventos fuertes esta semana)")
    L.append("Rangos ±% = ref. histórica. No es asesoramiento financiero.")
    try:
        _tca = tca_linea(extras.get("arrival"), t["last"])
        if _tca and "s/d" not in _tca:
            L.append(_tca)
    except Exception:
        pass
    try:
        L.append(linea_runbook())
    except Exception:
        pass
    try:
        _out = []
        for _ln in L:
            if _ln == "" and _out and _out[-1] == "":
                continue
            _out.append(_ln)
        return "\n".join(_out)
    except Exception:
        return "\n".join(L)


def _u16(s):
    """Longitud en unidades UTF-16 (lo que cuenta Telegram): emojis = 2."""
    try:
        return len(s.encode("utf-16-le")) // 2
    except Exception:
        return len(s or "")


def trocear(texto, limite=3900):
    """Parte un mensaje largo en trozos <= limite (en unidades UTF-16, que es como
    cuenta Telegram) sin romper lineas. Antes medía caracteres: muchos emojis podian
    superar 4096 unidades y Telegram devolvia 400 (alerta perdida)."""
    try:
        texto = str(texto or "")
    except Exception:
        texto = ""
    if not texto:
        return []
    partes = []
    for bloque in texto.split("\n"):
        while _u16(bloque) > limite:
            corte = bloque.rfind(" ", 0, limite)
            if corte < limite // 2 or _u16(bloque[:corte]) > limite:
                corte = limite
                while corte > 1 and _u16(bloque[:corte]) > limite:
                    corte -= 1
            partes.append(bloque[:corte])
            bloque = bloque[corte:].lstrip()
        if not partes or _u16(partes[-1]) + _u16(bloque) + 1 > limite:
            partes.append(bloque)
        else:
            partes[-1] += "\n" + bloque
    return [p for p in partes if p]


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        try:
            print(text)
        except UnicodeEncodeError:
            try:
                print(str(text).encode("ascii", "replace").decode("ascii"))
            except Exception:
                pass
        except Exception:
            pass
        try:
            with open("parte_cloud.txt", "w", encoding="utf-8") as fh:
                fh.write(str(text if text is not None else ""))
        except Exception:
            pass
        print("\n[modo local] Variables TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ausentes.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    import time as _t
    try:
        partes = trocear(text)
    except Exception:
        return False
    if not partes:
        return False
    for i, parte in enumerate(partes):
        txt = parte if i == 0 else "(sigue) " + parte
        try:
            payload = json.dumps({"chat_id": chat, "text": txt}, ensure_ascii=False).encode("utf-8", "replace")
        except Exception:
            return False
        ok = False
        for intento in range(3):
            try:
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    r.read()
                ok = True
                break
            except Exception as e:
                code = getattr(e, "code", None)
                if code in (400, 401, 403, 404):
                    break
                espera = 2 * (intento + 1)
                try:
                    body = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
                    m = re.search(r'"retry_after"\s*:\s*(\d+)', body)
                    if code == 429 and m:
                        espera = min(int(m.group(1)), 60)
                except Exception:
                    pass
                if intento < 2:
                    try:
                        _t.sleep(espera)
                    except Exception:
                        pass
        if not ok:
            return False
    return True


def guardia_lectura():
    """Protocolo de seguridad: el bot es SOLO lectura. Si alguien configura
    claves de trading por error, se niega a arrancar (fail-closed)."""
    for k in ("BINANCE_API_KEY", "BINANCE_API_SECRET", "TRADING_ENABLED", "BINGX_API_KEY"):
        if os.environ.get(k, "").strip():
            print(f"BLOQUEO DE SEGURIDAD: {k} configurada; este bot es solo-lectura. Saliendo.")
            raise SystemExit(2)
    return True


def main():
    guardia_lectura()
    _elegir_fuente()  # fija spot/futuros una sola vez para toda la pasada
    ahora = datetime.datetime.now(datetime.timezone.utc)
    try:
        t = ticker24()
        kl_h1 = klines("1h", 72)
        kl_h4 = klines("4h", 60)
        kl_d1 = klines("1d", 60)
        kl_w1 = klines("1w", 52)
        try:
            kl_m5 = klines("5m", 576)  # 48 h: niveles y toques de corto plazo
            if kl_m5 and kl_m5[-1]["t"] + datetime.timedelta(minutes=5) > ahora:
                kl_m5 = kl_m5[:-1]  # descartar la vela en curso
        except Exception:
            kl_m5 = None
        h1 = analyze(kl_h1, 60, "1H")
        h4 = analyze(kl_h4, 240, "4H")
        d1 = analyze(kl_d1, 1440, "1D")
        w1 = analyze(kl_w1, 10080, "1S")
        pd = pivots("1d", "D")
        pw = pivots("1w", "S")
        regimen = "tendencia" if h4.get("adx", 0) >= 20 else "rango"
        # chop = ruido puro: en ese estado el bot informa pero NO invita a entrar.
        _chop = (regimen_operativo(h1, h4) == "chop")
        if regimen == "rango":
            for _x in (h1, h4):
                _x["score"] = _x["score"] - _x.get("macd", 0)
        niv = niveles(h1, h4, d1, w1, pd, pw, t["last"])
        dirb = direccion(h1, h4, d1, w1)
        prox = proxima_sesion()
        senti = sentiment()
        fg = fear_greed(d1, senti, t["chg"])
        notis = noticias()
        # M1: una sola bajada del calendario. `evs` = solo futuros (para mostrar/avisar);
        # `_evs_cal` incluye las últimas 24 h para que el estudio de eventos no esté muerto.
        _evs_cal = calendario(limit=80, incluir_pasadas_h=48)
        evs = [e for e in _evs_cal if e.get("cuando") and e["cuando"] > ahora][:5]

        est, hist = cargar_estado()
        pide = bool(est.get("pide_detalle"))
        if pide:
            est["pide_detalle"] = False
        try:
            _vc = kl_h1[-2] if len(kl_h1) >= 2 else {}
            _rr = (niv.get("resistencias") or [{}])[0] or {}
            _ss = (niv.get("soportes") or [{}])[0] or {}
            evalua_zona(est, _rr.get("precio"), _ss.get("precio"),
                        _vc.get("h"), _vc.get("l"), _vc.get("c"))
        except Exception:
            pass
        es_dup = False
        try:
            if est.get("ultimo_run"):
                dt_run = (ahora - datetime.datetime.fromisoformat(est["ultimo_run"])).total_seconds()
                es_dup = 0 <= dt_run < 90
        except Exception:
            pass
        umbral = max(UMBRAL_MOV, (h1["atr"] / t["last"]) * UMBRAL_ATR_MULT) if t["last"] else UMBRAL_MOV
        try:
            _velas_ev = klines("1h", 220)
        except Exception:
            _velas_ev = None
        try:
            evaluar_mfe(est, ahora, _velas_ev)
        except Exception:
            pass
        try:
            # Las que el gate silencio se miden aparte: no son alertas enviadas.
            evaluar_mfe(est, ahora, _velas_ev, pend_key="pend_gate", log_key="eval_gate",
                        alza_key="alza_gate", baja_key="baja_gate", metodo="gate")
        except Exception:
            pass
        try:
            evaluar_sombra(est, ahora, _velas_ev)
        except Exception:
            pass
        try:
            evaluar_precision(est, ahora)
        except Exception:
            pass
        try:
            evaluar_todo(est, ahora, _velas_ev)
        except Exception:
            pass
        estudiar_eventos(est, hist, _evs_cal, ahora)
        mx = macro_ext()
        cb = coinbase_analisis(t.get("last"), t.get("vol"))
        sm = smart_money(t, h1, senti, notis, (cb or {}).get("prem"))
        bal = ballenas()
        foot = None  # footprint eliminado (era ruido); se mantiene la variable por compatibilidad
        if bal is None:
            try:
                _pb = est.get("last_bal") or {}
                _pbt = datetime.datetime.fromisoformat(str(_pb.get("t", "")))
                if _pbt.tzinfo is None:
                    _pbt = _pbt.replace(tzinfo=datetime.timezone.utc)
                _edh = (ahora - _pbt).total_seconds() / 3600
                if _edh < 6 and isinstance(_pb.get("bal"), dict):
                    bal = dict(_pb["bal"])
                    bal["txt"] = str(bal.get("txt", "")) + f" (hace {int(_edh)}h)"
            except Exception:
                pass
        try:
            if isinstance(bal, dict) and (bal.get("nb", 0) + bal.get("ns", 0)) > 0 and "(hace" not in str(bal.get("txt", "")):
                est["last_bal"] = {"t": ahora.isoformat(), "bal": {k: bal.get(k) for k in ("nb", "ns", "buys", "sells", "big", "txt")}}
        except Exception:
            pass
        ima = imanes(t["last"])
        oro = oro_vs_btc(t["chg"])
        lsr = ls_global()
        dom = dominancia()
        pres = presion_noticias(notis)
        dcvd = div_cvd()
        liqmap = mapa_liq(kl_h1, t["last"], senti["funding"])
        aut = auto_stats(est.get("eval_log", []))
        senti_viejo = ""
        if senti["funding"] is None and senti["taker"] is None and est.get("last_senti"):
            try:
                _ed = (ahora - datetime.datetime.fromisoformat(est["last_senti"]["t"])).total_seconds() / 3600
            except Exception:
                _ed = 99
            if _ed < 12:
                senti = {"funding": est["last_senti"].get("funding"), "oi": None,
                         "taker": est["last_senti"].get("taker")}
                senti_viejo = f" (hace {int(_ed)}h)"
        if senti["funding"] is not None or senti["taker"] is not None:
            est["last_senti"] = {"funding": senti["funding"], "taker": senti["taker"],
                                 "t": ahora.isoformat()}
        # --- RED NEURONAL (OPT-IN) ----------------------------------------------
        # Solo actua si VIGILANTE_NN=1. Reconstruye la ventana viva con las MISMAS
        # funciones del bot y reescribe dirb["bias"]/["confianza"] con la clase mas
        # probable (ALZA/BAJA/LATERAL). Si falta el modelo, onnxruntime o falla algo,
        # el bot sigue con su logica de siempre: no se rompe nada.
        if os.environ.get("VIGILANTE_NN", "0") not in ("", "0", "false", "False"):
            try:
                import nn_infer
                if not nn_infer.disponible():
                    print(nn_infer.info())
                else:
                    _bias_bot, _conf_bot = dirb["bias"], dirb["confianza"]
                    _basis = None
                    try:
                        _pi = fetch(f"{FAPI}/premiumIndex?symbol=BTCUSDT", tries=1)
                        _mp = float(_pi.get("markPrice") or 0)
                        _ix = float(_pi.get("indexPrice") or 0)
                        if _ix > 0:
                            _basis = (_mp - _ix) / _ix * 100.0
                    except Exception:
                        _basis = None
                    _mod = sys.modules.get(__name__)
                    if _mod is None or not hasattr(_mod, "analyze"):
                        import types
                        _mod = types.SimpleNamespace(analyze=analyze, niveles=niveles)
                    _ventana = nn_infer.ventana_vivo(
                        _mod, kl_h1, kl_h4, kl_d1, kl_w1, t["last"],
                        {"funding": senti.get("funding"), "taker": senti.get("taker")},
                        {"basis": _basis, "premium": (cb or {}).get("prem"), "niv": niv},
                        ahora)
                    if nn_infer.aplicar(dirb, _ventana):
                        _p = dirb["nn"]["probs"]
                        print(f"  red: {dirb['bias']} {dirb['confianza']}% "
                              f"(bot decia {_bias_bot} {_conf_bot}%) "
                              f"probs A/B/L={_p[0]:.2f}/{_p[1]:.2f}/{_p[2]:.2f}")
                    else:
                        print(nn_infer.info())
            except Exception as _enn:
                print(f"red neuronal omitida: {type(_enn).__name__}: {_enn}")
        macro_viejo = ""
        if mx is None and est.get("last_macro"):
            try:
                _ed2 = (ahora - datetime.datetime.fromisoformat(est["last_macro"]["t"])).total_seconds() / 3600
            except Exception:
                _ed2 = 99
            if _ed2 < 24 and est["last_macro"].get("mx"):
                mx = est["last_macro"]["mx"]
                macro_viejo = f" (hace {int(_ed2)}h)"
        if mx:
            est["last_macro"] = {"mx": mx, "t": ahora.isoformat()}
        # Confluencia del nivel mas cercano: solo informativa, NO cambia el grado.
        try:
            _c_res = confluencia_nivel(niv["resistencias"][0])
            _c_sup = confluencia_nivel(niv["soportes"][0])
            _d_res = abs(niv["resistencias"][0]["precio"] - t["last"])
            _d_sup = abs(t["last"] - niv["soportes"][0]["precio"])
            _confl = _c_res if _d_res <= _d_sup else _c_sup
        except Exception:
            _confl = 0
        grade = score_senal(dirb, h1, h4, regimen, confl=_confl)
        veto = hay_veto(dirb["bias"], (cb or {}).get("prem"), ((mx or {}).get("dxy") or {}).get("chg", 0))
        if veto and grade in ("A", "B"):
            grade = chr(ord(grade) + 2)
        bloqueo, motivo_bloq = blackout(evs, ahora)
        aviso_previo = preaviso(est, evs, ahora)
        try:
            edad_h = (ahora - kl_h1[-1]["t"]).total_seconds() / 3600 if kl_h1 else 99
        except Exception:
            edad_h = 99
        if edad_h > 1.25:
            est["stale_n"] = est.get("stale_n", 0) + 1
            guardar_estado(est, hist)
            if est["stale_n"] >= 3:
                send_telegram("⚠️ Datos desactualizados (velas viejas): revisa fuentes. No opero a ciegas.")
                est["stale_n"] = 0
                guardar_estado(est, hist)
            print(f"Datos viejos ({round(edad_h, 2)} h). Salto.")
            return
        est["stale_n"] = 0
        cvd_v = cvd()
        mov1h = None
        obj1h = (ahora - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        for h in reversed(hist):
            if h.get("t", "")[:16] <= obj1h and h.get("precio"):
                mov1h = round((t["last"] - h["precio"]) / h["precio"] * 100, 2)
                break
        mov30 = None
        obj30 = (ahora - datetime.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
        for h in reversed(hist):
            if h.get("t", "")[:16] <= obj30 and h.get("precio"):
                mov30 = round((t["last"] - h["precio"]) / h["precio"] * 100, 2)
                break
        hoy = ahora.strftime("%Y-%m-%d")
        mov_ny = None
        corte = hoy + "T13:30"
        for h in hist:
            if h.get("t", "")[:16] >= corte and h.get("precio"):
                mov_ny = round((t["last"] - h["precio"]) / h["precio"] * 100, 2)
                break
        try:
            _ln = liquidez_nivel(kl_h1, t["last"])
        except Exception:
            _ln = None
        liq = _ln["texto"] if _ln else None
        liq_plan = None
        try:
            if _ln and h1.get("atr"):
                _buf = 0.15 * h1["atr"]
                _stop_liq = (_ln["extremo"] + _buf) if _ln["lado"] == "max" else (_ln["extremo"] - _buf)
                liq_plan = plan_trade("short" if _ln["lado"] == "max" else "long",
                                      t["last"], niv, h1.get("atr"), stop=_stop_liq)
        except Exception:
            liq_plan = None
        poc = punto_control(kl_h1)
        try:
            fvg = fvgs_activos(kl_h1, kl_h4, t["last"])
        except Exception:
            fvg = None
        rup = ruptura(kl_h1, niv["soportes"][0]["precio"], niv["resistencias"][0]["precio"])
        try:
            # M3: solo velas CERRADAS (antes usaba la viva y la señal repintaba)
            qb = quiebre_estructura(kl_h1[:-1])
        except Exception:
            qb = None
        try:
            sl = sl_estructura(t["last"], (qb or {}).get("dir"), (qb or {}).get("swing"), h1.get("atr")) if qb else None
        except Exception:
            sl = None
        try:
            _mr = mecha_rechazo((kl_h1 or [])[:-1])
            mecha = None
            slm = None
            if isinstance(_mr, dict):
                if _mr["dir"] == "ALZA" and t["last"] > _mr["mid"]:
                    mecha = _mr
                    slm = sl_estructura(t["last"], "ALZA", _mr["nivel"], h1.get("atr"))
                elif _mr["dir"] == "BAJA" and t["last"] < _mr["mid"]:
                    mecha = _mr
                    slm = sl_estructura(t["last"], "BAJA", _mr["nivel"], h1.get("atr"))
        except Exception:
            mecha = None
            slm = None
        pila = None
        pila_key = None
        try:
            zonas = zonas_pilas(pw, d1, w1, t["last"], ima)
            texto, key = mensaje_pila(zonas, t["last"], niv["soportes"], niv["resistencias"], h1, h4, ahora.hour)
            if texto and est.get("pilas", {}).get(key) != hoy and lado_ok(dirb["bias"], texto):
                pila = texto
                pila_key = key
        except Exception:
            pila = None
        forzado = None
        vivas = []
        for a in est.get("mis_alertas", []):
            try:
                hit = (a["dir"] == "sube" and t["last"] >= a["precio"]) or (a["dir"] == "baja" and t["last"] <= a["precio"])
                if hit and forzado is None:
                    verbo = "llegó a" if a["dir"] == "sube" else "cayó a"
                    forzado = f"Tu alerta: BTC {verbo} {fmt_miles(a['precio'])}"
                elif not hit:
                    vivas.append(a)
            except Exception:
                continue
        est["mis_alertas"] = vivas
        abiertas, cierres = journal_check(est.get("ops", []), kl_h1, t["last"])
        est["ops"] = abiertas
        if cierres:
            journal = est.get("journal", [])
            for cc in cierres:
                journal.append({"dir": cc["dir"], "res": cc["res"], "r": cc["r"], "t": ahora.isoformat()})
            est["journal"] = journal[-50:]
        sims_ab, sims_ci = journal_check(est.get("sim_abiertas", []), kl_h1, t["last"])
        est["sim_abiertas"] = sims_ab
        if sims_ci:
            sc = est.get("sim_cerradas", [])
            for cc in sims_ci:
                sc.append({"dir": cc["dir"], "res": cc["res"], "r": cc["r"], "t": ahora.isoformat()})
                send_telegram(f"🔬 Simulada cerrada: {cc['dir']} {cc['res']} ({cc['r']:+.1f}R). Sin dinero, solo aprendizaje.")
                print(f"  simulada cerrada {cc['dir']} {cc['res']}")
            est["sim_cerradas"] = sc[-20:]
        # GESTION: BE/trailing de ops abiertas (las del usuario, no señales).
        gestion_txt = None
        try:
            _atr1 = h1.get("atr")
            for _llave in ("ops", "sim_abiertas"):
                _lista = est.get(_llave, [])
                if not isinstance(_lista, list):
                    continue
                for _o in _lista:
                    if not isinstance(_o, dict):
                        continue
                    _r, _acc, _nsl = gestion_sl(_o, t["last"], _atr1, regimen)
                    if _acc == "BE":
                        try:
                            _o["risk0"] = abs(float(_o["entrada"]) - float(_o["stop"]))
                        except Exception:
                            pass
                        _o["be_done"] = True
                        _o["stop"] = _nsl
                        gestion_txt = (f"🔒 BE: {_o.get('dir')} {fmt_miles(_o.get('entrada'))} → {fmt_miles(t['last'])} "
                                       f"({_r:+.1f}R). Mueve SL a {fmt_miles(_nsl)} (entrada).")
                        break
                    if _acc == "TRAIL":
                        if _o.get("trail_lock") == _nsl:
                            continue
                        _o["trail_lock"] = _nsl
                        _o["stop"] = _nsl
                        gestion_txt = (f"🔒 TRAIL: {_o.get('dir')} {fmt_miles(_o.get('entrada'))} → {fmt_miles(t['last'])} "
                                       f"({_r:+.1f}R). Traba +1R en {fmt_miles(_nsl)}.")
                        break
                if gestion_txt:
                    break
        except Exception:
            gestion_txt = None
        # PAPEL XLX: revisa cierres con la ultima vela 1H + ticker (invisible, sin avisos)
        abiertas_p = []
        for o in est.get("paper_abiertas", []):
            try:
                ref_h, ref_l = ref_rango(kl_h1, o.get("t"))
                fin = cierre_papel(o, ref_h, ref_l, t["last"])
                if fin:
                    px, donde, pnl = fin
                    banco = float(est.get("banco", PAPER_BANCO)) + pnl
                    est["banco"] = round(banco, 2)
                    cerr = est.get("paper_cerradas", [])
                    cerr.append({"dir": o["dir"], "res": donde, "pnl": round(pnl, 2),
                                 "r": round(pnl / o["riesgo"], 2) if o["riesgo"] else 0,
                                 "t": ahora.isoformat()})
                    est["paper_cerradas"] = cerr[-100:]
                    pdh = est.get("paper_dia") or {}
                    if pdh.get("fecha") != ahora.strftime("%Y-%m-%d"):
                        pdh = {"fecha": ahora.strftime("%Y-%m-%d"), "pnl": 0.0}
                    pdh["pnl"] = round(pdh.get("pnl", 0) + pnl, 2)
                    est["paper_dia"] = pdh
                else:
                    abiertas_p.append(o)
            except Exception:
                continue
        est["paper_abiertas"] = abiertas_p
        hist.append({"t": ahora.isoformat(), "precio": round(t["last"]),
                     "bias": dirb["bias"], "conf": dirb["confianza"], "fg": fg["valor"],
                     "fund": senti["funding"], "taker": senti["taker"],
                     "res": niv["resistencias"][0]["precio"], "sup": niv["soportes"][0]["precio"],
                     "grade": grade})

        calib = calibrar(est)
        est["calib"] = calib
        f_ses = calib.get(sesion_bucket(ahora.hour), 1.0)
        uf = UMBRAL_CONF_FUERTE * f_ses
        uc = UMBRAL_CONF_CAMBIO * f_ses
        try:
            cools_antes = dict(est.get("cools") or {})
        except Exception:
            cools_antes = {}
        _snap_run = est.get("ultimo_run")
        _snap_lat = est.get("latido")
        _snap_preny = est.get("ultimo_preny")
        _snap_man = est.get("ultimo_resumen")
        _snap_noc = est.get("ultimo_resumen_noche")
        _snap_mad = est.get("ultimo_madrugada")
        try:
            import copy as _cp
            _snap_ual = _cp.deepcopy(est.get("ultima_alerta"))
        except Exception:
            _snap_ual = est.get("ultima_alerta")
        try:
            _atr1 = h1.get("atr") or 0
            _ema1 = h1.get("ema20") or 0
            _rsi1 = h1.get("rsi", 50)
            estir = None
            if _atr1 > 0 and _ema1 > 0:
                _dx = (t["last"] - _ema1) / _atr1
                if _dx <= -2.0 and _rsi1 < 35:
                    estir = f"bajo media {_dx:.1f}×ATR (RSI {_rsi1:.0f})"
                elif _dx >= 2.0 and _rsi1 > 65:
                    estir = f"sobre media +{_dx:.1f}×ATR (RSI {_rsi1:.0f})"
        except Exception:
            estir = None
        enviar, motivo, tipo = decidir_alerta(t["last"], niv, dirb, est, ahora, forzado, mov1h, regimen, bloqueo, motivo_bloq, mov_ny, liq, pila, uf, uc, mov30, rup, qb, sl, gestion_txt, mecha, slm, estir, foot, umbral=umbral, atr=h1.get("atr"), liq_plan=liq_plan, chop=_chop)
        # Capa 1: toques multiples (contexto, no entrada). Solo si no hay otro
        # mensaje programado (manana/noche/preny) para no pisarlo.
        if (not es_dup) and kl_m5 and not (enviar and tipo != "alerta"):
            _toques_multi = detectar_toques_multiples(kl_m5, t["last"], ahora, est, niv=niv)
            if _toques_multi:
                if enviar and tipo == "alerta":
                    motivo = motivo + "\n" + _toques_multi
                else:
                    enviar, motivo, tipo = True, _toques_multi, "alerta"
        _motivo_alerta = motivo
        _tipo_alerta = tipo_de_motivo(motivo)
        _dir_alerta = direccion_alerta(motivo, dirb["bias"])
        if (not es_alerta_direccional(motivo)) or _tipo_alerta not in DIRECCIONES_MEDIBLES:
            _dir_alerta = None
        gate = cargar_gate_validacion()
        motor = cargar_motor_nuevo()
        enviar, motivo, tipo, gate_blocked = aplicar_gate_alerta(
            enviar, motivo, tipo, gate, forzado=forzado, gestion=gestion_txt
        )
        if gate_blocked:
            print(f"Gate validacion: alerta direccional silenciada ({gate.get('reason', 'sin evidencia')}).")
            # Contrafactual: medir la alerta silenciada con la misma regla que las
            # enviadas. Sirve para saber si el gate protege o si esta bloqueando
            # señales buenas; nunca se envia ni se mezcla con el scoreboard vivo.
            registrar_pend_gate(est, ahora, t["last"], dirb, _dir_alerta,
                                _tipo_alerta, _motivo_alerta,
                                gate.get("reason", "sin evidencia"), umbral,
                                h1, h4, senti, fg)
        hist[-1]["motivo"] = motivo
        hist[-1]["tipo"] = tipo
        if gate_blocked:
            hist[-1]["motivo_bloqueado"] = _motivo_alerta
        fresco = est.get("runs", 0) == 0
        est["runs"] = est.get("runs", 0) + 1
        res = niv["resistencias"][0]
        sup = niv["soportes"][0]

        est["ultimo_bias"] = dirb["bias"]
        est["ultima_conf"] = dirb["confianza"]
        try:
            precio_ant = est.get("ultimo_precio")
        except Exception:
            precio_ant = None
        est["ultimo_precio"] = round(t["last"])
        est["ultimo_run"] = ahora.isoformat()
        est["latido"] = ahora.isoformat()
        if enviar and tipo == "alerta":
            est["ultima_alerta"] = {"t": ahora.isoformat(), "motivo": motivo,
                                    "precio": round(t["last"]), "bias": dirb["bias"],
                                    "conf": dirb["confianza"]}
        if tipo == "manana":
            est["ultimo_resumen"] = f"{hoy}-manana"
        elif tipo == "noche":
            est["ultimo_resumen_noche"] = hoy
        elif tipo == "preny":
            est["ultimo_preny"] = hoy
        elif tipo == "madrugada":
            est["ultimo_madrugada"] = hoy
        # Veto z-score: no registrar senal si el precio esta estirado (|z|>=2) -> no perseguir.
        _z1 = h1.get("z") if isinstance(h1, dict) else None
        _z_ok = (_z1 is None) or (abs(_z1) < 2)
        # Puerta dura: no registrar senal si veto institucional o blackout activo.
        _veto_ok = True
        if os.environ.get("VIGILANTE_FILTRO_VETO", "1") not in ("", "0", "false", "False"):
            _veto_ok = (not bloqueo) and (not veto)
        # Confluencia: registrar solo si hay grado B+ o evidencia (liquidez/ruptura/mecha/PILAS).
        _conf_ok = True
        if os.environ.get("VIGILANTE_FILTRO_CONFLUENCIA", "1") not in ("", "0", "false", "False"):
            _conf_ok = (grade in ("A", "B")) or bool(liq) or bool(rup) or bool(mecha) or bool(pila)
        # Toque real obligatorio (flag opt-in): solo registrar si hubo toque de nivel/liquidez/ruptura/mecha.
        _toque_ok = True
        if os.environ.get("VIGILANTE_SOLO_TOQUE", "0") not in ("", "0", "false", "False"):
            _toque_ok = bool(liq) or bool(rup) or bool(mecha) or bool(pila)
        # Medir la direccion REAL del plan (no el sesgo del bot). Una alerta de
        # VENTA con sesgo ALZA se evalua como BAJA; un aviso de contexto no entra.
        _medible = es_alerta_direccional(motivo)
        if enviar and tipo == "alerta" and _dir_alerta in ("ALZA", "BAJA") and _medible and _z_ok and _veto_ok and _conf_ok and _toque_ok:
            reciente = False
            for p in est.get("pendientes", []):
                try:
                    _pd = p.get("dir") or direccion_alerta(p.get("motivo", ""), p.get("bias")) or p.get("bias")
                    if _pd == _dir_alerta and (ahora - datetime.datetime.fromisoformat(p["t"])).total_seconds() / 3600 < DEDUP_HORAS:
                        reciente = True
                        break
                except Exception:
                    continue
            if not reciente:
                est["pendientes"] = est.get("pendientes", []) + [
                    {"t": ahora.isoformat(), "precio": round(t["last"]),
                     "bias": dirb["bias"], "dir": _dir_alerta,
                     "conf": dirb["confianza"], "tipo": _tipo_alerta,
                     "motivo": motivo[:200],
                     "risk": round(umbral * t["last"], 1),
                     "feat": {"rsi": h1["rsi"], "adx": h4.get("adx", 0),
                              "fund": senti["funding"], "taker": senti["taker"],
                              "fg": fg["valor"]}}]
        # PAPEL: opera señales B (35%+) aunque la alerta pida A (45%+). Aprende sin spamear.
        if puede_papel(est, dirb["bias"], dirb["confianza"], ahora):
            # PAPEL INTERNO (invisible): abre virtual con frenos institucionales
            pos = abrir_papel(est, dirb, niv, t["last"], ahora)
            if pos:
                est["paper_ult"] = {"dir": dirb["bias"], "t": ahora.isoformat()}
        # SOMBRA (invisible): mide TODA señal con sesgo, sin pisos ni frenos.
        try:
            abrir_sombra(est, dirb["bias"], dirb["confianza"], t["last"], umbral, ahora)
        except Exception:
            pass
        # TODO (invisible): mide CADA pasada hable o calle, para saber si callar fue correcto.
        try:
            abrir_todo(est, dirb["bias"], dirb["confianza"], t["last"], umbral, ahora)
        except Exception:
            pass
        guardar_estado(est, hist)

        # Scoreboard semanal (domingo 12:00 UTC): acierto real por tipo, no promesas.
        try:
            if ahora.weekday() == 6 and ahora.hour == 12 and est.get("ultimo_score") != hoy:
                _txt_sb = texto_scoreboard(est.get("eval_log", []), min_n=5, solo_plan=True)
                if _txt_sb:
                    send_telegram("🗓️ SCOREBOARD SEMANAL (señales direccionales)\n" + _txt_sb +
                                  "\nSin promesas: es lo que pasó, no lo que va a pasar.")
                est["ultimo_score"] = hoy
                guardar_estado(est, hist)
        except Exception:
            pass

        ctx = {"t": t, "dirb": dirb, "niv": niv, "fg": fg, "est": est,
               "h1": h1, "h4": h4, "d1": d1, "w1": w1, "senti": senti,
               "notis": notis, "evs": evs, "ahora": ahora, "cb": cb, "smart": sm, "aut": aut,
               "grade": grade, "regimen": regimen, "bloqueo": bloqueo, "pres": pres,
               "confl": _confl, "motor": motor}
        try:
            cmds, new_off = leer_comandos(est.get("offset", 0))
        except Exception:
            cmds, new_off = [], est.get("offset", 0)
        if new_off != est.get("offset", 0):
            est["offset"] = new_off
            guardar_estado(est, hist)
        for cc in cierres:
            send_telegram("📓 " + cc["txt"])
        if not fresco:
            print(f"Comandos pendientes: {len(cmds)}")
            for cm in cmds:
                r, d = responder_comando(cm, ctx)
                if r:
                    send_telegram("💬 " + cm["texto"] + "\n" + r)
                    print(f"  respondido {cm['texto']} (chat {cm['chat']})")
                else:
                    print(f"  ignorado {cm['texto']} (chat {cm['chat']})")

        try:
            _tags = etiquetar_senal(senti, ahora.hour, dcvd)
        except Exception:
            _tags = {}
        est["snapshot"] = {
            "t": ahora.isoformat(),
            "precio": t["last"], "chg": t["chg"], "hi": t["hi"], "lo": t["lo"],
            "bias": dirb["bias"], "conf": dirb["confianza"], "grade": grade, "regimen": regimen,
            "confl": _confl,
            "tf": {k: {"tend": x["tend"], "rsi": x["rsi"], "macd": x["macd"], "score": x["score"],
                         "er": x.get("er"), "z": x.get("z")}
                   for k, x in (("h1", h1), ("h4", h4), ("d1", d1), ("w1", w1))},
            "niv": {"sop": niv["soportes"], "res": niv["resistencias"]},
            "fg": {"valor": fg["valor"], "etiqueta": fg["etiqueta"]},
            "senti": {"funding": senti["funding"], "taker": senti["taker"]},
            "notis": [{"titulo": n["titulo"], "score": n["score"]} for n in notis[:5]],
            "evs": [{"titulo": e["titulo"], "cuando": e["cuando"].isoformat(), "impact": e["impact"]} for e in evs[:5]],
            "pres": pres,
            "smart": ({"inst": sm["inst"], "ret": sm["ret"], "veredicto": sm["veredicto"]} if sm else None),
            "bal": ({"nb": bal.get("nb", 0), "ns": bal.get("ns", 0), "buys": bal.get("buys", 0),
                     "sells": bal.get("sells", 0), "big": bal.get("big", 0), "txt": bal.get("txt", "")}
                    if isinstance(bal, dict) else None),
            "poc": poc if isinstance(poc, dict) else None,
            "fvg": fvg,
            "qb": qb if isinstance(qb, dict) else None,
            "sl": list(sl) if isinstance(sl, (list, tuple)) else None,
            "mecha": mecha if isinstance(mecha, dict) else None,
            "slm": list(slm) if isinstance(slm, (list, tuple)) else None,
            "dom": dom if isinstance(dom, dict) else None,
            "liqmap": ({"arriba": liqmap.get("arriba", [])[:5],
                        "abajo": liqmap.get("abajo", [])[:5],
                        "iman": liqmap.get("iman")} if isinstance(liqmap, dict) else None),
            "evstudy": {f: {"avg": round(sum(a) / len(a), 2), "n": len(a)}
                        for f, a in ((est.get("ev_study", {}) or {}).items()) if a},
            "gate": {"n": len(est.get("eval_gate", []) or []),
                     "hit": sum(1 for e in (est.get("eval_gate", []) or [])
                                if isinstance(e, dict) and float(e.get("r", 0) or 0) > 0),
                     "pending": len(est.get("pend_gate", []) or [])},
            "metodo_eval": "plan",
            "tags": _tags,
        }
        guardar_estado(est, hist)
        if gate_blocked and est.get("gate_aviso") != hoy:
            try:
                if send_telegram(
                    "🔇 Alerta direccional silenciada.\n"
                    f"La validación todavía no permite señales: {gate.get('reason', 'sin evidencia')}.\n"
                    f"Medición: {resumen_medicion(est)}.\n"
                    "Sigo midiendo; no convierto confianza en entrada."
                ):
                    est["gate_aviso"] = hoy
                    guardar_estado(est, hist)
            except Exception:
                pass
        forzar = (any(cm.get("texto") == "/detalle" for cm in cmds) if not fresco else False) or pide
        if forzar:
            motivo, tipo, enviar = "Detalle pedido", "alerta", True
        # FIX BUG1: envío centralizado del preaviso High 15-60min.
        # Debe salir aunque no haya señal principal (enviar=False).
        # La marca preavisos solo se pone tras envío real, nunca al calcularlo.
        try:
            if aviso_previo and not es_dup:
                try:
                    send_telegram(aviso_previo)
                except Exception:
                    pass
                try:
                    marcar_preaviso(est, evs, ahora)
                    try:
                        guardar_estado(est, hist)
                    except Exception:
                        pass
                except Exception:
                    pass
                try:
                    print("Pre-evento enviado")
                except Exception:
                    pass
                aviso_previo = None
        except Exception:
            pass
        # AVISO DE PRECISION (nivel defendido): mensaje propio, corto, sin plan.
        # Condiciones para salir (todas): modo activo, no duplicado, motor fresco,
        # nivel que califica, sin deriva de regimen y con evidencia OOS local.
        try:
            if PRECISION_MODO and not es_dup:
                _der = deriva_regimen()
                if _der == "alert":
                    print("Aviso de precision omitido: deriva de regimen (validation.json).")
                else:
                    _mot = cargar_motor_full()
                    _niv = nivel_precision(_mot, t["last"]) if _mot else None
                    _ev = precision_evidencia()
                    if _niv and _ev and precision_nueva(est, _niv, ahora):
                        _txt = texto_alerta_precision(_niv, t["last"], _ev)
                        if send_telegram(_txt):
                            registrar_pend_precision(est, _niv, ahora)
                            print(f"  aviso de precision enviado: {_niv['nivel']} "
                                  f"({_niv['lado']}) p={_niv['prob']}")
                            try:
                                guardar_estado(est, hist)
                            except Exception:
                                pass
        except Exception:
            pass
        if not enviar:
            print(f"Sin alerta ({motivo}). Estado e historial guardados.")
            return
        if es_dup and not forzar:
            try:
                est["cools"] = cools_antes
                if _snap_run is None:
                    est.pop("ultimo_run", None)
                else:
                    est["ultimo_run"] = _snap_run
                if _snap_lat is None:
                    est.pop("latido", None)
                else:
                    est["latido"] = _snap_lat
                est["ultimo_preny"] = _snap_preny
                est["ultimo_resumen"] = _snap_man
                est["ultimo_resumen_noche"] = _snap_noc
                est["ultimo_madrugada"] = _snap_mad
                guardar_estado(est, hist)
            except Exception:
                pass
            print("Duplicado (<90 seg desde la ultima pasada). Comandos respondidos, parte omitido.")
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
        else:
            intro = "Cerramos el día: esto fue lo importante."
        memoria = []
        if veto:
            memoria.append("veto institucional: premium USA + dólar en contra (calidad degradada)")
        if tipo == "alerta" and motivo.startswith("Tocando"):
            nivel = res["precio"] if "resistencia" in motivo else sup["precio"]
            n = toques_hoy(hist, nivel, ahora)
            if n >= 2:
                memoria.append(f"ya tocó ese nivel {n} veces hoy: cada toque lo debilita")
        va = vs_ayer(hist, t["last"], ahora)
        if va is not None:
            memoria.append(f"vs ayer a esta hora: {va:+.2f}%")
        bj = sum(1 for h in hist if isinstance(h, dict) and h.get("tipo") == "alerta"
                 and str(h.get("t", ""))[:10] == hoy
                 and ("BAJISTA" in str(h.get("motivo", "")) or "PISO" in str(h.get("motivo", ""))
                      or "bajo mínimos" in str(h.get("motivo", "")) or "Ritmo acelerado -" in str(h.get("motivo", ""))))
        bl = sum(1 for h in hist if isinstance(h, dict) and h.get("tipo") == "alerta"
                 and str(h.get("t", ""))[:10] == hoy
                 and ("ALCISTA" in str(h.get("motivo", "")) or "TECHO" in str(h.get("motivo", ""))
                      or "sobre máximos" in str(h.get("motivo", "")) or "Ritmo acelerado +" in str(h.get("motivo", ""))))
        if bj + bl > 0:
            memoria.append(f"presión del día: {bj} avisos bajistas / {bl} alcistas")
        er1 = h1.get("er")
        if er1 is not None and er1 >= 0.5:
            memoria.append(f"eficiencia {er1}: el 1H va a alguna parte (tendencia real)")
        elif er1 is not None and er1 <= 0.15:
            memoria.append(f"eficiencia {er1}: puro ruido en 1H (chop, no persigas)")
        z1 = h1.get("z")
        if z1 is not None and abs(z1) >= 2:
            memoria.append(f"estirado {z1:+}σ sobre media 20H: no persigas la vela")
        pu, pdn = psico(t["last"])
        memoria.append(f"psicológicos: {fmt_miles(pu)} (+{round((pu - t['last']) / t['last'] * 100, 2)}%) / {fmt_miles(pdn)} ({round((pdn - t['last']) / t['last'] * 100, 2)}%)")
        rt = retest(kl_h1, res, sup, t["last"])
        if rt:
            memoria.append(rt)
        if liq:
            memoria.append("toma de liquidez: " + liq)
        div = divergencia(kl_h1)
        if div and div != est.get("div1h"):
            memoria.append(f"nueva divergencia {div} en RSI 1H: posible giro")
        est["div1h"] = div
        if dcvd and dcvd != est.get("divcvd"):
            memoria.append("divergencia CVD " + dcvd)
        est["divcvd"] = dcvd
        if tipo == "noche":
            hy = [h for h in hist if isinstance(h, dict) and str(h.get("t", ""))[:10] == hoy]
            na = sum(1 for h in hy if h.get("tipo") == "alerta")
            pdh = est.get("paper_dia") or {}
            tc0 = tabla_calibracion(est.get("eval_log", []))
            cal0 = (f"mi tino: {tc0['n']} evaluadas, Brier {tc0['brier']}" if tc0
                    else "aún sin evaluadas: aprendo en silencio")
            memoria.append(f"auto-revisión: hoy {len(hy)} pasadas y {na} alertas; "
                           f"papel del día {pdh.get('pnl', 0):+.0f} USDT; {cal0}; "
                           f"{len(est.get('pendientes', []))} señales en seguimiento")
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
        # M6/M5: no marcar las noticias como vistas HASTA que el envío tenga éxito
        # (más abajo, tras send ok). Así la sección "NOTICIAS NUEVAS" sí las muestra
        # y, si el envío falla, no se pierden (se reintentan en la pasada siguiente).
        nuevas = [n for n in notis if n.get("titulo") not in est.get("vistas", [])][:2]
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
            ini = (ahora - datetime.timedelta(hours=24)).isoformat()
            ps = [h["precio"] for h in hist if h.get("t", "") >= ini and h.get("precio")]
            bs = [h["bias"] for h in hist if h.get("t", "") >= ini and h.get("bias")]
            if ps:
                dom = max(set(bs), key=bs.count) if bs else "?"
                memoria.append(f"tu día: máx {fmt_miles(max(ps))}, mín {fmt_miles(min(ps))}, sesgo dominante {dom}")
            if evs:
                memoria.append("mañana vigilo: " + ", ".join(e["titulo"] for e in evs[:2]))
        extras = {"intro": intro,
                  "arrival": precio_ant if isinstance(precio_ant, (int, float)) else est.get("ultimo_precio"),
                  "narrativa": narrar(dirb, h1, h4, d1, res, sup, t["last"]),
                  "memoria": memoria,
                  "plan": plan_entrada(dirb, niv, evs, ahora),
                  "fflag": funding_flag(senti),
                  "nuevas": nuevas,
                  "mov_ny": mov_ny,
                  "grade": grade,
                  "regimen": regimen,
                  "motor": motor,
                  "cvd_v": cvd_v,
                  "macro": {"mx": mx, "lectura": lectura_macro(mx)},
                  "senti_viejo": senti_viejo,
                  "macro_viejo": macro_viejo,
                  "cb": cb,
                  "smart": sm,
                  "bal": bal,
                  "ima": ima,
                  "oro": oro,
                  "lsr": lsr,
                  "dom": dom,
                  "aut": aut,
                  "liqmap": liqmap,
                  "poc": poc,
                  "fvg": fvg,
                  "pres": pres,
                  "vistas": list(est.get("vistas", []))}
        # (preaviso ya enviado de forma centralizada arriba, incluso sin señal principal)
        msg = build_parte(t, h1, h4, d1, w1, niv, dirb, prox, senti, fg, est, motivo, tipo, notis, evs, ahora, extras)
        ok = send_telegram(msg)
        print("Enviado OK" if ok else "NO enviado (modo local)")
        if not ok:
            try:
                est["cools"] = cools_antes
                est["ultimo_preny"] = _snap_preny
                est["ultimo_resumen"] = _snap_man
                est["ultimo_resumen_noche"] = _snap_noc
                est["ultimo_madrugada"] = _snap_mad
                est["ultima_alerta"] = _snap_ual
                guardar_estado(est, hist)
            except Exception:
                pass
        if ok:
            hist[-1]["enviado"] = True
            est["vistas"] = (est.get("vistas", []) + [n["titulo"] for n in notis])[-30:]
            try:
                if pila and pila_key and motivo == pila:
                    est.setdefault("pilas", {})[pila_key] = hoy
            except Exception:
                pass
            guardar_estado(est, hist)
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
