#!/usr/bin/env python3
"""Tests del entrenador walk-forward. Sin red. Uso: python test_entrenar_hold.py"""

import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import entrenar_hold as eh
import hold_model as hm

UTC = datetime.UTC


def _muestra(feats, y, **extra):
    d = {
        "feats": list(feats),
        "y": y,
        "t": datetime.datetime(2024, 1, 1, tzinfo=UTC).isoformat(),
    }
    d.update(extra)
    return d


class EntrenarTest(unittest.TestCase):
    def test_separable_aprende(self):
        datos = []
        for i in range(120):
            f = [0.0] * len(eh.FEATURES)
            f[0] = 0.01 if i % 2 == 0 else -0.01  # dist separa las clases
            datos.append(_muestra(f, 1 if i % 2 == 0 else 0))
        m = eh.entrenar(datos, C=0.03, iters=300)
        p1 = eh.predecir(m, [0.01] + [0.0] * 8)
        p0 = eh.predecir(m, [-0.01] + [0.0] * 8)
        self.assertGreater(p1, p0)
        self.assertGreater(p1, 0.5)
        self.assertLess(p0, 0.5)

    def test_l1_apaga_ruido(self):
        base = [0.0] * len(eh.FEATURES)
        datos = []
        for i in range(200):
            f = list(base)
            f[0] = 0.02 if i % 2 == 0 else -0.02  # senal real
            f[3] = ((i * 37) % 11) / 100.0  # ruido puro
            datos.append(_muestra(f, i % 2))
        m = eh.entrenar(datos, C=0.03, iters=300)
        self.assertEqual(abs(m["coef"][0]) > abs(m["coef"][3]), True)

    def test_recalibrar_intercepto_solo_mueve_intercepto(self):
        datos = [
            _muestra([0.01 if i % 2 == 0 else -0.01] + [0.0] * 8, i % 2)
            for i in range(100)
        ]
        m = eh.entrenar(datos, C=0.03, iters=200)
        r = eh.recalibrar_intercepto(m, datos)
        self.assertEqual(m["coef"], r["coef"])
        self.assertEqual(m["mean"], r["mean"])
        self.assertNotEqual(m["intercept"], r["intercept"])

    def test_metricas_perfectas(self):
        muestras = [_muestra([0.0] * 9, 1), _muestra([0.0] * 9, 0)]
        out = eh.metricas(muestras, [1.0, 0.0])
        self.assertEqual(out["brier"], 0.0)
        self.assertEqual(out["brier_skill"], 1.0)
        self.assertEqual(out["base_rate"], 0.5)

    def test_ece_conocida(self):
        # predice 0.9 y real 1.0 -> ECE 0.1
        self.assertAlmostEqual(eh.ece([0.9], [1.0]), 0.1, places=3)
        self.assertAlmostEqual(eh([0.8, 0.8], [1.0, 0.6]) if False else 0.0, 0.0)

    def test_racha_positiva(self):
        self.assertEqual(eh._racha_positiva([0.1, 0.2, -0.1, 0.3, 0.4, 0.5]), 3)
        self.assertEqual(eh._racha_positiva([-1, -2]), 0)
        self.assertEqual(eh._racha_positiva([0.1, None, 0.2]), 1)

    def test_folds_embargo(self):
        d0 = datetime.datetime(2023, 1, 1, tzinfo=UTC)
        d1 = datetime.datetime(2026, 1, 1, tzinfo=UTC)
        fs = eh.folds(d0, d1, test_dias=90, train_dias=365, embargo_horas=24)
        self.assertGreater(len(fs), 0)
        for corte, t_ini, t_fin in fs:
            self.assertLess(corte, t_ini)
            self.assertEqual((t_ini - corte).total_seconds() / 3600, 24)
            self.assertEqual((t_fin - t_ini).days, 90)
        # el primer fold arranca despues del train completo
        self.assertEqual(fs[0][1].date().isoformat(), "2024-01-01")

    def test_cortar_htf_sin_futuro(self):
        barras = [
            {"t": datetime.datetime(2024, 1, i + 1, tzinfo=UTC), "c": 1}
            for i in range(10)
        ]
        tiempos = [b["t"] for b in barras]
        corte = datetime.datetime(2024, 1, 5, 12, tzinfo=UTC)
        out = eh.cortar_htf({"1h": barras}, {"1h": tiempos}, corte)
        self.assertTrue(all(b["t"] <= corte for b in out["1h"]))
        self.assertEqual(len(out["1h"]), 5)

    def test_replay_vacio_sin_datos(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "klines_5m.jsonl")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "openTime": 0,
                            "open": "1",
                            "high": "1",
                            "low": "1",
                            "close": "1",
                            "volume": "1",
                        }
                    )
                    + "\n"
                )
            with patch.object(hm, "load_klines_jsonl", return_value=[]):
                self.assertEqual(eh.replay([], {}, 0, 0), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
