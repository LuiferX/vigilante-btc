"""Evalua el aguante registrado por run_decision.py.

No mide win rate ni ganancia. Mide si el nivel aguanto 4h segun la misma
definicion del modelo: cierre 0,5% mas alla del nivel. Compara la
probabilidad con el resultado (Brier) y muestra calibracion por tramos.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
from datetime import datetime, timezone
from typing import Optional

import hold_model as hm
import paths


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


def evaluate(decisions_path: str, klines_path: str, horizon: int = 48) -> dict:
    decisions = _load_jsonl(decisions_path)
    kl = hm.load_klines_jsonl(klines_path)
    if not kl:
        return {"ok": False, "error": "sin_klines"}
    kl = sorted(kl, key=lambda x: x["t"])
    times = [x["t"] for x in kl]

    seen = set()
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
            "detail": "Aun no hay decisiones con 4h de futuro y aguante calculado.",
        }

    n = len(samples)
    brier = sum((s["prob"] - s["label"]) ** 2 for s in samples) / n
    base = sum(s["label"] for s in samples) / n
    bins = []
    for lo, hi in ((0.0, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 1.01)):
        group = [s for s in samples if lo <= s["prob"] < hi]
        if not group:
            continue
        bins.append(
            {
                "bin": f"{lo:.2f}-{hi:.2f}",
                "n": len(group),
                "pred": round(sum(s["prob"] for s in group) / len(group), 4),
                "real": round(sum(s["label"] for s in group) / len(group), 4),
            }
        )
    high = [s for s in samples if s["prob"] >= 0.80]
    return {
        "ok": True,
        "samples": n,
        "brier": round(brier, 4),
        "base_rate": round(base, 4),
        "high_score": {
            "n": len(high),
            "pred": round(sum(s["prob"] for s in high) / len(high), 4) if high else None,
            "real": round(sum(s["label"] for s in high) / len(high), 4) if high else None,
        },
        "bins": bins,
        "disclaimer": (
            "Mide aguante de nivel, no win rate. Muestra chica = ruido; "
            "no cambiar el modelo por un solo corte."
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
