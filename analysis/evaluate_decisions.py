"""Evalua el aguante registrado por run_decision.py.

No mide win rate ni ganancia. Mide si el nivel aguanto 4h segun la misma
definicion del modelo: cierre 0,5% mas alla del nivel. Compara la
probabilidad con el resultado (Brier), calcula skill frente a la tasa base,
calibracion por tramos e intervalos de Wilson.

Regla de lectura: con menos de 30 muestras el resultado es ruido. No se
cambia el modelo por un corte chico.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import os
from datetime import datetime, timezone
from typing import Optional

import hold_model as hm
import paths


MIN_SAMPLES_RECOMMENDED = 30


def _load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
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


def level_holds(future: list[dict], level: float, side: str) -> bool:
    """True si el nivel aguanto: ningun cierre 0,5% mas alla en el futuro."""
    if side == "soporte":
        return all(x["c"] >= level * 0.995 for x in future)
    return all(x["c"] <= level * 1.005 for x in future)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> Optional[list[float]]:
    """Intervalo de confianza 95% para una proporcion (Wilson)."""
    if n <= 0:
        return None
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n) / denom
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def _stats(samples: list[dict]) -> dict:
    n = len(samples)
    if n == 0:
        return {"n": 0}
    labels = [s["label"] for s in samples]
    probs = [s["prob"] for s in samples]
    base = sum(labels) / n
    brier = sum((p - y) ** 2 for p, y in zip(probs, labels)) / n
    brier_base = base * (1.0 - base)
    skill = 1.0 - brier / brier_base if brier_base > 0 else None
    return {
        "n": n,
        "brier": round(brier, 4),
        "base_rate": round(base, 4),
        "mean_prob": round(sum(probs) / n, 4),
        "brier_base": round(brier_base, 4),
        "brier_skill": round(skill, 4) if skill is not None else None,
        "real_ci95": wilson_interval(sum(labels), n),
    }


def evaluate(decisions_path: str, klines_path: str, horizon: int = 48) -> dict:
    decisions = _load_jsonl(decisions_path)
    kl = hm.load_klines_jsonl(klines_path)
    if not kl:
        return {"ok": False, "error": "sin_klines"}
    kl = sorted(kl, key=lambda x: x["t"])
    times = [x["t"] for x in kl]

    seen = set()
    evaluated_events = set()
    samples = []
    for rec in decisions:
        ev = _dt(rec.get("event_time"))
        if ev is None or ev in seen:
            continue
        seen.add(ev)
        idx = bisect.bisect_right(times, ev) - 1
        if idx < 0:
            continue
        future = kl[idx + 1 : idx + 1 + horizon]
        if len(future) < horizon:
            continue
        evaluated_events.add(ev)
        for lvl in rec.get("levels", []):
            prob = lvl.get("hold_prob")
            if prob is None:
                continue
            side = lvl.get("role")
            level = float(lvl["center"])
            label = 1 if level_holds(future, level, side) else 0
            samples.append(
                {
                    "event_time": rec["event_time"],
                    "level": level,
                    "side": side,
                    "prob": float(prob),
                    "label": label,
                    "quality": lvl.get("quality"),
                }
            )

    if not samples:
        return {
            "ok": True,
            "samples": 0,
            "status": "sin_muestras",
            "decisions_total": len(seen),
            "min_samples_recommended": MIN_SAMPLES_RECOMMENDED,
            "detail": "Aun no hay decisiones con 4h de futuro y aguante calculado.",
        }

    overall = _stats(samples)
    n = overall["n"]
    status = "ok" if n >= MIN_SAMPLES_RECOMMENDED else "muestra_chica"

    bins = []
    for lo, hi in ((0.0, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 1.01)):
        group = [s for s in samples if lo <= s["prob"] < hi]
        if not group:
            continue
        labels = [s["label"] for s in group]
        bins.append(
            {
                "bin": f"{lo:.2f}-{hi:.2f}",
                "n": len(group),
                "pred": round(sum(s["prob"] for s in group) / len(group), 4),
                "real": round(sum(labels) / len(labels), 4),
                "real_ci95": wilson_interval(sum(labels), len(labels)),
            }
        )

    weighted_gap = sum(abs(b["pred"] - b["real"]) * b["n"] for b in bins) / n
    high = [s for s in samples if s["prob"] >= 0.80]
    high_stats = _stats(high)
    if high_stats.get("n"):
        high_stats["lift_vs_base"] = round(
            high_stats["base_rate"] / overall["base_rate"], 4
        ) if overall["base_rate"] else None

    by_side = {}
    for side in ("soporte", "resistencia"):
        group = [s for s in samples if s["side"] == side]
        if group:
            by_side[side] = _stats(group)

    return {
        "ok": True,
        "samples": n,
        "status": status,
        "decisions_total": len(seen),
        "decisions_evaluated": len(evaluated_events),
        "coverage": round(len(evaluated_events) / len(seen), 4) if seen else 0.0,
        "horizon_bars": horizon,
        "horizon_hours": round(horizon * 5 / 60.0, 2),
        "min_samples_recommended": MIN_SAMPLES_RECOMMENDED,
        "brier": overall["brier"],
        "base_rate": overall["base_rate"],
        "mean_prob": overall["mean_prob"],
        "brier_base": overall["brier_base"],
        "brier_skill": overall["brier_skill"],
        "calibration_error": round(weighted_gap, 4),
        "overall": overall,
        "high_score": high_stats,
        "by_side": by_side,
        "bins": bins,
        "disclaimer": (
            "Mide aguante de nivel, no win rate. Muestra chica = ruido; "
            "no cambiar el modelo por un solo corte. Brier_skill > 0 es mejor "
            "que predecir la tasa base."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluacion del aguante registrado")
    ap.add_argument("--decisions", default=paths.default_decisions_path())
    ap.add_argument("--klines", default=paths.default_klines_path())
    ap.add_argument("--out", default="data/eval.json")
    ap.add_argument("--horizon", type=int, default=48, help="velas 5m; 48 = 4h")
    args = ap.parse_args()

    out = evaluate(args.decisions, args.klines, horizon=args.horizon)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
