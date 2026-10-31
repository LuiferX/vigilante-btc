#!/usr/bin/env python3
"""
render.py - RENDER DEL PARTE (Fase 13): el mensaje de Telegram completo
(veredicto, marcos, memoria, mercado, contexto, plan).
"""

import datetime

VERSION = "v6"

from vigilante.estado import cambio
from vigilante.eventos import (
    acuerdo_tecnica,
    linea_escenario,
    linea_runbook,
    regla_spread,
    tca_linea,
)
from vigilante.indicadores import cuenta_regresiva, fmt_miles, sesion_hora
from vigilante.mercado import cb_veredicto, texto_fvg, veredicto_dom
from vigilante.noticias import explicar_evento, explicar_noticia, impacto_evento, impacto_noticia
from vigilante.precision import linea_motor
from vigilante.red import FUENTE


def build_parte(
    t, h1, h4, d1, w1, niv, dirb, prox, senti, fg, est, motivo, tipo, notis, evs, ahora, extras
):
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
            _grade = extras.get("grade") or "?"
            C.append(
                f"{dirb['bias']} {dirb['confianza']}% · calidad {_grade} · {fmt_miles(t['last'])} ({t['chg']:+.2f}%)"
            )
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

    icono_tipo = {
        "alerta": "🚨",
        "preny": "📊",
        "manana": "☀️",
        "madrugada": "🌙",
        "noche": "🌙",
    }.get(tipo, "🤖")
    L = []
    L.append(icono_tipo + " " + motivo)
    L.append("💬 " + str(extras.get("intro") or "").strip())
    L.append("━━━━━ 🧭 VEREDICTO ━━━━━")
    L.append(
        f"{dirb['bias']} {dirb['confianza']}% · calidad {extras.get('grade', '?')} · {fmt_miles(t['last'])} ({t['chg']:+.2f}%)"
    )
    L.append(f"🎯 {accion}")
    L.append("")
    L.append(f"🤖 VIGILANTE BTC {VERSION} | {now} | {sesion_hora()} | datos {FUENTE['nombre']}")
    L.append(f"📈 max {fmt_miles(t['hi'])} / min {fmt_miles(t['lo'])}")
    L.append("")
    L.append(
        f"🧭 MARCOS: {dirb['bias']} ({dirb['confianza']}%) · régimen {extras.get('regimen', '?')} · ADX 4H {h4.get('adx', '?')}"
    )
    if extras.get("motor"):
        L.append("📐 " + linea_motor(extras["motor"]))
    if extras.get("confl", 0) >= 2:
        L.append(f"🧩 Confluencia: {extras['confl']} fuentes en el nivel más cercano")
    L.append(
        "  "
        + "  ".join(
            f"{x['tf']}{icon.get(x['tend'], '🟡')}(s{x['score']:+d})" for x in (h1, h4, d1, w1)
        )
    )
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
        L.append(
            f"⏱ Objetivo SOBRE {fmt_miles(res['precio'])} a ~{horas_res} h | ⏰ {prox} | 4H en {h4['cierreEnMin']} min"
        )
    elif dirb["bias"] == "BAJA":
        L.append(
            f"⏱ Objetivo BAJO {fmt_miles(sup['precio'])} a ~{horas_sup} h | ⏰ {prox} | 4H en {h4['cierreEnMin']} min"
        )
    else:
        L.append(f"⏱ Rango activo | ⏰ {prox} | 4H en {h4['cierreEnMin']} min")
    coil = [x["tf"] for x in (h1, h4, d1, w1) if x["compresion"] < 0.5]
    if coil:
        L.append(f"🌀 Compresión: {', '.join(coil)} (mercado quieto)")
    L.append(f"🌡 Volatilidad {h1['regLabel']} ({h1['regPct']}%)")
    L.append("")
    L.append("━━━━━ 📊 MERCADO (solo cambios) ━━━━━")
    hubo = False
    fg_icon = (
        "😱"
        if fg["valor"] < 25
        else (
            "😨"
            if fg["valor"] < 45
            else ("😐" if fg["valor"] < 55 else ("🙂" if fg["valor"] < 75 else "🤑"))
        )
    )
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
                L.append(
                    f"💵 DÓLAR: {dxy['px']} ({dxy['chg']:+.2f}%) | BOLSA SPX: {spx['px']} ({spx['chg']:+.2f}%)"
                    + extras.get("macro_viejo", "")
                )
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
        L.append(
            f"🐋 BALLENAS: {bal['ns']} sells {fmt_miles(bal['sells'])} BTC vs {bal['nb']} buys {fmt_miles(bal['buys'])} BTC → {bal['txt']}"
        )
        hubo = True
    ima = extras.get("ima")
    if ima and ima.get("top"):
        tops = " | ".join(
            f"{fmt_miles(x['strike'])} ({fmt_miles(x['oi'])} BTC)" for x in ima["top"]
        )
        pc = f" P/C {ima['pc']}" if ima.get("pc") is not None else ""
        clave_ima = tops + pc
        if cambio(est, "ima", clave_ima, 0):
            L.append(f"🧲 IMANES: {tops}{pc}")
            if ima.get("up") and ima.get("down"):
                L.append(
                    f"   → imán cercano arriba {fmt_miles(ima['up'])} / abajo {fmt_miles(ima['down'])}"
                )
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
        arrib = " | ".join(
            f"{fmt_miles(x['precio'])} ({x['dist']:+.2f}%)" for x in lm.get("arriba", [])[:2]
        )
        abaj = " | ".join(
            f"{fmt_miles(x['precio'])} ({x['dist']:+.2f}%)" for x in lm.get("abajo", [])[:2]
        )
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
            L.append(
                f"🎯 POC {tag}{fmt_miles(pc['poc'])} (área {fmt_miles(pc['val'])}–{fmt_miles(pc['vah'])})"
            )
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
            L.append(
                f"👑 DOMINANCIA BTC {dm['btc']}% (ETH {dm.get('eth', '?')}%) → {veredicto_dom(dm['btc'], prevd)}"
            )
            hubo = True
    pr = extras.get("pres")
    if pr and cambio(est, "pres", pr["valor"], 10):
        L.append(f"📰 IMPACTO: {pr['txt']} → {acuerdo_tecnica(dirb['bias'], pr['valor'])}")
        hubo = True
    if not hubo:
        L.append("(mercado sin cambios desde tu último parte)")
    aut = extras.get("aut")
    if aut:
        L.append(
            f"🧠 AUTO: mejor {aut['mejor'][0]} ({aut['mejor'][1]}%) · peor {aut['peor'][0]} ({aut['peor'][1]}%) · n={aut['n']}"
        )
    L.append("━━━━━ 📚 CONTEXTO ━━━━━")
    L.append("📰 NOTICIAS NUEVAS (no vistas):")
    _vistas = extras.get("vistas") or []
    _notis = notis or []
    frescas = [
        n
        for n in _notis
        if isinstance(n, dict)
        and str(n.get("titulo") or "").strip()
        and n.get("titulo") not in _vistas
    ][:3]
    if frescas:
        for n in frescas:
            icono = "🔴" if n["score"] >= 9 else "🟡"
            L.append(f"  {icono} [{n['score']}] {n['titulo']}")
            L.append(
                f"     → {explicar_noticia(n.get('tags') or [])} · impacto {impacto_noticia(n.get('score') or 0)}"
            )
    else:
        L.append("  (sin noticias nuevas desde tu último parte)")
    L.append("")
    L.append("🗓 PROXIMOS EVENTOS EE.UU.:")
    if evs:
        for e in evs[:3]:
            cuando_s = e["cuando"].strftime("%a %d %H:%M UTC")
            L.append(f"  📌 {e['titulo']} ({cuando_s}, {cuenta_regresiva(e['cuando'], ahora)})")
            L.append(
                f"     → {explicar_evento(e['titulo'])} · impacto {impacto_evento(e['impact'])}"
            )
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
        _out: list[str] = []
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
