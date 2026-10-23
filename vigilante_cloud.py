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
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

# --- Fase 1 modularizacion: matematicas puras en vigilante/indicadores.py ---
_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)
from vigilante.indicadores import (  # noqa: E402,F401  (re-export: API publica)
    ema_series,
    ema,
    rsi,
    slope,
    atr,
    adx,
    atr_regime,
    mecha_rechazo,
    quiebre_estructura,
    sl_estructura,
    structure,
    detect_swings,
    swings_idx,
    find_swing_points,
    find_equal_levels,
    clamp,
    eficiencia,
    zscore,
    fmt_miles,
    sesion_hora,
    sesion_bucket,
    es_alerta_direccional,
    tipo_de_motivo,
    direccion_alerta,
    num_txt,
    validar_velas,
    latido_tarde,
)
from vigilante.estado import (  # noqa: E402,F401  (re-export: API publica)
    cambio,
    enfriar,
    cargar_estado,
    _podar_estado,
    guardar_estado,
    ESTADO_FILE,
    HIST_FILE,
    MAX_HIST,
    MAX_PEND_TODO,
    MAX_EVAL_TODO,
    MAX_PAPER_ABIERTAS,
    MAX_OPS,
    MAX_DELTAS,
)
from vigilante.toques import (  # noqa: E402,F401  (re-export: API publica)
    pivotes_micro,
    toques_en_nivel,
    _ema_ultimo,
    _std_muestral,
    features_toque,
    score_toque,
    detectar_toques_multiples,
    MODELO_TOQUES,
    UMBRAL_TOQUE,
)
from vigilante.red import (  # noqa: E402,F401  (re-export: API publica)
    _elegir_fuente,
    fetch,
    klines,
    ticker24,
    sentiment,
    FAPI,
    FDATA,
    VISION,
    FUENTE,
    MERCADO,
)
from vigilante.mercado import (  # noqa: E402,F401  (re-export: API publica)
    macro_ext,
    yahoo_cierres,
    lectura_macro,
    coinbase_premium,
    coinbase_analisis,
    cb_veredicto,
    smart_money,
    dominancia,
    veredicto_dom,
    ls_global,
    oro_vs_btc,
    ballenas,
    cvd,
    div_cvd,
    mapa_liq,
    punto_control,
    _atr_serie,
    fvg_velas,
    fvgs_cercanos,
    fvgs_activos,
    texto_fvg,
    retest,
    ruptura,
    liquidez_nivel,
    liquidez,
    divergencia,
    zonas_pilas,
    mensaje_pila,
    prob_reaccion,
    etiquetar_senal,
    lado_ok,
    psico,
    snap_nivel,
    UMBRAL_BALLENA,
    UMBRAL_RUPTURA_MIN,
    UMBRAL_RUPTURA_ESTRICTO,
    REAC_BASE,
    REAC_TAB,
)
from vigilante.paper import (  # noqa: E402,F401
    racha_perdidas,
    perdon_bloqueo,
    puede_papel,
    kelly_half,
    sharpe,
    abrir_papel,
    cierre_papel,
    ref_rango,
    journal_check,
    gestion_sl,
    PAPER_BANCO,
    PAPER_LEV,
    PAPER_RIESGO,
    UMBRAL_PAPEL,
)
from vigilante.alertas import (  # noqa: E402,F401
    plan_trade,
    texto_plan,
    hay_veto,
    score_senal,
    blackout,
    decidir_alerta,
    plan_entrada,
    funding_flag,
    MIN_RR_ALERTA,
    MAX_STOP_ATR,
    BLACKOUT_MIN,
    FUNDING_EXTREMO,
    FEE_PCT,
    FILTRO_VOL,
    UMBRAL_CONF_FUERTE,
    UMBRAL_CONF_CAMBIO,
    UMBRAL_CONF_SENAL,
    UMBRAL_BRUSCO,
    UMBRAL_RITMO,
    UMBRAL_DIA_NY,
    cuenta_regresiva,
)
from vigilante.precision import (  # noqa: E402,F401
    _gate_desde_validacion,
    cargar_gate_validacion,
    cargar_motor_nuevo,
    linea_motor,
    cargar_motor_full,
    precision_evidencia,
    nivel_precision,
    precision_nueva,
    texto_alerta_precision,
    registrar_pend_precision,
    evaluar_precision,
    deriva_regimen,
    precision_stats,
    aplicar_gate_alerta,
    GATE_FILE,
    MOTOR_FILE,
    BT_FILE,
    VALIDATION_FILE,
    PRECISION_MIN_PROB,
    PRECISION_MIN_CALIDAD,
    PRECISION_MIN_TOQUES,
    PRECISION_MAX_EDAD_MIN,
    PRECISION_CERCA_PCT,
    PRECISION_DEDUP_HORAS,
    PRECISION_EVAL_HORAS,
)
from vigilante.medicion import (  # noqa: E402,F401
    resumen_medicion,
    precision_plan,
    tabla_calibracion,
    auto_stats,
    calibrar,
    registrar_pend_gate,
    evaluar_mfe,
    abrir_todo,
    evaluar_todo,
    abrir_sombra,
    evaluar_sombra,
    EVAL_HORAS,
    DEDUP_HORAS,
    SEMILLA_SESION,
    UMBRAL_MOV,
)
from vigilante.analisis import (  # noqa: E402,F401
    analyze,
    pivots,
    niveles,
    fuentes_nivel,
    confluencia_nivel,
    regimen_operativo,
    direccion,
    fear_greed,
    ficha_zona,
    evalua_zona,
    proxima_sesion,
)

VERSION = "v6"

# Fuente de mercado: se fija UNA vez por pasada para que precio y velas vengan
# del mismo sitio. Antes cada llamada hacia su propio fallback y una pasada podia
# quedar con klines de futuros y ticker de spot (mezcla inconsistente).



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








# F6: anti "ruptura de chop". Una ruptura confirmada DEBE tener la vela en la
# direccion del break (roja=bajista, verde=alcista), cruzar el nivel de verdad
# (la vela previa cerraba al otro lado) y superar un margen minimo. Evita cantar
# "ruptura BAJISTA" cuando el soporte mas cercano sube pegado al precio en subida.
UMBRAL_ATR_MULT = 0.5    # acierto = moverse >= 0.5 * ATR 1H a favor (relativo al mercado)
MIN_SENALES = 5          # minimo de senales para mostrar % de precision












# ---------------- Modo PRECISION: avisos de nivel defendido -----------------
# Solo avisa cuando el motor 4h marca un nivel con aguante medido alto
# (hold_prob alto, 3+ toques reales, calidad alta, sin quiebre confirmado) y el
# precio esta cerca. NO es una orden: publica la probabilidad medida y su muestra.
PRECISION_MODO = os.environ.get("VIGILANTE_PRECISION", "1") not in ("", "0", "false", "False")
































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










































GRID_NIVELES = 500  # rejilla fija: max14/min14 caminan cada hora; sin snap cada pasada es un "nivel nuevo" y re-dispara cooldowns
































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






# Modelo logistico de "aguante" de un nivel tras 3+ toques.
# Entrenado con 394.256 velas de 5m (2023-01 a 2026-09), 3.009 eventos,
# objetivo: NO cerrar 0,5% mas alla del nivel en las siguientes 4h.












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










DIRECCIONES_MEDIBLES = ("fuerte", "cambio", "toque", "ruptura", "estructura", "mecha", "liquidez")




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






# ---------------- Estado / historial / precision ----------------











def prec_str(lista):
    if len(lista) < MIN_SENALES:
        return f"pocas ({len(lista)})" if lista else "s/d"
    ok = sum(lista)
    return f"{round(ok / len(lista) * 100)}% ({ok}/{len(lista)})"








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
