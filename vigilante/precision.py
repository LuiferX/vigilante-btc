#!/usr/bin/env python3
"""
precision.py - GATE DE VALIDACION + MODO PRECISION (Fase 8).

La puerta que decide si una alerta direccional puede salir (con
evidencia viva u OOS), el modo PRECISION (avisos de nivel defendido,
con probabilidad medida y autocensura por deriva) y su medicion.
"""

import datetime
import json
import os
from typing import Any

from vigilante.indicadores import fmt_miles, es_alerta_direccional
from vigilante.red import klines

GATE_FILE = os.environ.get("VIGILANTE_VALIDATION", "analysis/data/validation.json")


def _sub(d: Any, clave: str) -> dict[str, Any]:
    """Sub-diccionario tolerante: {} si falta la clave o no es objeto.

    validation.json / latest_decision.json vienen de disco (json): su forma no
    esta garantizada. Antes esto se escribia inline
    (`d.get(k) if isinstance(d.get(k), dict) else {}`), que mypy no sabe
    estrechar y por eso marcaba `.get()` sobre un posible None.
    """
    v = d.get(clave)
    return v if isinstance(v, dict) else {}


def _num(v: Any) -> float | None:
    """float tolerante: None si el valor falta o no es numerico.

    Equivale al `try: float(...) except: None` original (mismo resultado), pero
    deja explicito que el None es un caso esperado y no un accidente.
    """
    try:
        return float(v)
    except Exception:
        return None


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
    samples = _sub(data, "samples")
    metrics = _sub(data, "metrics")
    drift = _sub(data, "drift")
    status = str(data.get("status") or "sin_datos")
    gate = _sub(data, "gate")
    oos = _sub(data, "oos")
    try:
        effective = int(samples.get("effective") or 0)
    except Exception:
        effective = 0
    skill = _num(metrics.get("brier_skill"))
    ece = _num(metrics.get("calibration_error"))
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
    if (
        status == "ok"
        and effective >= 100
        and skill is not None
        and skill > 0
        and ece is not None
        and ece <= 0.08
        and drift_status != "alert"
    ):
        return {"ok": True, "reason": "vivo · " + " · ".join(partes)}
    # 2) canal OOS: validation.json ya lo calcula (oos_valido + sin veto vivo)
    canal = str(gate.get("canal") or "")
    if canal == "oos":
        # P0-1.1 (auditoria 2026-10-29): el canal OOS era un puente sobre el
        # canal vivo. Con el vivo en skill negativa o deriva en alerta, el
        # puente se cae: no se puede mandar una senal direccional cuando la
        # ventana viva -aunque corta- dice lo contrario. Requiere muestras
        # vivas suficientes para que el veredicto no sea ruido (>= 30).
        vivo_efectivo = effective >= 30
        vivo_contradice = (
            vivo_efectivo and ((skill is not None and skill <= 0)
                               or (ece is not None and ece > 0.08)
                               or drift_status == "alert")
        )
        try:
            o_eff = int(oos.get("effective") or 0)
        except Exception:
            o_eff = 0
        o_skill = _num(oos.get("brier_skill"))
        o_ece = _num(oos.get("ece"))
        if (
            o_eff >= 100
            and o_skill is not None
            and o_skill > 0
            and o_ece is not None
            and o_ece <= 0.08
            and status not in ("roto", "degradado")
            and not vivo_contradice
        ):
            partes.append(f"OOS {o_eff} muestras · skill {o_skill:+.4f} · ECE {o_ece:.3f}")
            return {"ok": True, "reason": " · ".join(partes)}
        if vivo_contradice:
            partes.append("veto vivo (skill<=0 / ECE>0.08 / drift alert) bloquea OOS")
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
    dec = _sub(d, "decision")
    state = _sub(d, "state")
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


BT_FILE = os.environ.get("VIGILANTE_MOTOR_BT", "analysis/data/backtest.json")


VALIDATION_FILE = os.environ.get("VIGILANTE_VALIDATION", "analysis/data/validation.json")


PRECISION_MIN_PROB = float(os.environ.get("VIGILANTE_PRECISION_MIN", "0.85"))


PRECISION_MIN_CALIDAD = float(os.environ.get("VIGILANTE_PRECISION_CALIDAD", "8.0"))


PRECISION_MIN_TOQUES = int(os.environ.get("VIGILANTE_PRECISION_TOQUES", "3"))


PRECISION_MAX_EDAD_MIN = float(os.environ.get("VIGILANTE_PRECISION_EDAD", "20"))


PRECISION_CERCA_PCT = float(os.environ.get("VIGILANTE_PRECISION_CERCA", "0.35"))


PRECISION_DEDUP_HORAS = float(os.environ.get("VIGILANTE_PRECISION_DEDUP", "12"))


PRECISION_EVAL_HORAS = 4.0  # mismo horizonte que el motor (48 velas de 5m)


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
                return {
                    "n": int(b.get("n") or 0),
                    "real": float(b.get("real") or 0),
                    "pred": float(b.get("pred") or 0),
                    "skill": bt.get("brier_skill"),
                    "muestras": int(bt.get("samples") or 0),
                    "inicio": bt.get("start"),
                }
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
    dec = _sub(motor, "decision")
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
            continue  # un nivel roto no esta "defendido"
        center = lv.get("center")
        if not center or center <= 0:
            continue
        cerca = abs(center - precio) / precio * 100
        if cerca > PRECISION_CERCA_PCT:
            continue  # el aviso es "precio en el nivel"
        if mejor is None or prob > mejor[0]:
            mejor = (prob, lv, calidad, toques, cerca)
    if not mejor:
        return None
    prob, lv, calidad, toques, cerca = mejor
    return {
        "nivel": lv.get("center"),
        "lado": lv.get("role"),
        "prob": round(prob, 3),
        "calidad": round(calidad, 1),
        "toques": toques,
        "cerca": round(cerca, 2),
        "round_level": lv.get("round_level"),
        "confluencia": lv.get("htf_confluence"),
        "edad_min": motor.get("_edad_min"),
        "bias": (motor.get("state") or {}).get("bias"),
        "accion": dec.get("action"),
        "confianza": dec.get("confidence"),
    }


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
    L.append(
        f"Precio {fmt_miles(precio)} a {nivel['cerca']}% del nivel · "
        f"aguante estimado {prob * 100:.0f}% (fallo ~{100 * (1 - prob):.0f}%)"
    )
    L.append(
        f"Evidencia: {nivel['toques']} toques reales en 6h · calidad {nivel['calidad']}/10"
        + (
            f" · confluencia {nivel['confluencia']} temporalidades"
            if nivel.get("confluencia")
            else ""
        )
    )
    if evidencia:
        L.append(
            f"Medido fuera de muestra: {evidencia['muestras']} casos desde "
            f"{str(evidencia['inicio'])[:10]}, banda alta rindió {evidencia['real'] * 100:.0f}%"
        )
    L.append(
        "Solo aviso, no es orden ni entrada: el aguante se anula con cierre 4h más allá del nivel."
    )
    return "\n".join(L)


def registrar_pend_precision(est, nivel, ahora):
    pend = est.get("pend_precision") or []
    pend.append(
        {
            "t": ahora.isoformat(),
            "nivel": nivel["nivel"],
            "lado": nivel["lado"],
            "prob": nivel["prob"],
            "toques": nivel["toques"],
            "calidad": nivel["calidad"],
        }
    )
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
        ventana = [
            v for v in velas if t0 < v["t"] <= t0 + datetime.timedelta(hours=PRECISION_EVAL_HORAS)
        ]
        if len(ventana) < barras:
            vivas.append(p)
            continue
        lado = str(p.get("lado") or "").lower()
        if lado.startswith("sop"):
            aguanto = all(v["c"] >= nivel * 0.995 for v in ventana)
        else:
            aguanto = all(v["c"] <= nivel * 1.005 for v in ventana)
        log = est.get("precision_log") or []
        log.append(
            {
                "t": ahora.isoformat(),
                "nivel": nivel,
                "lado": p.get("lado"),
                "prob": p.get("prob"),
                "r": 1 if aguanto else 0,
            }
        )
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
    return {
        "n": n,
        "aciertos": ok_n,
        "tasa": round(ok_n / n, 3) if n else None,
        "banda_alta_n": len(altos),
        "banda_alta_ok": altos_ok,
        "banda_alta_tasa": round(altos_ok / len(altos), 3) if altos else None,
    }


def aplicar_gate_alerta(enviar, motivo, tipo, gate, forzado=None, gestion=None):
    """Devuelve (enviar, motivo, tipo, bloqueada). Puro y testeable."""
    if not enviar or tipo != "alerta":
        return enviar, motivo, tipo, False
    if forzado or gestion:
        return enviar, motivo, tipo, False
    if not isinstance(gate, dict):
        # P0-1.1 (auditoria 2026-10-29): antes, un gate no-dict (carga fallida)
        # dejaba PASAR la alerta direccional. Fail-closed: sin gate valido, se
        # silencia. Es el modo opuesto al de un bot que promete no mentir.
        return (False, "silenciada por validacion: gate invalido (fail-closed)",
                "nada", True)
    if gate.get("ok"):
        return enviar, motivo, tipo, False
    if not es_alerta_direccional(motivo):
        return enviar, motivo, tipo, False
    return False, f"silenciada por validacion: {gate.get('reason', 'sin evidencia')}", "nada", True
