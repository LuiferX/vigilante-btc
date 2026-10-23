#!/usr/bin/env python3
"""
estado.py - PERSISTENCIA Y ANTI-SPAM del Vigilante (Fase 2 de modularizacion).

Extraido 1:1 de vigilante_cloud.py. Maneja estado.json / historial.jsonl
(lectura tolerante, poda con cota dura, escritura atomica), el anti-spam por
categoria (enfriar) y los topes de crecimiento. vigilante_cloud.py re-exporta
estos nombres: la API publica no cambia.
"""

import datetime
import json
import os

ESTADO_FILE = "estado.json"


HIST_FILE = "historial.jsonl"


MAX_HIST = 1500


MAX_PEND_TODO = 100


MAX_EVAL_TODO = 200


MAX_PAPER_ABIERTAS = 5


MAX_OPS = 20


MAX_DELTAS = 25


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
    est = {
        "ultimo_bias": "?",
        "ultima_conf": 0,
        "ultimo_precio": 0,
        "ultimo_run": "",
        "ultimo_resumen": "",
        "ultimo_resumen_noche": "",
        "alza": [],
        "baja": [],
        "pendientes": [],
        "offset": 0,
        "runs": 0,
        "vistas": [],
    }
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
            est["cools"] = dict(
                sorted(est["cools"].items(), key=lambda kv: str(kv[1] or ""))[-200:]
            )
        if isinstance(est.get("pilas"), dict) and len(est["pilas"]) > 200:
            est["pilas"] = dict(list(est["pilas"].items())[-200:])
        if isinstance(est.get("preavisos"), dict) and len(est["preavisos"]) > 100:
            est["preavisos"] = dict(list(est["preavisos"].items())[-100:])
        for k, n in (
            ("pend_todo", MAX_PEND_TODO),
            ("eval_todo", MAX_EVAL_TODO),
            ("pend_sombra", MAX_PEND_TODO),
            ("eval_sombra", MAX_EVAL_TODO),
            ("pendientes", MAX_PEND_TODO),
            ("eval_log", MAX_EVAL_TODO),
            ("pend_gate", MAX_PEND_TODO),
            ("eval_gate", MAX_EVAL_TODO),
            ("alza_gate", 50),
            ("baja_gate", 50),
            ("paper_abiertas", MAX_PAPER_ABIERTAS),
            ("ops", MAX_OPS),
            ("journal", 50),
            ("sim_cerradas", 20),
            ("paper_cerradas", 100),
        ):
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
