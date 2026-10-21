"""Backtest OOS del aguante que produce el motor de decision.

No ejecuta ordenes. Recorre velas historicas, construye el contexto solo con
datos disponibles en ese momento y mide si los niveles con 3+ toques aguantaron
las siguientes 4h. Sirve para ver si el motor sigue calibrado fuera del periodo
de entrenamiento del modelo.

Ejemplo:
    python analysis/backtest.py --start 2026-10-01 --out analysis/data/backtest.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Optional

import decision_engine as de
import evaluate_decisions as ev
import hold_model as hm
import paths


def _dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _slice_htf(htf: dict[str, list[dict]], cutoff: datetime) -> dict[str, list[dict]]:
    return {
        key: [row for row in rows if row.get("t") and row["t"] <= cutoff]
        for key, rows in (htf or {}).items()
    }


def run(
    klines_path: str,
    out_path: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    step: int = 48,
    horizon: int = 48,
    warmup: int = 300,
) -> dict:
    kl = hm.load_klines_jsonl(klines_path)
    if len(kl) < warmup + horizon + step:
        return {
            "ok": False,
            "error": "faltan_velas",
            "detail": f"Se necesitan al menos {warmup + horizon + step} velas 5m.",
        }
    kl = sorted(kl, key=lambda x: x["t"])
    htf = de.load_htf_klines(os.path.dirname(klines_path))

    samples = []
    decisions = 0
    skipped = 0
    for i in range(warmup, len(kl) - horizon, step):
        cutoff = kl[i]["t"]
        if start is not None and cutoff < start:
            continue
        if end is not None and cutoff > end:
            break
        out = de.decide(
            kl[: i + 1],
            now=cutoff,
            htf_klines=_slice_htf(htf, cutoff),
        )
        if not out.get("ok"):
            skipped += 1
            continue
        decisions += 1
        future = kl[i + 1 : i + 1 + horizon]
        for z in out.get("levels", []):
            hold = z.get("hold")
            if not hold:
                continue
            samples.append(
                {
                    "event_time": out["event_time"],
                    "level": z["center"],
                    "side": z["role"],
                    "prob": float(hold["prob"]),
                    "label": 1 if ev.level_holds(future, z["center"], z["role"]) else 0,
                    "quality": z.get("quality"),
                }
            )

    if not samples:
        result = {
            "ok": True,
            "samples": 0,
            "decisions": decisions,
            "skipped": skipped,
            "status": "sin_muestras",
            "detail": "No hubo niveles con aguante en el rango solicitado.",
        }
    else:
        overall = ev._stats(samples)
        n = overall["n"]
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
                    "real_ci95": ev.wilson_interval(sum(labels), len(labels)),
                }
            )
        high = ev._stats([s for s in samples if s["prob"] >= 0.80])
        by_side = {
            side: ev._stats([s for s in samples if s["side"] == side])
            for side in ("soporte", "resistencia")
        }
        result = {
            "ok": True,
            "samples": n,
            "decisions": decisions,
            "skipped": skipped,
            "status": "ok" if n >= ev.MIN_SAMPLES_RECOMMENDED else "muestra_chica",
            "brier": overall["brier"],
            "base_rate": overall["base_rate"],
            "mean_prob": overall["mean_prob"],
            "brier_skill": overall["brier_skill"],
            "high_score": high,
            "by_side": {k: v for k, v in by_side.items() if v.get("n")},
            "bins": bins,
            "horizon_bars": horizon,
            "step_bars": step,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "trained_until": hm.MODEL.get("trained_until"),
            "disclaimer": (
                "Backtest OOS del aguante, no win rate ni ganancia. "
                "No usa datos futuros para construir el contexto; solo para etiquetar."
            ),
        }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, default=str)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest OOS del motor de aguante")
    ap.add_argument("--klines", default=paths.default_klines_path())
    ap.add_argument("--out", default="analysis/data/backtest.json")
    ap.add_argument("--start", default=None, help="ISO-8601; por defecto todo")
    ap.add_argument("--end", default=None, help="ISO-8601; por defecto todo")
    ap.add_argument("--step", type=int, default=48, help="velas 5m entre cortes; 48 = 4h")
    ap.add_argument("--horizon", type=int, default=48, help="velas 5m de futuro; 48 = 4h")
    args = ap.parse_args()
    out = run(
        args.klines,
        args.out,
        start=_dt(args.start) if args.start else None,
        end=_dt(args.end) if args.end else None,
        step=args.step,
        horizon=args.horizon,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
