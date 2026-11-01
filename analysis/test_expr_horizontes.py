#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_expr_horizontes.py - reglas duras de expr_horizontes.py (H6).

Cubren: cero look-ahead en la entrada, funding con el signo correcto, costes
aplicados, cooldown que evita holds solapados y bootstrap determinista.

Uso: python -m unittest analysis.test_expr_horizontes
"""

from __future__ import annotations

import datetime
import os
import sys
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import expr_horizontes as eh
except ImportError:
    sys.path.insert(0, AQUI)
    import expr_horizontes as eh

T0 = datetime.datetime(2023, 6, 1, tzinfo=UTC)
PASO = datetime.timedelta(minutes=5)


def kl(n, base=30000.0, paso=0.0):
    out = []
    for i in range(n):
        t = T0 + PASO * i
        o = base + paso * i
        c = o + paso
        out.append({"t": t, "o": o, "h": max(o, c) + 1, "l": min(o, c) - 1, "c": c})
    return out


def muestra(t, lado="soporte", prob=0.9, vol="normal"):
    return {"t": t.isoformat(), "nivel": 30000.0, "lado": lado,
            "prob_modelo": prob, "volatilidad": vol, "mae_pct": 0.1,
            "mfe_pct": 0.1}


class TestSinLookAhead(unittest.TestCase):
    def test_entrada_en_la_vela_siguiente(self):
        b = kl(1200)
        tiempos = [v["t"] for v in b]
        r = eh.resolver(muestra(T0 + PASO * 50), b, tiempos, 144)
        self.assertIsNotNone(r)
        self.assertEqual(r["t"], b[51]["t"])       # open de la vela 51

    def test_salida_al_cierre_del_horizonte(self):
        b = kl(1200, paso=0.0)
        tiempos = [v["t"] for v in b]
        r = eh.resolver(muestra(T0), b, tiempos, 144)
        self.assertAlmostEqual(r["bruto"], 0.0, places=9)

    def test_sin_datos_suficientes_devuelve_none(self):
        b = kl(100)                                 # 100 velas < 144
        tiempos = [v["t"] for v in b]
        self.assertIsNone(eh.resolver(muestra(T0), b, tiempos, 144))


class TestFunding(unittest.TestCase):
    """La convencion de signo ya corregida en H1: largo cobra si rate<0."""

    def test_largo_cobra_funding_negativo(self):
        b = kl(1200, paso=0.0)
        tiempos = [v["t"] for v in b]
        eh._FTS[:] = [b[51]["t"] + datetime.timedelta(hours=2)]
        eh._FRATES[:] = [-0.0002]                  # -0,02% en 8h
        r = eh.resolver(muestra(T0, lado="soporte"), b, tiempos, 144)
        self.assertGreater(r["funding_pct"], 0.0)
        self.assertAlmostEqual(r["funding_pct"], 0.02, places=9)

    def test_largo_paga_funding_positivo(self):
        b = kl(1200, paso=0.0)
        tiempos = [v["t"] for v in b]
        eh._FTS[:] = [b[51]["t"] + datetime.timedelta(hours=2)]
        eh._FRATES[:] = [0.0002]
        r = eh.resolver(muestra(T0, lado="soporte"), b, tiempos, 144)
        self.assertLess(r["funding_pct"], 0.0)
        self.assertAlmostEqual(r["funding_pct"], -0.02, places=9)

    def test_corto_cobra_funding_positivo(self):
        b = kl(1200, paso=0.0)
        tiempos = [v["t"] for v in b]
        eh._FTS[:] = [b[51]["t"] + datetime.timedelta(hours=2)]
        eh._FRATES[:] = [0.0002]
        r = eh.resolver(muestra(T0, lado="resistencia"), b, tiempos, 144)
        self.assertAlmostEqual(r["funding_pct"], 0.02, places=9)

    def test_funding_fuera_del_hold_no_cuenta(self):
        b = kl(1200, paso=0.0)
        tiempos = [v["t"] for v in b]
        eh._FTS[:] = [b[51]["t"] + datetime.timedelta(hours=100)]   # >12h
        eh._FRATES[:] = [0.0002]
        r = eh.resolver(muestra(T0), b, tiempos, 144)
        self.assertAlmostEqual(r["funding_pct"], 0.0, places=9)


class TestCostes(unittest.TestCase):
    def test_neto_incluye_coste_y_funding(self):
        b = kl(1200, paso=0.0)
        tiempos = [v["t"] for v in b]
        eh._FTS[:] = []
        eh._FRATES[:] = []
        r = eh.resolver(muestra(T0), b, tiempos, 144)
        self.assertAlmostEqual(r["bruto"], 0.0, places=9)
        self.assertAlmostEqual(r["neto"], -r["coste"], places=9)


class TestIndependencia(unittest.TestCase):
    def test_holds_no_se_solapan(self):
        b = kl(4000)
        tiempos = [v["t"] for v in b]
        # senales cada 30 min: con hold 12h + cooldown 4h (16h de bloqueo)
        # de 40 senales solo entran las que caen fuera de ese bloqueo
        ms = [muestra(T0 + PASO * i * 6) for i in range(40)]
        ms.sort(key=lambda m: m["t"])
        rets, detalle = eh.secuencia_independiente(ms, b, tiempos, 144, "todas")
        self.assertLess(len(rets), 40, "el cooldown debe descartar casi todas")
        for a, c in zip(detalle, detalle[1:]):
            self.assertGreaterEqual((c["t"] - a["t"]).total_seconds(), 16 * 3600)

    def test_cooldown_deja_pasar_secuenciales(self):
        b = kl(6000)
        tiempos = [v["t"] for v in b]
        ms = [muestra(T0 + PASO * i * 400) for i in range(4)]
        ms.sort(key=lambda m: m["t"])
        rets, _ = eh.secuencia_independiente(ms, b, tiempos, 144, "todas")
        self.assertEqual(len(rets), 4)

    def test_filtro_top(self):
        b = kl(6000)
        tiempos = [v["t"] for v in b]
        ms = [muestra(T0 + PASO * i * 400, prob=0.5) for i in range(3)]
        ms.sort(key=lambda m: m["t"])
        rets, _ = eh.secuencia_independiente(ms, b, tiempos, 144, "top")
        self.assertEqual(len(rets), 0)


class TestBootstrap(unittest.TestCase):
    def test_determinista(self):
        v = [(-1) ** i * 0.2 for i in range(200)]
        self.assertEqual(eh.bootstrap_ci(v, semilla=42),
                         eh.bootstrap_ci(v, semilla=42))


class TestDatosReales(unittest.TestCase):
    def test_todos_los_horizontes_medibles(self):
        for f in ("expr_muestras.jsonl", "klines_5m.jsonl", "funding.jsonl"):
            if not os.path.exists(os.path.join(eh.CACHE, f)):
                self.skipTest("cache no disponible")
        ms = eh.cargar_muestras()
        b = eh.cargar_klines()
        tiempos = [v["t"] for v in b]
        eh.cargar_funding()
        for h, barras in eh.HORIZONTES.items():
            rets, _ = eh.secuencia_independiente(ms, b, tiempos, barras, "top")
            self.assertGreater(len(rets), 100, f"{h} debe tener muestra")
            for r in rets:
                self.assertTrue(-100.0 < r < 100.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
