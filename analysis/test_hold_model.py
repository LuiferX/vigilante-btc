"""Tests del modelo de aguante v2. Ejecutar: python test_hold_model.py"""

import math
import tempfile
import unittest
from datetime import datetime, timezone

import hold_model as hm


def make_kl(n=320):
    """Velas sinteticas suaves, con ruido deterministico."""
    out = []
    price = 80000.0
    for i in range(n):
        wave = math.sin(i / 11.0) * 35.0 + math.sin(i / 37.0) * 90.0
        o = price
        c = 80000.0 + wave
        h = max(o, c) + 18.0
        l = min(o, c) - 18.0
        out.append(
            {
                "t": datetime(2026, 10, 1, tzinfo=timezone.utc),
                "o": o,
                "h": h,
                "l": l,
                "c": c,
                "v": 100.0 + (i % 7),
            }
        )
        price = c
    return out


class HoldModelTest(unittest.TestCase):
    def test_features_shape(self):
        f = hm.features(make_kl(), 80000.0, 80050.0, datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc))
        self.assertIsNotNone(f)
        self.assertEqual(set(f), set(hm.MODEL["features"]))
        self.assertGreater(f["atr"], 0)
        self.assertGreater(f["x_atr48"], 0)
        self.assertGreater(f["x_atr144"], 0)
        self.assertGreater(f["x_atr288"], 0)

    def test_short_history(self):
        now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.assertIsNone(hm.features(make_kl(100), 80000.0, 80000.0, now))
        self.assertIsNone(hm.features(make_kl(320), 0.0, 80000.0, now))
        self.assertIsNone(hm.features(make_kl(320), 80000.0, 0.0, now))

    def test_score_range_and_tier(self):
        now = datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc)
        f = hm.features(make_kl(), 80000.0, 80050.0, now)
        p = hm.score(f)
        self.assertIsNotNone(p)
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, 1.0)
        self.assertIn(hm.tier(p), {"alto", "medio", "fragil"})
        self.assertEqual(hm.tier(0.80), "alto")
        self.assertEqual(hm.tier(0.60), "medio")
        self.assertEqual(hm.tier(0.59), "fragil")

    def test_contributions_match_logit(self):
        now = datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc)
        f = hm.features(make_kl(), 80000.0, 80050.0, now)
        p = hm.score(f)
        z = hm.MODEL["intercept"] + sum(x["contribution"] for x in hm.contributions(f))
        self.assertAlmostEqual(p, 1.0 / (1.0 + math.exp(-z)), places=12)
        self.assertEqual(len(hm.contributions(f)), len(hm.MODEL["features"]))
        self.assertEqual(len(hm.explain(f)["drivers"]), 4)

    def test_load_jsonl(self):
        raw = (
            '{"openTime": 1792379400000, "open": "82596.70", "high": "82633.80", '
            '"low": "82594.10", "close": "82594.10", "volume": "221.040"}\n'
        )
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
            fh.write(raw)
            path = fh.name
        kl = hm.load_klines_jsonl(path)
        self.assertEqual(len(kl), 1)
        self.assertEqual(kl[0]["c"], 82594.10)
        self.assertEqual(kl[0]["t"].tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
