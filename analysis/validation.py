"""Validation bot: control de calidad y calibracion del motor.

No ejecuta ordenes, no cambia el modelo y no usa IA. Responde una sola
pregunta: hay evidencia suficiente y estable para confiar en el aguante que
publica el motor, o la medicion esta rota/degradada?

Lee eval.json, backtest.json, decisions.jsonl y las velas. Escribe
validation.json y, opcionalmente, una linea en validation_history.jsonl.

Reglas:
- Menos de 30 muestras efectivas es ruido.
- 100+ muestras efectivas es el minimo para hablar de validacion.
- Las decisiones cada 15 min se solapan a 4h; se descuenta el solapamiento.
- Brier y calibracion miden aguante, no win rate.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import hold_model as hm
import paths

MIN_SAMPLES = 30
TARGET_SAMPLES = 100
MAX_KLINE_AGE_MIN = 30.0
PSI_WATCH = 0.10
PSI_ALERT = 0.25
ECE_WATCH = 0.05
ECE_ALERT = 0.08
SKILL_ALERT = -0.05
BIN_EDGES = (0.00, 0.60, 0.70, 0.80, 1.01)
BIN_LABELS = ("0.00-0.60", "0.60-0.70", "0.70-0.80", "0.80-1.01")
HISTORY_LIMIT = 500
DRIFT_VENTANA_H = 48.0   # ventana reciente para medir deriva (H6, pre-registrado)
DRIFT_MIN_PROBS = 30     # con menos probs vivas, PSI es ruido -> deriva indeterminada


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _load_jsonl(path: str) -> list[dict]:
    rows = []
    try:
        with open(path, encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    return rows


def _dt(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _round(value, digits: int = 4):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _prob_bin_counts(probs: list[float]) -> list[int]:
    counts = [0] * (len(BIN_EDGES) - 1)
    for raw in probs:
        try:
            p = float(raw)
        except (TypeError, ValueError):
            continue
        p = min(1.0, max(0.0, p))
        for i in range(len(BIN_EDGES) - 1):
            upper = BIN_EDGES[i + 1]
            if BIN_EDGES[i] <= p < upper or (i == len(counts) - 1 and p == upper):
                counts[i] += 1
                break
    return counts


def _bin_index(label: str) -> Optional[int]:
    try:
        low = float(str(label).split("-")[0])
    except (TypeError, ValueError):
        return None
    for i in range(len(BIN_EDGES) - 1):
        if abs(BIN_EDGES[i] - low) < 1e-9:
            return i
    return None


def _backtest_bin_counts(backtest: dict) -> Optional[list[int]]:
    bins = backtest.get("bins") or []
    counts = [0] * (len(BIN_EDGES) - 1)
    for row in bins:
        idx = _bin_index(row.get("bin", ""))
        if idx is None:
            continue
        try:
            counts[idx] += int(row.get("n") or 0)
        except (TypeError, ValueError):
            continue
    return counts if sum(counts) > 0 else None


def psi(expected: list[int], actual: list[int]) -> Optional[float]:
    """Population Stability Index con suavizado para bins vacios."""
    if not expected or not actual or sum(expected) <= 0 or sum(actual) <= 0:
        return None
    n = len(expected)
    e_total = float(sum(expected))
    a_total = float(sum(actual))
    value = 0.0
    for e, a in zip(expected, actual):
        e_pct = (float(e) + 0.5) / (e_total + 0.5 * n)
        a_pct = (float(a) + 0.5) / (a_total + 0.5 * n)
        value += (a_pct - e_pct) * math.log(a_pct / e_pct)
    return round(value, 4)


def _kline_quality(kl: list[dict], now: datetime) -> dict:
    if not kl:
        return {
            "ok": False,
            "error": "sin_klines",
            "bars": 0,
            "detail": "No hay velas para validar la frescura.",
        }
    kl = sorted(kl, key=lambda x: x["t"])
    times = [x["t"] for x in kl]
    unique = len(set(times))
    first = times[0]
    last = times[-1]
    age_min = max(0.0, (now - last).total_seconds() / 60.0)
    window_start = last - timedelta(hours=24)
    within = [t for t in times if t >= window_start]
    span_min = max(0.0, (last - max(first, window_start)).total_seconds() / 60.0)
    expected = max(1, min(288, int(span_min // 5) + 1))
    coverage = min(1.0, len(within) / expected) if expected else 0.0
    gaps = [
        (times[i] - times[i - 1]).total_seconds() / 60.0
        for i in range(1, len(times))
        if times[i] >= window_start
    ]
    max_gap = max(gaps) if gaps else 0.0
    duplicates = len(times) - unique
    ok = (
        age_min <= MAX_KLINE_AGE_MIN
        and coverage >= 0.95
        and max_gap <= 30.0
        and duplicates == 0
    )
    return {
        "ok": ok,
        "bars": len(times),
        "unique_bars": unique,
        "duplicates": duplicates,
        "first": first.isoformat(),
        "last": last.isoformat(),
        "age_min": round(age_min, 2),
        "coverage_24h": round(coverage, 4),
        "expected_24h": expected,
        "missing_24h": max(0, expected - len(within)),
        "max_gap_min": round(max_gap, 2),
        "max_age_min": MAX_KLINE_AGE_MIN,
    }


def _decision_samples(
    decisions: list[dict],
    kl: list[dict],
    horizon_bars: int,
) -> dict:
    events = sorted(
        {
            dt
            for rec in decisions
            for dt in [_dt(rec.get("event_time"))]
            if dt is not None
        }
    )
    all_probs: list[float] = []
    for rec in decisions:
        for level in rec.get("levels") or []:
            prob = level.get("hold_prob")
            if prob is not None:
                try:
                    all_probs.append(float(prob))
                except (TypeError, ValueError):
                    continue

    if not events or not kl:
        return {
            "events": len(events),
            "resolved_events": 0,
            "independent_events": 0,
            "coverage": 0.0,
            "levels_with_hold": len(all_probs),
            "resolved_levels": 0,
            "effective_samples": 0,
            "avg_levels_per_event": None,
            "span_hours": 0.0,
        }

    times = [x["t"] for x in sorted(kl, key=lambda x: x["t"])]
    resolved = []
    resolved_level_counts = []
    for rec in decisions:
        ev = _dt(rec.get("event_time"))
        if ev is None:
            continue
        idx = bisect.bisect_right(times, ev) - 1
        if idx < 0 or len(times) - idx - 1 < horizon_bars:
            continue
        resolved.append(ev)
        resolved_level_counts.append(
            sum(1 for level in rec.get("levels") or [] if level.get("hold_prob") is not None)
        )

    resolved = sorted(set(resolved))
    horizon = timedelta(minutes=5 * horizon_bars)
    independent = 0
    last: Optional[datetime] = None
    for ev in resolved:
        if last is None or ev - last >= horizon:
            independent += 1
            last = ev

    avg_levels = (
        sum(resolved_level_counts) / len(resolved_level_counts)
        if resolved_level_counts
        else None
    )
    effective = int(round(independent * (avg_levels or 0.0)))
    span_hours = (events[-1] - events[0]).total_seconds() / 3600.0 if len(events) > 1 else 0.0
    return {
        "events": len(events),
        "resolved_events": len(resolved),
        "independent_events": independent,
        "coverage": round(len(resolved) / len(events), 4) if events else 0.0,
        "levels_with_hold": len(all_probs),
        "resolved_levels": sum(resolved_level_counts),
        "effective_samples": effective,
        "avg_levels_per_event": _round(avg_levels, 2),
        "span_hours": round(span_hours, 1),
    }


def _sample_status(
    eval_samples: int,
    effective_samples: int,
    min_samples: int = MIN_SAMPLES,
    target_samples: int = TARGET_SAMPLES,
) -> str:
    if eval_samples <= 0:
        return "sin_muestras"
    if effective_samples < min_samples:
        return "muestra_chica"
    if effective_samples < target_samples:
        return "muestra_media"
    return "suficiente"


def _drift_summary(
    decisions: list[dict],
    backtest: dict,
    ahora: Optional[datetime] = None,
    ventana_horas: Optional[float] = None,
) -> dict:
    """PSI entre la distribucion de probabilidades vivas y la del backtest OOS.

    La deriva se mide sobre una ventana RECIENTE (por defecto 48 h). Comparar
    contra todo el historico mezcla versiones del modelo y hace la metrica
    pegajosa: decisiones viejas nunca salen del log. Lo que importa es si el
    regimen de ahora se parece al que el modelo vio fuera de muestra.
    Pre-registro: analysis/EXPERIMENTOS.md (H6).
    """
    if ventana_horas is None:
        ventana_horas = DRIFT_VENTANA_H
    if ahora is None:
        ahora = datetime.now(timezone.utc)

    limite = ahora - timedelta(hours=ventana_horas)
    live_probs = []
    usadas = 0
    for rec in decisions:
        ev = rec.get("event_time") or rec.get("t")
        if not ev:
            continue
        try:
            t = datetime.fromisoformat(str(ev).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if t < limite:
            continue
        usadas += 1
        for level in rec.get("levels") or []:
            prob = level.get("hold_prob")
            if prob is None:
                continue
            try:
                live_probs.append(float(prob))
            except (TypeError, ValueError):
                continue
    live_counts = _prob_bin_counts(live_probs)
    backtest_counts = _backtest_bin_counts(backtest)
    value = psi(backtest_counts or [], live_counts)
    if len(live_probs) < DRIFT_MIN_PROBS:
        # PSI sobre pocas muestras es ruido: la derivaqueda indeterminada.
        status = "sin_datos"
        value = None
    elif value is None:
        status = "sin_datos"
    elif value >= PSI_ALERT:
        status = "alert"
    elif value >= PSI_WATCH:
        status = "watch"
    else:
        status = "ok"
    live_mean = _mean(live_probs)
    backtest_mean = backtest.get("mean_prob")
    shift = None
    if live_mean is not None and backtest_mean is not None:
        try:
            shift = round(live_mean - float(backtest_mean), 4)
        except (TypeError, ValueError):
            shift = None
    return {
        "status": status,
        "psi": value,
        "watch_threshold": PSI_WATCH,
        "alert_threshold": PSI_ALERT,
        "live_bins": [
            {"bin": label, "n": count} for label, count in zip(BIN_LABELS, live_counts)
        ],
        "backtest_bins": (
            [
                {"bin": label, "n": count}
                for label, count in zip(BIN_LABELS, backtest_counts)
            ]
            if backtest_counts is not None
            else []
        ),
        "live_mean_prob": _round(live_mean, 4),
        "backtest_mean_prob": _round(backtest_mean, 4),
        "mean_shift": shift,
        "detail": (
            "PSI compara la distribucion de probabilidades vivas contra el "
            "backtest OOS. No mide resultados; detecta cambio de regimen."
        ),
    }


def _overall_status(
    *,
    data_ok: bool,
    eval_samples: int,
    effective_samples: int,
    metrics: dict,
    drift: dict,
    min_samples: int = MIN_SAMPLES,
    target_samples: int = TARGET_SAMPLES,
) -> str:
    if not data_ok:
        return "roto"
    if eval_samples <= 0:
        return "sin_muestras"
    skill = metrics.get("brier_skill")
    ece = metrics.get("calibration_error")
    degraded = (
        (skill is not None and skill < SKILL_ALERT)
        or (ece is not None and ece > ECE_ALERT)
        or drift.get("status") == "alert"
    )
    if degraded and effective_samples >= min_samples:
        return "degradado"
    if effective_samples < min_samples:
        return "muestra_chica"
    if effective_samples < target_samples:
        return "muestra_media"
    if skill is not None and skill < 0:
        return "vigilar"
    if ece is not None and ece > ECE_WATCH:
        return "vigilar"
    return "ok"


def _ece_from_bins(bins) -> Optional[float]:
    """Error de calibracion ponderado (EEP) desde los bins del backtest."""
    if not isinstance(bins, list) or not bins:
        return None
    total = 0
    acc = 0.0
    for b in bins:
        if not isinstance(b, dict):
            continue
        try:
            n = int(b.get("n") or 0)
            pred = float(b.get("pred") or 0.0)
            real = float(b.get("real") or 0.0)
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        total += n
        acc += abs(pred - real) * n
    if total <= 0:
        return None
    return round(acc / total, 4)


def oos_summary(backtest: dict, horizon: int = 48) -> dict:
    """Canal OOS: resume analysis/data/backtest.json como evidencia purgada.

    Con step >= horizon las ventanas de etiquetado NO se solapan: cada decision
    es independiente y las muestras efectivas son las muestras etiquetadas.
    Con step < horizon se descuenta por solapamiento, igual que el canal vivo.
    """
    if not isinstance(backtest, dict) or not backtest.get("ok"):
        return {"available": False}
    try:
        samples = int(backtest.get("samples") or 0)
        decisions = int(backtest.get("decisions") or 0)
    except (TypeError, ValueError):
        return {"available": False}
    if samples <= 0 or decisions <= 0:
        return {"available": False}
    try:
        step = int(backtest.get("step_bars") or horizon)
    except (TypeError, ValueError):
        step = horizon
    try:
        bars = int(backtest.get("horizon_bars") or horizon)
    except (TypeError, ValueError):
        bars = horizon
    factor = 1.0
    if step > 0 and step < bars:
        # Cada decision se solapa con las siguientes (bars/step - 1): se descuenta.
        factor = max(0.0, min(1.0, step / bars))
    effective = int(round(samples * factor))
    try:
        skill = backtest.get("brier_skill")
        skill = float(skill) if skill is not None else None
    except (TypeError, ValueError):
        skill = None
    return {
        "available": True,
        "samples": samples,
        "decisions": decisions,
        "effective": effective,
        "brier": _round(backtest.get("brier")),
        "brier_skill": _round(skill),
        "base_rate": _round(backtest.get("base_rate")),
        "mean_prob": _round(backtest.get("mean_prob")),
        "ece": _ece_from_bins(backtest.get("bins")),
        "step_bars": step,
        "horizon_bars": bars,
        "solape_descontado": factor < 1.0,
        "start": backtest.get("start"),
        "end": backtest.get("end"),
        "trained_until": backtest.get("trained_until") or hm.MODEL.get("trained_until"),
    }


def oos_valido(oos: dict, drift: dict, min_samples: int = TARGET_SAMPLES) -> bool:
    """El canal OOS aporta evidencia suficiente para confiar en la calibracion."""
    if not isinstance(oos, dict) or not oos.get("available"):
        return False
    if isinstance(drift, dict) and drift.get("status") == "alert":
        return False
    effective = int(oos.get("effective") or 0)
    skill = oos.get("brier_skill")
    ece = oos.get("ece")
    if effective < min_samples:
        return False
    if skill is None or skill <= 0:
        return False
    if ece is None or ece > ECE_ALERT:
        return False
    return True


def _warnings(
    *,
    eval_data: dict,
    eval_samples: int,
    sample_info: dict,
    metrics: dict,
    backtest: dict,
    oos_arg: Optional[dict] = None,
    drift: dict,
    kline: dict,
    data_ok: bool,
) -> list[str]:
    out = []
    if not data_ok:
        out.append("Datos incompletos: el validador no puede certificar frescura.")
    if eval_samples <= 0:
        out.append("Aun no hay decisiones con 4h de futuro y aguante calculado.")
    effective = int(sample_info.get("effective_samples") or 0)
    if eval_samples > 0 and effective < MIN_SAMPLES:
        out.append(
            f"Muestra efectiva {effective} < {MIN_SAMPLES}; el resultado es ruido."
        )
    elif eval_samples > 0 and effective < TARGET_SAMPLES:
        out.append(
            f"Muestra efectiva {effective} < {TARGET_SAMPLES}; falta recorrido para validar."
        )
    nominal = int(sample_info.get("resolved_levels") or 0)
    if nominal and effective and nominal != effective:
        out.append(
            f"Muestras nominales {nominal}; efectivas {effective} por solapamiento de 4h."
        )
    skill = metrics.get("brier_skill")
    if skill is not None and skill < 0:
        out.append("Brier skill negativo: el motor no supera la tasa base en esta muestra.")
    ece = metrics.get("calibration_error")
    if ece is not None and ece > ECE_WATCH:
        out.append(f"Calibracion {ece:.4f} > {ECE_WATCH:.2f}; revisar bins.")
    if drift.get("status") == "alert":
        out.append("Drift alto en la distribucion de probabilidades; revisar regimen.")
    elif drift.get("status") == "sin_datos":
        out.append("Drift sin datos suficientes para comparar.")
    bt_samples = int(backtest.get("samples") or 0)
    if bt_samples and bt_samples < TARGET_SAMPLES:
        out.append(
            f"Backtest OOS con {bt_samples} muestras; no certifica edge predictivo."
        )
    bt_skill = backtest.get("brier_skill")
    if bt_skill is not None and bt_skill <= 0:
        out.append("Backtest OOS sin Brier skill positivo; no hay edge demostrado.")
    oos = oos_arg if isinstance(oos_arg, dict) else {}
    if oos.get("available"):
        oos_skill = oos.get("brier_skill")
        if oos_skill is not None and 0 < oos_skill < 0.01:
            out.append(
                f"Skill OOS positivo pero marginal ({oos_skill:+.4f}); "
                "la puerta OOS es evidencia debil, mantener el seguimiento vivo."
            )
        if oos.get("solape_descontado"):
            out.append("Backtest OOS con step < horizon: se desconto el solapamiento.")
    if kline.get("missing_24h"):
        out.append(f"Faltan {kline['missing_24h']} velas 5m en las ultimas 24h.")
    if kline.get("max_gap_min", 0) > 30:
        out.append(f"Gap maximo de {kline['max_gap_min']} min en velas.")
    if eval_data.get("status") == "sin_muestras":
        out.append("eval.json confirma cero muestras resueltas.")
    return out


def _headline(status: str, effective: int) -> str:
    if status == "roto":
        return "Validacion rota: faltan datos o hay gaps graves."
    if status == "sin_muestras":
        return "Sin muestras resueltas: aun no se puede validar el aguante."
    if status == "muestra_chica":
        return f"Muestra chica ({effective} efectivas): ruido, no cambiar el modelo."
    if status == "muestra_media":
        return f"Muestra media ({effective} efectivas): medicion en curso, sin certificar."
    if status == "vigilar":
        return "Muestra suficiente, pero calibracion/skill en zona de vigilancia."
    if status == "degradado":
        return "Validacion degradada: revisar calibracion y drift antes de confiar."
    return "Validacion estable: muestra suficiente y calibracion aceptable."


def _data_hash(
    eval_path: str,
    backtest_path: str,
    decisions_path: str,
    kl: list[dict],
) -> str:
    digest = hashlib.sha256()
    for path in (eval_path, backtest_path, decisions_path):
        try:
            with open(path, "rb") as fh:
                digest.update(fh.read())
        except OSError:
            digest.update(b"missing")
    if kl:
        digest.update(
            f"{len(kl)}|{kl[0]['t'].isoformat()}|{kl[-1]['t'].isoformat()}".encode(
                "utf-8"
            )
        )
    return digest.hexdigest()[:16]


def _append_history(path: str, row: dict, limit: int = HISTORY_LIMIT) -> None:
    rows = _load_jsonl(path)
    checked = row.get("checked_at")
    rows = [r for r in rows if r.get("checked_at") != checked]
    rows.append(row)
    rows = rows[-limit:]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for item in rows:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def validate(
    eval_path: str,
    backtest_path: str,
    decisions_path: str,
    klines_path: str,
    collector_health_path: Optional[str] = None,
    horizon: int = 48,
    now: Optional[datetime] = None,
    min_samples: int = MIN_SAMPLES,
    target_samples: int = TARGET_SAMPLES,
) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    eval_data = _read_json(eval_path) or {}
    backtest = _read_json(backtest_path) or {}
    decisions = _load_jsonl(decisions_path)
    try:
        kl = hm.load_klines_jsonl(klines_path)
    except (OSError, KeyError, TypeError, ValueError):
        kl = []

    eval_samples = int(eval_data.get("samples") or 0)
    sample_info = _decision_samples(decisions, kl, horizon)
    effective = int(sample_info.get("effective_samples") or 0)
    if effective <= 0 and eval_samples > 0:
        effective = eval_samples
        sample_info["effective_samples"] = effective
        sample_info["effective_fallback"] = "eval_samples"
    sample_status = _sample_status(
        eval_samples, effective, min_samples, target_samples
    )

    metrics = {
        "brier": _round(eval_data.get("brier")),
        "brier_skill": _round(eval_data.get("brier_skill")),
        "base_rate": _round(eval_data.get("base_rate")),
        "mean_prob": _round(eval_data.get("mean_prob")),
        "calibration_error": _round(eval_data.get("calibration_error")),
        "eval_status": eval_data.get("status"),
        "bins": eval_data.get("bins") or [],
        "high_score": eval_data.get("high_score") or {},
        "by_side": eval_data.get("by_side") or {},
        "coverage": _round(eval_data.get("coverage")),
    }

    kline = _kline_quality(kl, now)
    collector = _read_json(collector_health_path) if collector_health_path else None
    collector_info = {
        "available": collector is not None,
        "ok": bool(collector.get("ok")) if collector else None,
        "kline_ok": bool(collector.get("kline_ok")) if collector else None,
        "run_at": collector.get("run_at") if collector else None,
        "failed_jobs": [
            name
            for name, row in ((collector or {}).get("jobs") or {}).items()
            if isinstance(row, dict) and not row.get("ok")
        ]
        if collector
        else [],
    }
    data_ok = bool(kline.get("ok")) and bool(eval_data)
    if collector is not None and collector.get("kline_ok") is False:
        # Solo los datos que el motor USA (velas) pueden romper la validacion.
        # Los derivados bloqueados legal/geografico (p. ej. top-traders 451 desde
        # IP de EE.UU.) quedan registrados en failed_jobs y en warnings.
        data_ok = False

    drift = _drift_summary(decisions, backtest, ahora=now)
    oos = oos_summary(backtest)
    oos_ok = data_ok and oos_valido(oos, drift)
    status = _overall_status(
        data_ok=data_ok,
        eval_samples=eval_samples,
        effective_samples=effective,
        metrics=metrics,
        drift=drift,
        min_samples=min_samples,
        target_samples=target_samples,
    )
    warnings = _warnings(
        eval_data=eval_data,
        eval_samples=eval_samples,
        sample_info=sample_info,
        metrics=metrics,
        backtest=backtest,
        oos_arg=oos,
        drift=drift,
        kline=kline,
        data_ok=data_ok,
    )

    backtest_summary = {
        "samples": int(backtest.get("samples") or 0),
        "decisions": int(backtest.get("decisions") or 0),
        "status": backtest.get("status"),
        "brier": _round(backtest.get("brier")),
        "brier_skill": _round(backtest.get("brier_skill")),
        "base_rate": _round(backtest.get("base_rate")),
        "start": backtest.get("start"),
        "end": backtest.get("end"),
        "trained_until": backtest.get("trained_until") or hm.MODEL.get("trained_until"),
    }

    if status == "ok":
        canal = "vivo"
    elif oos_ok:
        canal = "oos"
    else:
        canal = "ninguno"

    return {
        "ok": status != "roto",
        "bot": "validation",
        "version": 1,
        "checked_at": now.isoformat(),
        "status": status,
        "healthy": status == "ok",
        "sample_status": sample_status,
        "headline": _headline(status, effective),
        "horizon_bars": horizon,
        "horizon_hours": round(horizon * 5 / 60.0, 2),
        "min_samples": min_samples,
        "target_samples": target_samples,
        "samples": {
            "eval": eval_samples,
            "effective": effective,
            "resolved_levels": sample_info.get("resolved_levels"),
            "levels_with_hold": sample_info.get("levels_with_hold"),
            "events": sample_info.get("events"),
            "resolved_events": sample_info.get("resolved_events"),
            "independent_events": sample_info.get("independent_events"),
            "coverage": sample_info.get("coverage"),
            "avg_levels_per_event": sample_info.get("avg_levels_per_event"),
            "span_hours": sample_info.get("span_hours"),
            "effective_fallback": sample_info.get("effective_fallback"),
        },
        "metrics": metrics,
        "backtest": backtest_summary,
        "oos": oos,
        "gate": {
            "ok": canal != "ninguno",
            "canal": canal,
            "detalle": (
                "vivo: 100+ efectivas, skill>0, ECE<=0.08"
                if canal == "vivo"
                else "oos: 100+ efectivas, skill>0, ECE<=0.08"
                if canal == "oos"
                else "sin canal con evidencia suficiente"
            ),
        },
        "drift": drift,
        "data": {
            "klines": kline,
            "collector": collector_info,
        },
        "model": {
            "version": hm.MODEL.get("version"),
            "target": hm.MODEL.get("target"),
            "trained_until": hm.MODEL.get("trained_until"),
            "holdout_2026": hm.MODEL.get("holdout_2026"),
        },
        "warnings": warnings,
        "limits": [
            "Mide aguante de nivel a 4h, no win rate ni ganancia.",
            "La muestra efectiva descuenta el solapamiento de decisiones cada 15 min.",
            "100+ muestras y Brier skill positivo son el minimo para hablar de validacion.",
            "No cambia el modelo, no ejecuta ordenes y no usa IA para decidir.",
        ],
        "data_hash": _data_hash(eval_path, backtest_path, decisions_path, kl),
        "code_sha": os.environ.get("GITHUB_SHA"),
        "disclaimer": (
            "Auditoria interna de calibracion. No es certificacion externa ni "
            "garantia de rentabilidad. Muestra chica = ruido."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validation bot del aguante BTC")
    ap.add_argument("--eval", default="data/eval.json")
    ap.add_argument("--backtest", default="data/backtest.json")
    ap.add_argument("--decisions", default=paths.default_decisions_path())
    ap.add_argument("--klines", default=paths.default_klines_path())
    ap.add_argument("--collector-health", default=None)
    ap.add_argument("--out", default="data/validation.json")
    ap.add_argument("--history", default="data/validation_history.jsonl")
    ap.add_argument("--horizon", type=int, default=48, help="velas 5m; 48 = 4h")
    ap.add_argument("--now", default=None, help="ISO-8601 para pruebas")
    ap.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    ap.add_argument("--target-samples", type=int, default=TARGET_SAMPLES)
    ap.add_argument("--strict", action="store_true", help="salir 1 si status=roto")
    args = ap.parse_args()

    result = validate(
        eval_path=args.eval,
        backtest_path=args.backtest,
        decisions_path=args.decisions,
        klines_path=args.klines,
        collector_health_path=args.collector_health,
        horizon=args.horizon,
        now=_dt(args.now) if args.now else None,
        min_samples=args.min_samples,
        target_samples=args.target_samples,
    )
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, default=str)
    if args.history:
        _append_history(
            args.history,
            {
                "checked_at": result["checked_at"],
                "status": result["status"],
                "sample_status": result["sample_status"],
                "eval_samples": result["samples"]["eval"],
                "effective_samples": result["samples"]["effective"],
                "brier": result["metrics"]["brier"],
                "brier_skill": result["metrics"]["brier_skill"],
                "calibration_error": result["metrics"]["calibration_error"],
                "drift_status": result["drift"]["status"],
                "drift_psi": result["drift"]["psi"],
                "backtest_samples": result["backtest"]["samples"],
                "backtest_skill": result["backtest"]["brier_skill"],
                "data_hash": result["data_hash"],
            },
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if args.strict and result["status"] == "roto":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
