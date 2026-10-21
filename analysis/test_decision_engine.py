"""Tests del motor de decision. Ejecutar: python test_decision_engine.py"""

import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import decision_engine as de


def make_kl(n=500, price=80000.0):
    out = []
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for i in range(n):
        base = price + 250.0 * math.sin(2 * math.pi * i / 24.0) + 80.0 * math.sin(
            2 * math.pi * i / 160.0
        )
        o = base + 15.0 * math.sin(2 * math.pi * i / 7.0)
        c = base
        out.append(
            {
                "t": t0 + timedelta(minutes=5 * i),
                "o": o,
                "h": max(o, c) + 30.0,
                "l": min(o, c) - 30.0,
                "c": c,
                "v": 100.0,
            }
        )
    return out


def make_htf(n=200, start=70000.0, step=100.0, minutes=60):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        c = start + step * i + 600.0 * math.sin(2 * math.pi * i / 20.0)
        out.append(
            {
                "t": t0 + timedelta(minutes=minutes * i),
                "o": c - step / 2,
                "h": c + step,
                "l": c - step,
                "c": c,
                "v": 1000.0,
            }
        )
    return out


class DecisionEngineTest(unittest.TestCase):
    def test_decide_ok(self):
        out = de.decide(make_kl(), price=80000.0)
        self.assertTrue(out["ok"])
        self.assertEqual(out["price"], 80000.0)
        self.assertTrue(out["levels"])
        self.assertTrue(any(z["hold"] is not None for z in out["levels"]))
        self.assertIn("base_scenario", out["decision"])
        self.assertIn("trigger", out["decision"])
        self.assertIn("invalidation", out["decision"])
        self.assertIn(out["decision"]["confidence"], {"alta", "media", "baja"})
        self.assertIn(out["decision"]["action"], {"esperar_confirmacion", "observar", "sin_escenario"})

    def test_insufficient_data(self):
        out = de.decide(make_kl(20), price=80000.0)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "faltan_velas")

    def test_zone_width_formula(self):
        kl = make_kl()
        price = 80000.0
        out = de.decide(kl, price=price)
        expected = max(de.ZONE_MIN_PCT * price, de.ZONE_ATR_MULT * de.atr_price(kl, 48))
        self.assertAlmostEqual(out["zone_width"], expected)

    def test_extra_level_is_scored(self):
        out = de.decide(
            make_kl(),
            price=80000.0,
            extra_levels=[{"precio": 81000.0, "tipo": "resistencia", "toques": 4}],
        )
        ext = [z for z in out["levels"] if "vigilante" in z["source"]]
        self.assertEqual(len(ext), 1)
        self.assertIsNotNone(ext[0]["hold"])
        self.assertGreaterEqual(ext[0]["hold"]["prob"], 0.0)
        self.assertLessEqual(ext[0]["hold"]["prob"], 1.0)

    def test_vigilante_levels_adapter(self):
        state = {
            "snapshot": {
                "niv": {
                    "sop": [{"precio": 81500, "origen": "S1", "n": 2}],
                    "res": [{"precio": 83000, "origen": "R1", "n": 3}],
                }
            }
        }
        levels = de.levels_from_vigilante_state(state)
        self.assertEqual(len(levels), 2)
        self.assertEqual(levels[0]["tipo"], "soporte")
        self.assertEqual(levels[0]["toques"], 0)
        self.assertEqual(levels[0]["confluencia"], 2)
        self.assertEqual(levels[1]["tipo"], "resistencia")
        self.assertEqual(levels[1]["toques"], 0)
        self.assertEqual(levels[1]["confluencia"], 3)

        out = de.decide(make_kl(), price=80000.0, extra_levels=levels)
        ext = [z for z in out["levels"] if "vigilante" in z["source"]]
        self.assertGreaterEqual(len(ext), 1)

    def test_hold_model_is_used(self):
        fake = {
            "prob": 0.91,
            "tier": "alto",
            "drivers": [{"feature": "x_atr288", "contribution": -0.2}],
        }
        with patch.object(de.hm, "score_level", return_value=fake) as mocked:
            out = de.decide(make_kl(), price=80000.0)
        self.assertTrue(mocked.called)
        scored = [z for z in out["levels"] if z["hold"] is not None]
        self.assertTrue(scored)
        self.assertEqual(scored[0]["hold"]["prob"], 0.91)
        self.assertEqual(scored[0]["hold"]["tier"], "alto")

    def test_no_order_language_in_decision(self):
        out = de.decide(make_kl(), price=80000.0)
        text = " ".join(str(v) for v in out["decision"].values()).lower()
        self.assertNotIn("comprar", text)
        self.assertNotIn("vender", text)
        self.assertIn("no hacer nada", out["decision"]["do_nothing"].lower())

    def test_decide_from_jsonl(self):
        # Solo verifica que el atajo exista y falle limpio con un archivo vacio.
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            path = fh.name
        out = de.decide_from_jsonl(path)
        self.assertFalse(out["ok"])

    def test_htf_bias_and_pivots(self):
        kl = make_kl()
        h = de.htf_bias(kl)
        self.assertIn(h["bias"], {"ALZA", "BAJA", "LATERAL"})
        self.assertIn(h["h1"], {"ALZA", "BAJA", "LATERAL", None})
        self.assertIn(h["h4"], {"ALZA", "BAJA", "LATERAL", None})
        piv = de.htf_pivots(kl)
        self.assertTrue(piv)
        self.assertTrue(all(p["tf"] in {"1h", "4h"} for p in piv))

    def test_round_level(self):
        level, step, score = de.round_level(83117.0, 248.0)
        self.assertEqual(level, 83000.0)
        self.assertEqual(step, 1000)
        self.assertAlmostEqual(score, 0.5)
        self.assertEqual(de.round_level(83117.0, 10.0)[2], 0.0)

    def test_volume_profile(self):
        vp = de.volume_profile(make_kl())
        self.assertIn("poc", vp)
        self.assertLessEqual(vp["val"], vp["poc"])
        self.assertLessEqual(vp["poc"], vp["vah"])

    def test_zone_quality_and_scenarios(self):
        out = de.decide(make_kl(), price=80000.0)
        self.assertTrue(out["levels"])
        self.assertTrue(all(0.0 <= z["quality"] <= 10.0 for z in out["levels"]))
        self.assertGreaterEqual(out["engine_quality"], 0.0)
        self.assertLessEqual(out["engine_quality"], 10.0)
        self.assertGreaterEqual(out["setup_quality"], 0.0)
        self.assertLessEqual(out["setup_quality"], 10.0)
        self.assertIn("composite", out["quality"])
        self.assertGreaterEqual(out["quality"]["composite"], 0.0)
        self.assertLessEqual(out["quality"]["composite"], 10.0)
        self.assertEqual(out["quality"]["target"], 8.5)
        self.assertIn(out["quality"]["grade"], {"A", "B", "C", "D"})
        self.assertGreaterEqual(out["quality"]["gap"], 0.0)
        self.assertEqual(
            [s["name"] for s in out["scenarios"]],
            ["base", "alternativo", "no_hacer_nada"],
        )

    def test_classify_zone(self):
        zone = {
            "zone_low": 99.0,
            "zone_high": 101.0,
            "role": "resistencia",
        }
        kl = [
            {"o": 100, "h": 102, "l": 99, "c": 100, "v": 1, "t": datetime(2026, 10, 1, tzinfo=timezone.utc)}
            for _ in range(3)
        ]
        kl[-2]["c"] = 101.5
        kl[-1]["c"] = 102.0
        r = de.classify_zone(kl, zone)
        self.assertEqual(r["position"], "arriba")
        self.assertTrue(r["break_confirmed"])
        self.assertGreaterEqual(r["break_bars"], 2)

    def test_native_htf_bias(self):
        htf = {
            "1h": make_htf(200, 70000, 100, 60),
            "4h": make_htf(150, 70000, 400, 240),
            "1d": make_htf(120, 70000, 1000, 1440),
        }
        out = de.decide(make_kl(), price=80000.0, htf_klines=htf)
        self.assertEqual(out["state"]["htf"]["source"], "nativo_1h_4h_1d")
        self.assertEqual(out["state"]["htf"]["h4"], "ALZA")
        self.assertEqual(out["state"]["htf"]["d1"], "ALZA")
        self.assertEqual(out["state"]["bias"], "ALZA")
        self.assertGreater(out["state"]["htf_pivots"], 0)

    def test_override_bias(self):
        out = de.decide(make_kl(), price=80000.0, htf_bias_override="BAJA")
        self.assertEqual(out["state"]["bias"], "BAJA")
        self.assertEqual(out["state"]["bias_source"], "override")

    def test_data_age(self):
        kl = make_kl()
        now = kl[-1]["t"] + timedelta(minutes=30)
        out = de.decide(kl, price=80000.0, now=now)
        self.assertAlmostEqual(out["data_age_min"], 30.0, places=1)
        self.assertTrue(any("antiguedad" in r for r in out["decision"]["risks"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
