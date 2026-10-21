"""Loop local del motor de decision. No ejecuta ordenes.

Cada intervalo:
1. lee el ultimo klines_5m.jsonl del colector,
2. registra una decision nueva (dedup por event_time),
3. evalua las decisiones que ya tienen 4h de futuro.

Pensado para correr en una terminal aparte del Vigilante.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

import evaluate_decisions as ev
import paths
import run_decision as rd


def once(klines: str, decisions: str, vigilante: str | None, horizon: int) -> None:
    out = rd.run(
        klines,
        out_path=decisions,
        vigilante=vigilante,
        now=datetime.now(timezone.utc),
    )
    if not out.get("ok"):
        print(f"[{datetime.now(timezone.utc).isoformat()}] sin datos: {out.get('error')}")
        return
    print(f"[{datetime.now(timezone.utc).isoformat()}] {out['summary']}")
    if not out.get("logged"):
        print("  (event_time ya registrado)")
    ev_out = ev.evaluate(decisions, klines, horizon=horizon)
    if ev_out.get("samples"):
        print(
            "  evaluacion:",
            json.dumps(
                {
                    "n": ev_out["samples"],
                    "brier": ev_out["brier"],
                    "base": ev_out["base_rate"],
                    "high": ev_out["high_score"],
                },
                ensure_ascii=False,
            ),
        )
    else:
        print("  evaluacion: aun sin 4h de futuro")


def main() -> None:
    ap = argparse.ArgumentParser(description="Loop local del motor de decision")
    ap.add_argument("--klines", default=paths.default_klines_path())
    ap.add_argument("--decisions", default=paths.default_decisions_path())
    ap.add_argument("--vigilante", default=None)
    ap.add_argument("--minutes", type=float, default=60.0)
    ap.add_argument("--horizon", type=int, default=48)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    while True:
        try:
            once(args.klines, args.decisions, args.vigilante, args.horizon)
        except Exception as exc:  # el loop no debe morir por un error de red/datos
            print(f"error: {exc}")
        if args.once:
            return
        time.sleep(max(60.0, args.minutes * 60.0))


if __name__ == "__main__":
    main()
