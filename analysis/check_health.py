"""Chequeo de salud del pipeline. No ejecuta ordenes.

Verifica que exista una decision reciente, que los datos no esten vencidos y
que el colector haya podido traer velas. Sale con codigo 1 si algo critico falla.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _age_min(iso_value: Optional[str]) -> Optional[float]:
    if not iso_value:
        return None
    try:
        dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 60.0)


def check(
    latest_path: str,
    collector_health_path: str,
    eval_path: str,
    max_age_min: float = 180.0,
) -> dict:
    latest = _read_json(latest_path)
    collector = _read_json(collector_health_path)
    evaluation = _read_json(eval_path)
    checks = {}

    if latest is None:
        checks["latest_decision"] = {"ok": False, "error": "no_existe_o_invalido"}
    else:
        age = _age_min(latest.get("bar_close_time") or latest.get("event_time"))
        data_age = latest.get("data_age_min")
        fresh = bool(latest.get("data_status", {}).get("fresh"))
        checks["latest_decision"] = {
            "ok": age is not None and age <= max_age_min and fresh,
            "age_min": round(age, 1) if age is not None else None,
            "data_age_min": data_age,
            "fresh": fresh,
            "action": latest.get("decision", {}).get("action"),
            "quality": latest.get("quality", {}).get("composite"),
        }

    if collector is None:
        checks["collector"] = {"ok": False, "error": "no_existe_o_invalido"}
    else:
        checks["collector"] = {
            "ok": bool(collector.get("ok")),
            "kline_ok": bool(collector.get("kline_ok")),
            "run_at": collector.get("run_at"),
            "failed_jobs": [
                name for name, row in (collector.get("jobs") or {}).items()
                if not row.get("ok")
            ],
        }

    if evaluation is None:
        checks["evaluation"] = {"ok": False, "error": "no_existe_o_invalido"}
    else:
        checks["evaluation"] = {
            "ok": True,
            "samples": evaluation.get("samples"),
            "status": evaluation.get("status"),
            "brier": evaluation.get("brier"),
            "brier_skill": evaluation.get("brier_skill"),
        }

    critical = ["latest_decision", "collector"]
    ok = all(checks[name]["ok"] for name in critical)
    return {
        "ok": ok,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "max_age_min": max_age_min,
        "checks": checks,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Chequeo de salud del pipeline")
    ap.add_argument("--latest", default="analysis/data/latest_decision.json")
    ap.add_argument("--collector-health", default="collector/data/health.json")
    ap.add_argument("--eval", default="analysis/data/eval.json")
    ap.add_argument("--max-age", type=float, default=180.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    result = check(
        args.latest,
        args.collector_health,
        args.eval,
        max_age_min=args.max_age,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
