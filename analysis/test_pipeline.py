"""Tests del runner y del evaluador. Ejecutar: python test_pipeline.py"""

import json
import math
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import evaluate_decisions as ev
import run_decision as rd


def _klines(n=500, price=80000.0):
    out = []
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for i in range(n):
        base = price + 250.0 * math.sin(2 * math.pi * i / 24.0)
        out.append(
            {
                "openTime": int((t0 + timedelta(minutes=5 * i)).timestamp() * 1000),
                "open": str(base),
                "high": str(base + 40),
                "low": str(base - 40),
                "close": str(base),
                "volume": "100",
            }
        )
    return out


class PipelineTest(unittest.TestCase):
    def test_level_holds(self):
        future = [
            {"c": 100.0},
            {"c": 100.2},
            {"c": 99.8},
        ]
        self.assertTrue(ev.level_holds(future, 100.0, "soporte"))
        self.assertTrue(ev.level_holds(future, 100.0, "resistencia"))
        self.assertFalse(ev.level_holds([{"c": 99.0}], 100.0, "soporte"))
        self.assertFalse(ev.level_holds([{"c": 101.0}], 100.0, "resistencia"))

    def test_compact_record(self):
        import decision_engine as de

        out = de.decide(
            [
                {
                    "t": datetime(2026, 10, 1, tzinfo=timezone.utc)
                    + timedelta(minutes=5 * i),
                    "o": 80000.0,
                    "h": 80200.0,
                    "l": 79800.0,
                    "c": 80000.0 + 100 * math.sin(i / 10),
                    "v": 10.0,
                }
                for i in range(500)
            ],
            price=80000.0,
        )
        rec = rd.compact_record(out)
        self.assertIn("event_time", rec)
        self.assertIn("levels", rec)
        self.assertIn("decision", rec)
        self.assertIn("scenarios", rec)
        self.assertIn("engine_quality", rec)

    def test_run_dedup(self):
        with tempfile.TemporaryDirectory() as td:
            kpath = os.path.join(td, "klines.jsonl")
            dpath = os.path.join(td, "decisions.jsonl")
            with open(kpath, "w", encoding="utf-8") as fh:
                for row in _klines():
                    fh.write(json.dumps(row) + "\n")
            a = rd.run(kpath, out_path=dpath)
            self.assertTrue(a["ok"])
            self.assertTrue(a["logged"])
            b = rd.run(kpath, out_path=dpath)
            self.assertTrue(b["ok"])
            self.assertFalse(b["logged"])
            with open(dpath, encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertTrue(os.path.exists(a["health_path"]))

    def test_wilson_interval(self):
        lo, hi = ev.wilson_interval(8, 10)
        self.assertLess(lo, 0.8)
        self.assertGreater(hi, 0.8)
        self.assertLessEqual(lo, hi)

    def test_evaluate_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            kpath = os.path.join(td, "klines.jsonl")
            dpath = os.path.join(td, "decisions.jsonl")
            rows = _klines(500)
            with open(kpath, "w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row) + "\n")
            event = datetime.fromtimestamp(
                rows[300]["openTime"] / 1000.0, tz=timezone.utc
            ).isoformat()
            rec = {
                "event_time": event,
                "levels": [
                    {"center": 80000.0, "role": "soporte", "hold_prob": 0.8, "quality": 8.0},
                    {"center": 80500.0, "role": "resistencia", "hold_prob": 0.7, "quality": 7.0},
                ],
            }
            with open(dpath, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            out = ev.evaluate(dpath, kpath, horizon=48)
            self.assertTrue(out["ok"])
            self.assertEqual(out["samples"], 2)
            self.assertIn("brier_skill", out)
            self.assertIn("calibration_error", out)
            self.assertEqual(out["status"], "muestra_chica")
            self.assertIn("real_ci95", out["bins"][0])

    def test_backtest_no_future_htf(self):
        import backtest

        t1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
        t2 = t1 + timedelta(hours=1)
        htf = {"1h": [{"t": t1}, {"t": t2}]}
        sliced = backtest._slice_htf(htf, t1)
        self.assertEqual(len(sliced["1h"]), 1)

    def test_check_health(self):
        import check_health

        with tempfile.TemporaryDirectory() as td:
            latest = os.path.join(td, "latest.json")
            collector = os.path.join(td, "health.json")
            evaluation = os.path.join(td, "eval.json")
            now = datetime.now(timezone.utc).isoformat()
            with open(latest, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "bar_close_time": now,
                        "data_age_min": 1.0,
                        "data_status": {"fresh": True},
                        "decision": {"action": "observar"},
                        "quality": {"composite": 8.6},
                    },
                    fh,
                )
            with open(collector, "w", encoding="utf-8") as fh:
                json.dump({"ok": True, "kline_ok": True, "jobs": {}}, fh)
            with open(evaluation, "w", encoding="utf-8") as fh:
                json.dump({"samples": 0, "status": "sin_muestras"}, fh)
            result = check_health.check(latest, collector, evaluation)
            self.assertTrue(result["ok"])
            self.assertTrue(result["checks"]["latest_decision"]["ok"])
            self.assertTrue(result["checks"]["collector"]["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
