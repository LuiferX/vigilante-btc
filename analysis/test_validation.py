"""Tests del validation bot. Sin red, sin ordenes."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import validation as v


START = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


def _write_klines(path, n=6500):
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(n):
            t = START + timedelta(minutes=5 * i)
            price = 80000.0 + 100.0 * ((i % 24) - 12) / 12.0
            fh.write(
                json.dumps(
                    {
                        "openTime": int(t.timestamp() * 1000),
                        "open": str(price),
                        "high": str(price + 40),
                        "low": str(price - 40),
                        "close": str(price),
                        "volume": "100",
                    }
                )
                + "\n"
            )


def _setup(
    td,
    *,
    events=10,
    spacing=48,
    levels=1,
    eval_samples=None,
    brier=0.12,
    skill=0.15,
    ece=0.03,
    prob=0.80,
    backtest_samples=120,
    backtest_skill=0.10,
    write_klines=True,
):
    kpath = os.path.join(td, "klines_5m.jsonl")
    dpath = os.path.join(td, "decisions.jsonl")
    epath = os.path.join(td, "eval.json")
    bpath = os.path.join(td, "backtest.json")
    now = START + timedelta(minutes=5 * 6500)

    if write_klines:
        _write_klines(kpath)

    with open(dpath, "w", encoding="utf-8") as fh:
        for k in range(events):
            idx = 300 + k * spacing
            event = START + timedelta(minutes=5 * idx)
            fh.write(
                json.dumps(
                    {
                        "event_time": event.isoformat(),
                        "levels": [
                            {
                                "center": 80000.0,
                                "role": "soporte",
                                "hold_prob": prob,
                                "quality": 8.0,
                            }
                            for _ in range(levels)
                        ],
                    }
                )
                + "\n"
            )

    if eval_samples is None:
        eval_samples = events * levels
    _write_json(
        epath,
        {
            "ok": True,
            "samples": eval_samples,
            "status": "ok" if eval_samples >= 30 else "muestra_chica",
            "brier": brier,
            "base_rate": 0.80,
            "mean_prob": prob,
            "brier_skill": skill,
            "calibration_error": ece,
            "bins": [
                {
                    "bin": "0.80-1.01",
                    "n": eval_samples,
                    "pred": prob,
                    "real": 0.80,
                }
            ]
            if eval_samples
            else [],
        },
    )
    _write_json(
        bpath,
        {
            "ok": True,
            "samples": backtest_samples,
            "brier": 0.16,
            "brier_skill": backtest_skill,
            "mean_prob": prob,
            "bins": [{"bin": "0.80-1.01", "n": backtest_samples}],
        },
    )
    return {
        "klines": kpath,
        "decisions": dpath,
        "eval": epath,
        "backtest": bpath,
        "now": now,
    }


class ValidationTest(unittest.TestCase):
    def test_sin_muestras(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=5, eval_samples=0)
            out = v.validate(
                paths["eval"],
                paths["backtest"],
                paths["decisions"],
                paths["klines"],
                now=paths["now"],
            )
            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "sin_muestras")
            self.assertEqual(out["sample_status"], "sin_muestras")
            self.assertIn("Sin muestras", out["headline"])
            self.assertTrue(any("4h de futuro" in w for w in out["warnings"]))

    def test_ok_with_enough_independent_samples(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=120, spacing=48, eval_samples=120)
            out = v.validate(
                paths["eval"],
                paths["backtest"],
                paths["decisions"],
                paths["klines"],
                now=paths["now"],
            )
            self.assertEqual(out["status"], "ok")
            self.assertTrue(out["healthy"])
            self.assertEqual(out["samples"]["eval"], 120)
            self.assertEqual(out["samples"]["effective"], 120)
            self.assertEqual(out["sample_status"], "suficiente")
            self.assertEqual(out["drift"]["status"], "ok")
            self.assertEqual(out["drift"]["psi"], 0.0)

    def test_overlap_reduces_effective_sample(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=120, spacing=12, eval_samples=120)
            out = v.validate(
                paths["eval"],
                paths["backtest"],
                paths["decisions"],
                paths["klines"],
                now=paths["now"],
            )
            self.assertEqual(out["status"], "muestra_media")
            self.assertEqual(out["sample_status"], "muestra_media")
            self.assertLess(out["samples"]["effective"], out["samples"]["eval"])
            self.assertEqual(out["samples"]["independent_events"], 30)
            self.assertTrue(
                any("solapamiento" in w for w in out["warnings"])
            )

    def test_degraded_when_skill_is_negative(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(
                td,
                events=120,
                spacing=48,
                eval_samples=120,
                skill=-0.20,
                ece=0.02,
            )
            out = v.validate(
                paths["eval"],
                paths["backtest"],
                paths["decisions"],
                paths["klines"],
                now=paths["now"],
            )
            self.assertEqual(out["status"], "degradado")
            self.assertFalse(out["healthy"])
            self.assertTrue(any("Brier skill negativo" in w for w in out["warnings"]))

    def test_roto_without_klines(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=10, write_klines=False)
            out = v.validate(
                paths["eval"],
                paths["backtest"],
                paths["decisions"],
                paths["klines"],
                now=paths["now"],
            )
            self.assertEqual(out["status"], "roto")
            self.assertFalse(out["ok"])
            self.assertFalse(out["data"]["klines"]["ok"])

    def test_psi(self):
        equal = [10, 10, 10, 10]
        self.assertEqual(v.psi(equal, equal), 0.0)
        shifted = v.psi([100, 0, 0, 0], [0, 0, 0, 100])
        self.assertIsNotNone(shifted)
        self.assertGreater(shifted, 1.0)
        self.assertIsNone(v.psi([], [1, 2, 3, 4]))

    def test_history_dedup_and_limit(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "history.jsonl")
            v._append_history(path, {"checked_at": "2026-10-21T00:00:00+00:00", "x": 1})
            v._append_history(path, {"checked_at": "2026-10-21T00:00:00+00:00", "x": 2})
            v._append_history(path, {"checked_at": "2026-10-21T00:05:00+00:00", "x": 3})
            rows = v._load_jsonl(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[-1]["x"], 3)

    def test_does_not_contain_order_or_network_calls(self):
        path = os.path.join(os.path.dirname(__file__), "validation.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read().lower()
        self.assertNotIn("place_order", source)
        self.assertNotIn("api.binance", source)
        self.assertNotIn("requests.", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
