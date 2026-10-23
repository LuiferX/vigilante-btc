#!/usr/bin/env python3
"""
alertas.py - MOTOR DE ALERTAS (Fase 10): decidir_alerta (la cascada
anti-spam), planes de entrada, veto institucional, blackout de eventos y
score de senal.
"""

import os
import re

from vigilante.estado import enfriar
from vigilante.indicadores import fmt_miles
from vigilante.toques import UMBRAL_TOQUE
from vigilante.analisis import fuentes_nivel, ficha_zona


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
        lineas.append(
            f"STOP: bajo {fmt_miles(stop)} ({sup['origen']}) · OBJETIVO: {fmt_miles(obj)} (2R)"
        )
        lineas.append("NO entres antes del cierre ni persigas velas estiradas")
    elif dirb["bias"] == "BAJA":
        gatillo = sup["precio"]
        stop = res["precio"]
        obj = gatillo - (stop - gatillo) * 2
        lineas.append(f"ESPERA: cierre 1H BAJO {fmt_miles(gatillo)} ({sup['origen']}) con volumen")
        lineas.append(
            f"STOP: sobre {fmt_miles(stop)} ({res['origen']}) · OBJETIVO: {fmt_miles(obj)} (2R)"
        )
        lineas.append("NO entres antes del cierre ni vendas el piso sin confirmación")
    else:
        lineas.append(
            f"ESPERA: ruptura de {fmt_miles(sup['precio'])} - {fmt_miles(res['precio'])} con volumen en sesión"
        )
        lineas.append("Sin sesgo no hay plan: el que opera rangos sin reglas, dona")
    if evs:
        e0 = evs[0]
        lineas.append(
            f"GUARDIA: {e0['titulo']} {cuenta_regresiva(e0['cuando'], ahora)}: no operes encima del evento"
        )
    lineas.append("Riesga máx 1% de tu cuenta por idea")
    return lineas


UMBRAL_CONF_FUERTE = 55


UMBRAL_CONF_CAMBIO = 40


UMBRAL_CONF_SENAL = (
    50  # subido de 45: menos señales, mayor calidad (replay: confluencia > umbral solo)
)


FEE_PCT = 0.001  # 0.10% ida+vuelta (costo de operar)


FILTRO_VOL = False  # opt-in: descarta senales cuando FEE/umbral > 0.25 (break-even > 41.7%)


FUNDING_EXTREMO = 0.05  # |funding| >= 0.05% = un lado recargado (lectura contrarian)


UMBRAL_BRUSCO = float(
    os.environ.get("VIGILANTE_UMBRAL_BRUSCO", "1.5")
)  # +/-1.5% en 1h: ruido comun, no aviso


UMBRAL_RITMO = float(
    os.environ.get("VIGILANTE_UMBRAL_RITMO", "1.5")
)  # +/-1.5% en 30min: movimiento real


UMBRAL_DIA_NY = 2.0  # +/-2% en el dia NY = dia de tendencia (avisa)


BLACKOUT_MIN = 30  # sin senales nuevas X min antes/despues de evento High


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
        res = sorted(
            float(x["precio"])
            for x in (niv or {}).get("resistencias", [])
            if isinstance(x, dict) and x.get("precio")
        )
        sup = sorted(
            (
                float(x["precio"])
                for x in (niv or {}).get("soportes", [])
                if isinstance(x, dict) and x.get("precio")
            ),
            reverse=True,
        )
    except Exception:
        return None
    entrada = precio
    if lado in ("soporte", "long", "rup_alcista"):
        dir_ = "ALZA"
        if stop is None:
            ref = sup[0] if sup else precio - atr
            stop = ref - 0.5 * atr
        obj = next((r for r in res if r > entrada + 0.1 * atr), None)
    elif lado in ("resistencia", "short", "rup_bajista"):
        dir_ = "BAJA"
        if stop is None:
            ref = res[0] if res else precio + atr
            stop = ref + 0.5 * atr
        obj = next((s for s in sup if s < entrada - 0.1 * atr), None)
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
        obj = entrada + 2 * riesgo if dir_ == "ALZA" else entrada - 2 * riesgo
    if (dir_ == "ALZA" and obj <= entrada) or (dir_ == "BAJA" and obj >= entrada):
        return None
    rr = abs(obj - entrada) / riesgo
    stop_pct = riesgo / entrada * 100
    return {
        "dir": dir_,
        "entrada": round(entrada, 1),
        "stop": round(stop, 1),
        "objetivo": round(obj, 1),
        "rr": round(rr, 2),
        "stop_pct": round(stop_pct, 2),
        "valido": bool(rr >= min_rr and riesgo <= max_stop_atr * atr),
    }


def texto_plan(plan):
    """Linea compacta del plan. Vacía si no hay plan."""
    try:
        if not isinstance(plan, dict):
            return ""
        return (
            f"📐 {plan['dir']}: stop {fmt_miles(plan['stop'])} (-{plan['stop_pct']:.2f}%) · "
            f"objetivo {fmt_miles(plan['objetivo'])} · R:R {plan['rr']:.1f}"
        )
    except Exception:
        return ""


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


def decidir_alerta(
    precio,
    niv,
    dirb,
    est,
    ahora,
    forzado=None,
    mov1h=None,
    regimen=None,
    bloqueo=False,
    motivo_bloq="",
    mov_ny=None,
    liq=None,
    pila=None,
    umbral_fuerte=UMBRAL_CONF_FUERTE,
    umbral_cambio=UMBRAL_CONF_CAMBIO,
    mov30=None,
    rup=None,
    qb=None,
    sl=None,
    gestion=None,
    mecha=None,
    slm=None,
    estir=None,
    foot=None,
    umbral=None,
    atr=None,
    liq_plan=None,
    chop=False,
):
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
    _vol_filtrado = FILTRO_VOL and umbral and umbral > 0 and (FEE_PCT / umbral) > 0.25
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
    if (
        not _vol_filtrado
        and prev != "?"
        and prev != bias
        and bias in ("ALZA", "BAJA")
        and conf >= umbral_cambio
        and enfriar(est, "fuerte:" + bias, 4, ahora)
    ):
        return True, f"Cambio de dirección: {prev} → {bias}", "alerta"
    if (
        not _vol_filtrado
        and bias in ("ALZA", "BAJA")
        and conf >= umbral_fuerte
        and enfriar(est, "fuerte:" + bias, 4, ahora)
    ):
        return True, f"Señal fuerte {bias} (confianza {conf}%)", "alerta"
    # Un movimiento = un aviso. Medido en produccion (historial real): 16 de 36
    # avisos de movimiento eran el MISMO movimiento repetido con minutos de
    # diferencia. brusco y ritmo comparten ventana por direccion: el que dispara
    # primero consume el enfriamiento del otro. VIGILANTE_RUIDO_UNIFICADO=0 apaga.
    _ruido_unif = os.environ.get("VIGILANTE_RUIDO_UNIFICADO", "1") not in (
        "",
        "0",
        "false",
        "False",
    )
    if (
        mov1h is not None
        and abs(mov1h) >= UMBRAL_BRUSCO
        and enfriar(est, "brusco:" + ("sube" if mov1h > 0 else "baja"), 4, ahora)
        and (
            not _ruido_unif
            or mov30 is None
            or abs(mov30) < UMBRAL_RITMO
            or ("sube" if mov30 > 0 else "baja") != ("sube" if mov1h > 0 else "baja")
            or enfriar(est, "ritmo:" + ("sube" if mov1h > 0 else "baja"), 4, ahora)
        )
    ):
        return True, f"Movimiento brusco de {mov1h:+.2f}% en 1 h", "alerta"
    if (
        mov30 is not None
        and abs(mov30) >= UMBRAL_RITMO
        and enfriar(est, "ritmo:" + ("sube" if mov30 > 0 else "baja"), 4, ahora)
        and (
            not _ruido_unif
            or mov1h is None
            or abs(mov1h) < UMBRAL_BRUSCO
            or ("sube" if mov30 > 0 else "baja") != ("sube" if mov1h > 0 else "baja")
            or enfriar(est, "brusco:" + ("sube" if mov30 > 0 else "baja"), 4, ahora)
        )
    ):
        return True, f"Ritmo acelerado {mov30:+.2f}% en 30 min", "alerta"
    if (
        isinstance(estir, str)
        and estir
        and (bias not in ("ALZA", "BAJA") or conf < 45)
        and enfriar(est, "estir:" + ("bajo" if estir.startswith("bajo") else "alto"), 4, ahora)
    ):
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
        _plan = (
            plan_trade("rup_alcista" if _rb else "rup_bajista", precio, niv, atr) if atr else None
        )
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
            _fut = f" [nivel: {_fut}]" if _fut else ""
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
            return (
                True,
                "Toma de liquidez: "
                + liq
                + f". Quien la persigue suele quedar atrapado → {ref}."
                + _pl,
                "alerta",
            )
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
    if (
        isinstance(qb, dict)
        and qb.get("dir") in ("ALZA", "BAJA")
        and bias == qb["dir"]
        and conf >= UMBRAL_CONF_SENAL
    ):
        try:
            _stop = sl[0] if isinstance(sl, (list, tuple)) and sl else None
            _plan = (
                plan_trade("long" if qb["dir"] == "ALZA" else "short", precio, niv, atr, stop=_stop)
                if (atr and _stop and not _chop)
                else None
            )
            _pasa = True if _chop else ((not atr) or bool(_plan and _plan["valido"]))
            if _pasa and enfriar(est, "qb:" + qb["dir"], 4, ahora):
                verbo = "COMPRA" if qb["dir"] == "ALZA" else "VENTA"
                extra = (
                    f" · {texto_plan(_plan)}"
                    if _plan
                    else (f" · SL {fmt_miles(_stop)}" if _stop is not None else "")
                )
                lejos = (
                    " (SL lejos, tamaño pequeño)"
                    if isinstance(sl, (list, tuple)) and len(sl) > 2 and sl[2]
                    else ""
                )
                _chopn = " (chop: contexto, no entrada)" if _chop else ""
                return (
                    True,
                    f"{verbo} {qb.get('tipo', 'BOS')} sobre {fmt_miles(qb.get('nivel', precio))}{extra}{lejos}{_chopn}",
                    "alerta",
                )
        except Exception:
            pass
    if (
        isinstance(mecha, dict)
        and mecha.get("dir") in ("ALZA", "BAJA")
        and bias == mecha["dir"]
        and conf >= UMBRAL_CONF_SENAL
        and regimen == "tendencia"
    ):
        try:
            _stopm = slm[0] if isinstance(slm, (list, tuple)) and slm else None
            _planm = (
                plan_trade(
                    "long" if mecha["dir"] == "ALZA" else "short", precio, niv, atr, stop=_stopm
                )
                if (atr and _stopm and not _chop)
                else None
            )
            _pasam = True if _chop else ((not atr) or bool(_planm and _planm["valido"]))
            if _pasam and enfriar(est, "mecha:" + mecha["dir"], 4, ahora):
                verbo = "RECHAZO ALZA" if mecha["dir"] == "ALZA" else "RECHAZO BAJA"
                extra = (
                    f" · {texto_plan(_planm)}"
                    if _planm
                    else (f" · SL {fmt_miles(_stopm)}" if _stopm is not None else "")
                )
                lejos = (
                    " (SL lejos, tamaño pequeño)"
                    if isinstance(slm, (list, tuple)) and len(slm) > 2 and slm[2]
                    else ""
                )
                _chopm = " (chop: contexto, no entrada)" if _chop else ""
                return (
                    True,
                    f"{verbo} {fmt_miles(mecha.get('nivel', precio))}→{fmt_miles(precio)}{extra}{lejos}{_chopm}",
                    "alerta",
                )
        except Exception:
            pass
    if min(dist_res, dist_sup) <= UMBRAL_TOQUE:
        lado = (
            f"la resistencia de {fmt_miles(res['precio'])}"
            if dist_res <= dist_sup
            else f"el soporte de {fmt_miles(sup['precio'])}"
        )
        nivel = res["precio"] if dist_res <= dist_sup else sup["precio"]
        fade_ok = (
            True
            if bias == "LATERAL"
            else ((bias == "BAJA") if dist_res <= dist_sup else (bias == "ALZA"))
        )
        _plan = (
            plan_trade("resistencia" if dist_res <= dist_sup else "soporte", precio, niv, atr)
            if (atr and not _chop)
            else None
        )
        _pasa_toque = True if _chop else ((not atr) or bool(_plan and _plan["valido"]))
        if (
            _pasa_toque
            and not (conf < 45 and (regimen or "tendencia") == "rango")
            and fade_ok
            and enfriar(est, f"toque:{nivel}", 10, ahora)
        ):
            _pt = (
                (" · " + texto_plan(_plan))
                if _plan
                else (" · chop: contexto, no entrada" if _chop else "")
            )
            _fut = fuentes_nivel(res if dist_res <= dist_sup else sup)
            _fut = f" [fuentes: {_fut}]" if _fut else ""
            return True, f"Tocando {lado}" + ficha_zona(est, nivel) + _fut + _pt, "alerta"
    _prog = _reporte_programado()
    if _prog:
        return _prog
    return False, "sin señal (rango, sin cambios)", "nada"
