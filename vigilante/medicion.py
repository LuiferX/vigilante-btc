#!/usr/bin/env python3
"""
medicion.py - MEDICION (Fase 7): precision MFE/MAE a 8h, sombra, todo,
contrafactual del gate, calibracion por sesion, scoreboard y plan de entrada.
"""

import datetime

from vigilante.estado import MAX_EVAL_TODO, MAX_PEND_TODO
from vigilante.indicadores import (
    direccion_alerta,
    sesion_bucket,
)
from vigilante.red import klines

EVAL_HORAS = 8


UMBRAL_MOV = 0.002


DEDUP_HORAS = 4  # misma direccion en 4 h = 1 sola senal (sin duplicados)


SEMILLA_SESION = {"NY": 1.0, "Londres": 1.0, "noche": 1.0, "Asia": 1.0}  # neutra: ver doc


def auto_stats(eval_log):
    """Auto-aprendizaje: en que sesion rinden mejor las senales (min 10 evaluadas)."""
    if len(eval_log) < 10:
        return None
    buckets: dict[str, list] = {}
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
    buckets: dict[str, list] = {}
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


def precision_plan(est):
    """Acierto por direccion del PLAN, no por sesgo. None si aun no hay muestra.

    Se apoya en `eval_log` (metodo=plan, dir=ALZA/BAJA). El historico viejo
    no tiene `metodo` y se queda fuera para no repetir el error anterior.
    """
    try:
        log = [
            e
            for e in (est.get("eval_log", []) or [])
            if isinstance(e, dict)
            and e.get("metodo") == "plan"
            and e.get("dir") in ("ALZA", "BAJA")
        ]
        if not log:
            return None
        return (
            [1 if e.get("r") else 0 for e in log if e.get("dir") == "ALZA"],
            [1 if e.get("r") else 0 for e in log if e.get("dir") == "BAJA"],
        )
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
        plan = [
            e
            for e in (est.get("eval_log", []) or [])
            if isinstance(e, dict) and e.get("metodo") == "plan"
        ]
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
        brier = sum(
            ((float(e.get("conf", 50)) / 100) - float(e.get("r", 0))) ** 2 for e in log
        ) / len(log)
        # cubs[cubeta] = [evaluadas, aciertos]
        cubs: dict[str, list[float]] = {}
        for e in log:
            c = float(e.get("conf", 50))
            k = "40s" if c < 50 else ("50s" if c < 60 else "60+")
            a, b = cubs.get(k, [0, 0])
            cubs[k] = [a + 1, b + float(e.get("r", 0))]
        return {
            "n": len(log),
            "brier": round(brier, 3),
            "cubetas": {k: (n, round(100 * w / n)) for k, (n, w) in sorted(cubs.items())},
        }
    except Exception:
        return None


def evaluar_mfe(
    est,
    ahora,
    velas=None,
    pend_key="pendientes",
    log_key="eval_log",
    alza_key="alza",
    baja_key="baja",
    metodo="plan",
):
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
        log.append(
            {
                "b": p.get("bias"),
                "dir": direc,
                "r": hit,
                "t": ahora.isoformat(),
                "conf": p.get("conf", 0),
                "mfe": round(mfe, 4),
                "mae": round(mae, 4),
                "tipo": p.get("tipo") or "?",
                "metodo": _metodo_p,
            }
        )
        est[log_key] = log[-200:]
    est[pend_key] = nuevas[-100:]


def registrar_pend_gate(
    est, ahora, precio, dirb, dir_alerta, tipo, motivo, gate_reason, umbral, h1, h4, senti, fg
):
    """Guarda una alerta silenciada para medirla despues. No la envia.

    Dedup 4h por direccion. Devuelve True si la registro. Es contrafactual:
    `eval_gate` nunca se mezcla con el scoreboard de alertas enviadas.
    """
    if dir_alerta not in ("ALZA", "BAJA"):
        return False
    for p in est.get("pend_gate", []):
        try:
            _pd = (
                p.get("dir")
                or direccion_alerta(p.get("motivo", ""), p.get("bias"))
                or p.get("bias")
            )
            if (
                _pd == dir_alerta
                and (ahora - datetime.datetime.fromisoformat(p["t"])).total_seconds() / 3600
                < DEDUP_HORAS
            ):
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
        {
            "t": ahora.isoformat(),
            "precio": round(precio),
            "bias": dirb.get("bias") if isinstance(dirb, dict) else None,
            "dir": dir_alerta,
            "conf": _conf,
            "tipo": tipo,
            "motivo": str(motivo or "")[:200],
            "gate": gate_reason,
            "risk": _risk,
            "feat": {
                "rsi": (h1 or {}).get("rsi"),
                "adx": (h4 or {}).get("adx", 0),
                "fund": (senti or {}).get("funding"),
                "taker": (senti or {}).get("taker"),
                "fg": (fg or {}).get("valor"),
            },
        }
    ]
    return True


def abrir_todo(est, bias, conf, precio, umbral, ahora):
    """Todo: registra CADA pasada (hable o calle) para medir si callar fue correcto.
    No alerta, no opera, no toca nada vivo. Dedup 1h por sesgo."""
    try:
        if bias not in ("ALZA", "BAJA", "LATERAL"):
            return False
        pu = est.get("todo_ult") or {}
        try:
            if (
                pu.get("dir") == bias
                and (ahora - datetime.datetime.fromisoformat(pu.get("t", ""))).total_seconds()
                / 3600
                < 1
            ):
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
        ps.append(
            {
                "t": ahora.isoformat(),
                "precio": round(precio),
                "bias": bias,
                "conf": conf,
                "risk": round(umbral * precio, 1),
            }
        )
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
                log.append(
                    {
                        "b": p["bias"],
                        "r": hit,
                        "t": ahora.isoformat(),
                        "conf": p.get("conf", 0),
                        "mfe": round(mfe, 4),
                        "mae": round(mae, 4),
                    }
                )
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
            if (
                pu.get("dir") == bias
                and (ahora - datetime.datetime.fromisoformat(pu.get("t", ""))).total_seconds()
                / 3600
                < DEDUP_HORAS
            ):
                return False
        except Exception:
            pass
        ps = est.get("pend_sombra", [])
        ps.append(
            {
                "t": ahora.isoformat(),
                "precio": round(precio),
                "bias": bias,
                "conf": conf,
                "risk": round(umbral * precio, 1),
            }
        )
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
                log.append(
                    {
                        "b": p["bias"],
                        "r": hit,
                        "t": ahora.isoformat(),
                        "conf": p.get("conf", 0),
                        "mfe": round(mfe, 4),
                        "mae": round(mae, 4),
                    }
                )
                est["eval_sombra"] = log[-MAX_EVAL_TODO:]
            except Exception:
                continue
        est["pend_sombra"] = nuevas[-MAX_PEND_TODO:]
    except Exception:
        pass


MIN_SENALES = 5  # minimo de senales para mostrar % de precision


def prec_str(lista):
    if len(lista) < MIN_SENALES:
        return f"pocas ({len(lista)})" if lista else "s/d"
    ok = sum(lista)
    return f"{round(ok / len(lista) * 100)}% ({ok}/{len(lista)})"
