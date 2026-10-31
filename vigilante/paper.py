#!/usr/bin/env python3
"""
paper.py - PAPER TRADING INVISIBLE (Fase 9): banco virtual, riesgo 1%,
Kelly acotado, BE/trailing, cierres por SL/TP y diario del usuario.
"""

import datetime
import os

from vigilante.estado import MAX_PAPER_ABIERTAS
from vigilante.indicadores import (
    fmt_miles,
)
from vigilante.medicion import DEDUP_HORAS, abrir_sombra, abrir_todo

UMBRAL_PAPEL = 40  # subido de 35: el papel aprende con menos ruido


PAPER_BANCO = float(os.environ.get("PAPER_BANCO", "100.0"))  # perfil XLX: banco virtual en USDT


PAPER_LEV = int(
    os.environ.get("PAPER_LEV", "50")
)  # apalancamiento: solo dimensiona la liquidacion estimada


PAPER_RIESGO = 0.01  # 1% por idea (0.5% en racha de 3+ perdidas)

# Comision REALISTA de ida y vuelta (taker perps ~0.05% x2). El papel la cobra
# para que su curva de equity sea comparable con dinero real: sin esto, el
# Sharpe y el PnL del papel estan inflados y no dicen nada del dinero
# (2026-10-28, ver analysis/cost_model.py).
PAPER_FEE_RT_PCT = float(os.environ.get("PAPER_FEE_RT_PCT", "0.10"))


def _fee(ent: float, tam: float) -> float:
    """Comision de ida y vuelta sobre el notional (entrada*tamano)."""
    try:
        return round(max(float(ent), 0.0) * max(float(tam), 0.0)
                     * PAPER_FEE_RT_PCT / 100.0, 2)
    except Exception:
        return 0.0


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
        return not (
            pu.get("dir") == bias
            and (ahora - datetime.datetime.fromisoformat(pu.get("t", ""))).total_seconds() / 3600
            < DEDUP_HORAS
        )
    except Exception:
        return True


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
                for _o in est.get("paper_abiertas") or []:
                    try:
                        _ent = float(_o.get("entrada"))
                        _tam = float(_o.get("tam"))
                        _ri = float(_o.get("riesgo") or 0)
                        if _o.get("dir") == "SHORT":
                            _pnl = round((_ent - _px_rb) * _tam, 2) - _fee(_ent, _tam)
                        else:
                            _pnl = round((_px_rb - _ent) * _tam, 2) - _fee(_ent, _tam)
                        _cerr.append(
                            {
                                "dir": _o.get("dir", "?"),
                                "res": "REBORN",
                                "pnl": _pnl,
                                "r": round(_pnl / _ri, 2) if _ri else 0,
                                "t": ahora.isoformat(),
                            }
                        )
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
    liq = (
        round(precio * (1 - 1.0 / PAPER_LEV))
        if dire == "LONG"
        else round(precio * (1 + 1.0 / PAPER_LEV))
    )
    if dist_stop > abs(precio - liq):
        return None
    if dist_stop > 0.5 * abs(precio - liq):
        return None
    entrada = round(precio)
    dist_stop = abs(entrada - stop)
    if dist_stop <= 0:
        return None
    liq = (
        round(entrada * (1 - 1.0 / PAPER_LEV))
        if dire == "LONG"
        else round(entrada * (1 + 1.0 / PAPER_LEV))
    )
    tam = (banco * riesgo_pct) / dist_stop
    try:
        if (tam * entrada) / PAPER_LEV > 10 * (dist_stop * tam):
            return None  # cap LIQ real: el LIQ de hoy pago 25.7x el riesgo; maximo 10x
        # NOTA DE AUDITORIA (2026-10-28): el LIQ de octubre (stop a 0.08% del
        # precio, 25.7x el riesgo) lo rechazaria ESTE guard. Se evaluo una
        # invariante mas dura (3x) pero la posicion canonica del repo carga
        # 2.075x y los tests de sizing usan 8.3x: apretarla romperia el sizing
        # sin un modo de fallo observado que lo justifique. Lo que faltaba no
        # era otro guard: era AUDITAR. El cierre ahora registra entrada/tam/
        # stop/liq/riesgo (ver vigilante_cloud.main) para que ningun LIQ vuelva
        # a ser inexplicable.
    except Exception:
        return None
    pos = {
        "dir": dire,
        "entrada": entrada,
        "stop": stop,
        "tp": round(tp),
        "tam": tam,
        "riesgo": round(dist_stop * tam, 2),
        "lev": PAPER_LEV,
        "liq": liq,
        "fee": _fee(entrada, tam),
        "t": ahora.isoformat(),
    }
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
        liq = float(
            o.get("liq") or (ent * (1 - 1.0 / lev) if o["dir"] == "LONG" else ent * (1 + 1.0 / lev))
        )
        f = _fee(ent, tam)  # comision de ida y vuelta: el PnL honesto la paga
        if o["dir"] == "LONG":
            if (ref_l is not None and ref_l <= liq) or last <= liq:
                return liq, "LIQ", round(-(tam * ent) / lev, 2) - f
            if (ref_l is not None and ref_l <= o["stop"]) or last <= o["stop"]:
                return float(o["stop"]), "SL", round((float(o["stop"]) - ent) * tam, 2) - f
            if (ref_h is not None and ref_h >= o["tp"]) or last >= o["tp"]:
                return float(o["tp"]), "TP", round((float(o["tp"]) - ent) * tam, 2) - f
        else:
            if (ref_h is not None and ref_h >= liq) or last >= liq:
                return liq, "LIQ", round(-(tam * ent) / lev, 2) - f
            if (ref_h is not None and ref_h >= o["stop"]) or last >= o["stop"]:
                return float(o["stop"]), "SL", round((ent - float(o["stop"])) * tam, 2) - f
            if (ref_l is not None and ref_l <= o["tp"]) or last <= o["tp"]:
                return float(o["tp"]), "TP", round((ent - float(o["tp"])) * tam, 2) - f
        return None
    except Exception:
        return None


def gestionar_be_trailing(est, precio, atr, regimen):
    """BE/trailing de las ops ABIERTAS del usuario (no de las señales).

    Extraído de `vigilante_cloud.main()` (P2, troceado 2/N). Muta las posiciones
    en `est["ops"]` / `est["sim_abiertas"]` y devuelve el texto de la primera
    gestión aplicada (o None). El texto lo emite el llamador.
    """
    gestion_txt = None
    try:
        for llave in ("ops", "sim_abiertas"):
            lista = est.get(llave, [])
            if not isinstance(lista, list):
                continue
            for o in lista:
                if not isinstance(o, dict):
                    continue
                r, acc, nsl = gestion_sl(o, precio, atr, regimen)
                if acc == "BE":
                    try:
                        o["risk0"] = abs(float(o["entrada"]) - float(o["stop"]))
                    except Exception:
                        pass
                    o["be_done"] = True
                    o["stop"] = nsl
                    gestion_txt = ("🔒 BE: " + str(o.get("dir")) + " " + fmt_miles(o.get("entrada"))
                                   + " → " + fmt_miles(precio) + f" ({r:+.1f}R). Mueve SL a "
                                   + fmt_miles(nsl) + " (entrada).")
                    break
                if acc == "TRAIL":
                    if o.get("trail_lock") == nsl:
                        continue
                    o["trail_lock"] = nsl
                    o["stop"] = nsl
                    gestion_txt = ("🔒 TRAIL: " + str(o.get("dir")) + " " + fmt_miles(o.get("entrada"))
                                   + " → " + fmt_miles(precio) + f" ({r:+.1f}R). Traba +1R en "
                                   + fmt_miles(nsl) + ".")
                    break
            if gestion_txt:
                break
    except Exception:
        gestion_txt = None
    return gestion_txt


def abrir_mediciones(est, dirb, niv, precio, umbral, ahora):
    """Abre papel/sombra/todo de una pasada (todo invisible, sin avisos).

    Extraído de `vigilante_cloud.main()` (P2, troceado 4/N). El papel real
    respeta sus frenos institucionales (`puede_papel`/`abrir_papel`); la sombra
    mide TODA señal con sesgo sin pisos; "todo" mide cada pasada, hable o
    calle, para saber si callar fue correcto. Las dos últimas nunca deben
    tumbar la pasada: van con su propio guardián.
    """
    if puede_papel(est, dirb["bias"], dirb["confianza"], ahora):
        pos = abrir_papel(est, dirb, niv, precio, ahora)
        if pos:
            est["paper_ult"] = {"dir": dirb["bias"], "t": ahora.isoformat()}
    try:
        abrir_sombra(est, dirb["bias"], dirb["confianza"], precio, umbral, ahora)
    except Exception:
        pass
    try:
        abrir_todo(est, dirb["bias"], dirb["confianza"], precio, umbral, ahora)
    except Exception:
        pass


def revisar_cierres_papel(est, kl_h1, precio, ahora):
    """Cierra el papel virtual con la última vela 1H cerrada + el precio.

    Extraído de `vigilante_cloud.main()` (P2, auditoria 2026-10-30: troceado).
    Muta `est`: banco, paper_cerradas (con auditoría de la posición y guardia
    anti-duplicado), paper_dia y paper_abiertas. Invisible: no avisa nada.
    """
    try:
        ultima = float(precio)
    except Exception:
        return
    def _clave(c):
        return (c.get("dir"), c.get("res"), c.get("pnl"),
                str(c.get("t", ""))[:16])

    abiertas_p = []
    for o in est.get("paper_abiertas", []):
        try:
            ref_h, ref_l = ref_rango(kl_h1, o.get("t"))
            fin = cierre_papel(o, ref_h, ref_l, ultima)
            if fin:
                px, donde, pnl = fin
                banco = float(est.get("banco", PAPER_BANCO)) + pnl
                est["banco"] = round(banco, 2)
                cerr = est.get("paper_cerradas", [])
                nuevo = {"dir": o["dir"], "res": donde, "pnl": round(pnl, 2),
                         "fee": o.get("fee", 0),
                         "r": round(pnl / o["riesgo"], 2) if o["riesgo"] else 0,
                         # auditoría: la posición completa, para que ningún LIQ
                         # vuelva a ser inexplicable.
                         "entrada": o.get("entrada"), "tam": o.get("tam"),
                         "stop": o.get("stop"), "tp": o.get("tp"),
                         "liq": o.get("liq"), "lev": o.get("lev"),
                         "riesgo": o.get("riesgo"),
                         "t": ahora.isoformat()}
                # P0-1.4: si el último registro es idéntico, no se repite.
                if not cerr or _clave(cerr[-1]) != _clave(nuevo):
                    cerr.append(nuevo)
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
                msgs.append(
                    {
                        "txt": f"Tu {d} {fmt_miles(e)} cerró en {donde} {fmt_miles(px)} ({r:+.1f}R)",
                        "r": round(r, 2),
                        "dir": d,
                        "res": donde,
                    }
                )
            else:
                abiertas.append(o)
        except Exception:
            abiertas.append(o)  # corrupta pero visible: nunca se pierde en silencio
            continue
    return abiertas, msgs


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
