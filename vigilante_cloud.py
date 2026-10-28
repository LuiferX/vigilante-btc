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
import urllib.request

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
    _fee,
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
from vigilante.comandos import (  # noqa: E402,F401
    leer_comandos,
    responder_comando,
)
from vigilante.render import (  # noqa: E402,F401
    VERSION,
    build_parte,
    _u16,
    trocear,
)
from vigilante.eventos import (  # noqa: E402,F401
    regla_spread,
    narrar,
    toques_hoy,
    vs_ayer,
    stats_fecha,
    cierre_ayer,
    imanes,
    scoreboard,
    texto_scoreboard,
    acuerdo_tecnica,
    linea_escenario,
    familia_evento,
    estudiar_eventos,
    linea_estudio,
    preaviso,
    marcar_preaviso,
    tca_linea,
    linea_runbook,
)
from vigilante.noticias import (  # noqa: E402,F401
    FEEDS,
    GRUPOS,
    EXPLICA,
    peso_noticia,
    impacto_noticia,
    explicar_noticia,
    noticias,
    CAL_EXP,
    explicar_evento,
    impacto_evento,
    calendario,
    direccion_noticia,
    presion_noticias,
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
    DEDUP_HORAS,
    EVAL_HORAS,
    MIN_SENALES,
    SEMILLA_SESION,
    UMBRAL_MOV,
    abrir_sombra,
    abrir_todo,
    auto_stats,
    calibrar,
    evaluar_mfe,
    evaluar_sombra,
    evaluar_todo,
    prec_str,
    precision_plan,
    registrar_pend_gate,
    resumen_medicion,
    tabla_calibracion,
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


# Fuente de mercado: se fija UNA vez por pasada para que precio y velas vengan
# del mismo sitio. Antes cada llamada hacia su propio fallback y una pasada podia
# quedar con klines de futuros y ticker de spot (mezcla inconsistente).



# ---------------- Noticias (prensa) y calendario (eventos futuros) --------

























# F6: anti "ruptura de chop". Una ruptura confirmada DEBE tener la vela en la
# direccion del break (roja=bajista, verde=alcista), cruzar el nivel de verdad
# (la vela previa cerraba al otro lado) y superar un margen minimo. Evita cantar
# "ruptura BAJISTA" cuando el soporte mas cercano sube pegado al precio en subida.
UMBRAL_ATR_MULT = 0.5    # acierto = moverse >= 0.5 * ATR 1H a favor (relativo al mercado)












# ---------------- Modo PRECISION: avisos de nivel defendido -----------------
# Solo avisa cuando el motor 4h marca un nivel con aguante medido alto
# (hold_prob alto, 3+ toques reales, calidad alta, sin quiebre confirmado) y el
# precio esta cerca. NO es una orden: publica la probabilidad medida y su muestra.
PRECISION_MODO = os.environ.get("VIGILANTE_PRECISION", "1") not in ("", "0", "false", "False")










































































GRID_NIVELES = 500  # rejilla fija: max14/min14 caminan cada hora; sin snap cada pasada es un "nivel nuevo" y re-dispara cooldowns
































# ---------------- Companero: tono, narrativa, memoria, comandos ------------

ABRIDORES = [
    "Oye, te cuento lo que veo",
    "Reporte desde la nube",
    "Pasaba por aquí y vi esto",
    "Actualización del mercado",
    "Te traigo noticias frescas",
]










# Modelo logistico de "aguante" de un nivel tras 3+ toques.
# Entrenado con 394.256 velas de 5m (2023-01 a 2026-09), 3.009 eventos,
# objetivo: NO cerrar 0,5% mas alla del nivel en las siguientes 4h.
















def stats_dia(hist, ahora):
    return stats_fecha(hist, ahora.strftime("%Y-%m-%d"))






























































































DIRECCIONES_MEDIBLES = ("fuerte", "cambio", "toque", "ruptura", "estructura", "mecha", "liquidez")












DIR_BULL = ("inflow", "inflows", "buy", "buys", "bought", "record", "demand", "adopt",
            "approval", "approve", "accumulat", "breakout", "rate cut", "cuts rates")
DIR_BEAR = ("outflow", "outflows", "sell", "sells", "sold", "lawsuit", "ban", "hack",
            "crash", "hike", "crackdown", "fraud", "charged", "fine", "bankrupt")
































# ---------------- Estado / historial / precision ----------------



















RUNBOOK_URL = "https://github.com/LuiferX/vigilante-btc/blob/main/README.md"
DASH_URL = "https://luiferx.github.io/vigilante-btc/"
































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
        # --- RED NEURONAL: RETIRADA (auditoria 2026-10-27) ----------------------
        # El bloque opt-in (VIGILANTE_NN=1) importaba `nn_infer`, modulo que NUNCA
        # existio en el repo: cada run fallaba con ImportError y el bot segua por
        # el except. Se retira en vez de dejar codigo que promete lo que no hay.
        # Si una NN vuelve, entra con: (1) pipeline de entrenamiento versionada en
        # el repo, (2) auditada sin fuga de futuro (etiquetas + ventana_vivo),
        # (3) bajo shadow+gate como cualquier otro challenger (mismo liston que
        # toques-wf-1: mismos folds, embargo y juez PBO). Ver EXPERIMENTOS.md.
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
                                 "fee": o.get("fee", 0),
                                 "r": round(pnl / o["riesgo"], 2) if o["riesgo"] else 0,
                                 # auditoria (2026-10-28): el LIQ de octubre fue
                                 # inexplicable porque el cierre no guardaba la
                                 # posicion. Con estos campos, cualquier cierre se
                                 # puede reconstruir: que riesgo se previo, donde
                                 # estaba el stop, a que precio se liquido.
                                 "entrada": o.get("entrada"), "tam": o.get("tam"),
                                 "stop": o.get("stop"), "tp": o.get("tp"),
                                 "liq": o.get("liq"), "lev": o.get("lev"),
                                 "riesgo": o.get("riesgo"),
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
