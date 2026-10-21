"""Ejecuta el motor de decision y guarda un registro para medir despues.

No ejecuta ordenes. No usa claves. Solo lee klines/estado y escribe JSONL.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Optional

import decision_engine as de
import hold_model as hm
import paths


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _already_logged(path: str, event_time: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("event_time") == event_time:
                    return True
    except OSError:
        return False
    return False


def compact_record(out: dict) -> dict:
    """Reduce la salida a lo necesario para evaluar sin guardar ruido."""
    levels = []
    for z in out.get("levels", []):
        hold = z.get("hold")
        levels.append(
            {
                "center": z["center"],
                "zone_low": z["zone_low"],
                "zone_high": z["zone_high"],
                "role": z["role"],
                "touches_6h": z.get("touches_6h", 0),
                "htf_confluence": z.get("htf_confluence", 0),
                "quality": z.get("quality"),
                "round_level": z.get("round_level"),
                "round_score": z.get("round_score"),
                "vol_share": z.get("vol_share"),
                "position": z.get("position"),
                "recent_sweep": z.get("recent_sweep"),
                "break_confirmed": z.get("break_confirmed"),
                "hold_prob": hold["prob"] if hold else None,
                "hold_tier": hold["tier"] if hold else None,
            }
        )
    return {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "event_time": out["event_time"],
        "data_age_min": out.get("data_age_min"),
        "price": out["price"],
        "summary": out["summary"],
        "engine_quality": out["engine_quality"],
        "setup_quality": out["setup_quality"],
        "quality": out.get("quality"),
        "state": {
            "bias": out["state"]["bias"],
            "bias_source": out["state"]["bias_source"],
            "volatility": out["state"]["volatility"],
            "htf": out["state"].get("htf"),
            "poc": out["state"].get("poc"),
        },
        "decision": {
            "action": out["decision"]["action"],
            "confidence": out["decision"]["confidence"],
            "trigger": out["decision"]["trigger"],
            "invalidation": out["decision"]["invalidation"],
            "risks": out["decision"]["risks"],
        },
        "levels": levels,
    }


def run(
    klines_path: str,
    out_path: str = "data/decisions.jsonl",
    vigilante: Optional[str] = None,
    price: Optional[float] = None,
    now: Optional[datetime] = None,
    force: bool = False,
) -> dict:
    kl = hm.load_klines_jsonl(klines_path)
    if vigilante and vigilante.startswith(("http://", "https://")):
        extra = de.fetch_vigilante_levels(vigilante)
    elif vigilante:
        extra = de.load_vigilante_levels(vigilante)
    else:
        extra = None

    htf = de.load_htf_klines(os.path.dirname(klines_path))
    out = de.decide(kl, price=price, now=now, extra_levels=extra, htf_klines=htf)
    if not out.get("ok"):
        return out

    base_dir = os.path.dirname(out_path) or "."
    os.makedirs(base_dir, exist_ok=True)
    rec = compact_record(out)
    logged = force or not _already_logged(out_path, out["event_time"])
    if logged:
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    else:
        out["detail"] = "event_time ya registrado"

    latest_path = os.path.join(base_dir, "latest_decision.json")
    with open(latest_path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2, default=str)

    out["logged"] = logged
    out["log_path"] = out_path
    out["latest_path"] = latest_path
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Registro del motor de decision (solo contexto)")
    ap.add_argument(
        "--klines",
        default=paths.default_klines_path(),
        help="ruta al klines_5m.jsonl",
    )
    ap.add_argument(
        "--out",
        default=paths.default_decisions_path(),
        help="JSONL de decisiones",
    )
    ap.add_argument(
        "--vigilante",
        default=None,
        help="ruta a estado.json o URL raw del Vigilante",
    )
    ap.add_argument("--price", type=float, default=None)
    ap.add_argument("--now", default=None, help="ISO-8601; por defecto la ultima vela")
    ap.add_argument("--force", action="store_true", help="registrar aunque exista el event_time")
    ap.add_argument("--json", action="store_true", help="imprimir la salida completa")
    args = ap.parse_args()

    out = run(
        args.klines,
        out_path=args.out,
        vigilante=args.vigilante,
        price=args.price,
        now=_parse_dt(args.now) or datetime.now(timezone.utc),
        force=args.force,
    )
    if not out.get("ok"):
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:
        print(out["summary"])
        print(out["decision"]["base_scenario"])
        print(out["decision"]["trigger"])
        print(out["decision"]["invalidation"])
        print(f"registrado: {out.get('logged')} -> {out.get('log_path', args.out)}")


if __name__ == "__main__":
    main()
