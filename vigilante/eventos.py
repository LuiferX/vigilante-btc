#!/usr/bin/env python3
"""
eventos.py - EVENTOS, SCOREBOARD Y NARRATIVA (Fase 12): preaviso de
eventos High, estudio historico por evento, marcador de precision,
imanes Deribit y la voz companero (narrativa, memoria, vs ayer).
"""

import datetime
import json
import re
import urllib.request


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


from vigilante.indicadores import fmt_miles, num_txt, cuenta_regresiva
from vigilante.toques import UMBRAL_TOQUE

RUNBOOK_URL = "https://github.com/LuiferX/vigilante-btc/blob/main/RUNBOOK.md"
DASH_URL = "https://luiferx.github.io/vigilante-btc/motor.html"


def narrar(dirb, h1, h4, d1, res, sup, precio):
    b, c = dirb["bias"], dirb["confianza"]
    if b == "ALZA":
        base = (
            f"los compradores mandan con {c}% de confianza: el corto plazo empuja "
            f"y busca romper {fmt_miles(res['precio'])}"
        )
    elif b == "BAJA":
        base = (
            f"los vendedores mandan con {c}% de confianza: la presión va "
            f"hacia {fmt_miles(sup['precio'])}"
        )
    else:
        if h1["tend"] == "ALCISTA":
            base = (
                "el corto plazo quiere subir pero los marcos grandes no confirman: mercado indeciso, "
                f"atrapado entre {fmt_miles(sup['precio'])} y {fmt_miles(res['precio'])}"
            )
        elif h1["tend"] == "BAJISTA":
            base = (
                "el corto plazo quiere caer pero los marcos grandes no confirman: mercado indeciso, "
                f"atrapado entre {fmt_miles(sup['precio'])} y {fmt_miles(res['precio'])}"
            )
        else:
            base = (
                f"nadie manda: todos los marcos laterales entre {fmt_miles(sup['precio'])} y "
                f"{fmt_miles(res['precio'])}. Cuando esto pasa, el movimiento que rompa suele ser fuerte"
            )
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


def cierre_ayer(hist, ahora):
    ay = (ahora - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    ps = [h["precio"] for h in hist if h.get("t", "").startswith(ay) and h.get("precio")]
    return ps[-1] if ps else None


def imanes(last):
    """Imanes de precio: strikes con mas Open Interest en opciones Deribit
    (gratis) + ratio put/call."""
    try:
        req = urllib.request.Request(
            "https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option",
            headers={"User-Agent": "vigilante-cloud/3.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        oi: dict[float, dict[str, float]] = {}
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
        return {
            "top": niveles,
            "pc": round(puts / calls, 2) if calls else None,
            "up": int(arriba[0]) if arriba else None,
            "down": int(abajo[0]) if abajo else None,
        }
    except Exception:
        return None


def scoreboard(eval_log, min_n=1, solo_plan=False):
    """Acierto REAL por tipo de alerta, medido en vivo (eval_log).
    Devuelve filas (tipo, n, aciertos, pct), mejor primero. Sin promesas.
    `solo_plan=True` excluye el histórico viejo, que medía sesgo y no plan."""
    # acc[tipo] = (evaluadas, aciertos)
    acc: dict[str, tuple[int, int]] = {}
    for e in eval_log or []:
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
    if re.search(
        r"cpi|ppi|pce|nfp|non-farm|nonfarm|payroll|unemployment|jobless|fomc|rate|interest", t
    ):
        return base + ": ALTO = baja | BAJO = sube"
    return base + ": la sorpresa manda la dirección"


def familia_evento(titulo):
    """Agrupa eventos por familia para el estudio (CPI, FOMC...)."""
    try:
        tl = str(titulo or "")
        for fam, pats in (
            ("CPI", ("CPI", "IPC")),
            ("PPI", ("PPI",)),
            ("FOMC", ("FOMC", "FED ", "POWELL", "TASA", "RATE DECISION")),
            ("NFP", ("NFP", "NON-FARM", "NOMINAS", "PAYROLL", "EMPLEO")),
            ("PIB", ("PIB", "GDP")),
            ("VENTAS", ("VENTAS", "RETAIL")),
        ):
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
                key = (
                    str(getattr(cu, "isoformat", lambda: str(cu))())
                    + "|"
                    + str(e.get("titulo", ""))
                )
                if key in hechas:
                    continue
                pre = [
                    h
                    for h in hist
                    if isinstance(h, dict) and h.get("t", "") <= cu.isoformat() and h.get("precio")
                ]
                post = [
                    h
                    for h in hist
                    if isinstance(h, dict)
                    and cu.isoformat()
                    < h.get("t", "")
                    <= (cu + datetime.timedelta(hours=2)).isoformat()
                    and h.get("precio")
                ]
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
            return (
                f"⚠️ {e['titulo']} en {cuenta_regresiva(e['cuando'], ahora)}"
                + (f" ({stu})" if stu else "")
                + ": cierro la boca ±30 min (blackout). Cuida el apalancamiento."
            )
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
        return "Ref %s → ahora %s (%+.2f%%) · operar te cuesta ~%.2f%% ida+vuelta" % (
            fmt_miles(arrival),
            fmt_miles(px),
            mov,
            _fee / 100,
        )
    except Exception:
        return "Ref s/d (sin precio previo)"


def linea_runbook():
    """Una línea con runbook + página + comando de diagnóstico. Puro."""
    return "Runbook: %s | Page: %s | diag: gh run view --repo LuiferX/vigilante-btc" % (
        RUNBOOK_URL,
        DASH_URL,
    )
