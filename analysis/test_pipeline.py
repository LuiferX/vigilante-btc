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


if __name__ == "__main__":
    unittest.main(verbosity=2)
