#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_expr_toques.py - reglas duras de expr_toques.py (H3).

Cubren: cero look-ahead en la entrada, coste siempre aplicados, independencia
por cooldown y bootstrap determinista.

Uso: python -m unittest analysis.test_expr_toques
"""

from __future__ import annotations

import datetime
import os
import sys
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))

try:
    from analysis import expr_toques as et
except ImportError:
    sys.path.insert(0, AQUI)
    import expr_toques as et

T0 = datetime.datetime(2023, 6, 1, tzinfo=UTC)
PASO = datetime.timedelta(minutes=5)


def kl_sinteticas(n, base=30000.0, paso=0.0):
    kl = []
    for i in range(n):
        t = T0 + PASO * i
        o = base + paso * i
        kl.append({"t": t, "o": o, "h": max(o, o + paso) + 2, "l": min(o, o + paso) - 2,
                   "c": o + paso})
    return kl


def muestra(t, lado="soporte", prob=0.9, vol="normal"):
    return {"t": t.isoformat(), "nivel": 30000.0, "lado": lado, "prob_modelo": prob,
            "volatilidad": vol, "mae_pct": 0.1, "mfe_pct": 0.1}


class TestSinLookAhead(unittest.TestCase):
    def test_entrada_es_open_de_la_vela_siguiente(self):
        kl = kl_sinteticas(200)
        tiempos = [v["t"] for v in kl]
        m = muestra(T0 + PASO * 50)
        r = et.operar(m, kl, tiempos, "E1_h4")
        self.assertIsNotNone(r)
        # la entrada es el open de la vela 51 (la siguiente al timestamp)
        self.assertAlmostEqual(kl[51]["o"], 30000.0, places=9)
        j = next(i for i, v in enumerate(kl) if v["t"] == r["t"])
        self.assertEqual(j, 51)
        self.assertGreater(r["t"], T0 + PASO * 50)

    def test_direccion_por_lado(self):
        kl = kl_sinteticas(200, paso=5.0)      # suba -> el soporte (largo) gana
        tiempos = [v["t"] for v in kl]
        r_largo = et.operar(muestra(T0, lado="soporte"), kl, tiempos, "E1_h4")
        r_corto = et.operar(muestra(T0, lado="resistencia"), kl, tiempos, "E1_h4")
        self.assertGreater(r_largo["bruto"], 0.0)
        self.assertLess(r_corto["bruto"], 0.0)


class TestCostes(unittest.TestCase):
    # la muestras de abajo entran en t = T0 -> vela de entrada = 1 (bisect_right
    # sobre el instante exacto), y las salidas se evaluan desde la vela 2
    # (la vela de entrada ya tiene su open como precio de compra).
    BARRA = 2

    def test_neto_resta_el_coste_del_viaje(self):
        kl = kl_sinteticas(200, paso=0.0)      # plano -> bruto 0
        tiempos = [v["t"] for v in kl]
        r = et.operar(muestra(T0, lado="soporte"), kl, tiempos, "E1_h4")
        self.assertAlmostEqual(r["bruto"], 0.0, places=9)
        self.assertAlmostEqual(r["neto"], -r["coste"], places=9)
        self.assertLess(r["neto"], 0.0)

    def test_gestionada_si_tp_y_sl_en_la_misma_vela_manda_sl(self):
        # vela con rango gigante: toca TP y SL -> se asume SL (conservador)
        kl = kl_sinteticas(200, paso=0.0)
        kl[self.BARRA]["h"] = 30000.0 + 100
        kl[self.BARRA]["l"] = 30000.0 - 100
        tiempos = [v["t"] for v in kl]
        r = et.operar(muestra(T0, lado="soporte"), kl, tiempos, "E2_gest")
        # SL del largo = entrada*(1-0,3%)
        self.assertAlmostEqual(r["bruto"], -0.3, places=6)

    def test_gestionada_tp_del_largo(self):
        kl = kl_sinteticas(200, paso=0.0)
        kl[self.BARRA]["h"] = 30000.0 + 200
        kl[self.BARRA]["l"] = 30000.0 - 0.1
        tiempos = [v["t"] for v in kl]
        r = et.operar(muestra(T0, lado="soporte"), kl, tiempos, "E2_gest")
        self.assertAlmostEqual(r["bruto"], 0.5, places=6)

    def test_gestionada_tp_del_corto(self):
        kl = kl_sinteticas(200, paso=0.0)
        kl[self.BARRA]["h"] = 30000.0 + 0.1
        kl[self.BARRA]["l"] = 30000.0 - 200
        tiempos = [v["t"] for v in kl]
        r = et.operar(muestra(T0, lado="resistencia"), kl, tiempos, "E2_gest")
        self.assertAlmostEqual(r["bruto"], 0.5, places=6)


class TestIndependencia(unittest.TestCase):
    def test_una_posicion_a_la_vez_y_cooldown(self):
        kl = kl_sinteticas(2000)
        tiempos = [v["t"] for v in kl]
        # 10 muestras seguidas cada 5 min: solo la primera debe operar
        ms = [muestra(T0 + PASO * i * 7) for i in range(10)]
        ms.sort(key=lambda m: m["t"])
        rets, detalle = et.secuencia_independiente(ms, kl, tiempos, "E1_h4", "todas")
        self.assertEqual(len(rets), 1, "el cooldown debe dejar pasar solo una")

    def test_cooldown_de_4h_deja_pasar_la_siguiente(self):
        kl = kl_sinteticas(4000)
        tiempos = [v["t"] for v in kl]
        ms = [muestra(T0 + PASO * i * 100) for i in range(3)]
        ms.sort(key=lambda m: m["t"])
        rets, _ = et.secuencia_independiente(ms, kl, tiempos, "E1_h4", "todas")
        self.assertEqual(len(rets), 3)

    def test_filtro_de_conviccion(self):
        kl = kl_sinteticas(4000)
        tiempos = [v["t"] for v in kl]
        ms = [muestra(T0 + PASO * i * 100, prob=0.5) for i in range(3)]
        ms.sort(key=lambda m: m["t"])
        rets, _ = et.secuencia_independiente(ms, kl, tiempos, "E1_h4", "top")
        self.assertEqual(len(rets), 0, "top excluye prob < p_top")


class TestBootstrap(unittest.TestCase):
    def test_determinista(self):
        vals = [(-1) ** i * 0.2 for i in range(200)]
        self.assertEqual(et.bootstrap_ci(vals, semilla=42), et.bootstrap_ci(vals, semilla=42))

    def test_constante_positiva_p_cero(self):
        lo, hi, p = et.bootstrap_ci([0.2] * 100, semilla=42)
        self.assertAlmostEqual(p, 0.0, places=9)


class TestDatosReales(unittest.TestCase):
    def test_replay_real_y_independencia(self):
        p_m = os.path.join(et.CACHE, "expr_muestras.jsonl")
        p_k = os.path.join(et.CACHE, "klines_5m.jsonl")
        if not (os.path.exists(p_m) and os.path.exists(p_k)):
            self.skipTest("cache no disponible")
        ms = et.cargar_muestras()
        kl = et.cargar_klines()
        tiempos = [v["t"] for v in kl]
        rets, detalle = et.secuencia_independiente(ms, kl, tiempos, "E1_h4", "todas")
        self.assertGreater(len(rets), 300, "el pre-registro exige >= 300 indep.")
        self.assertLess(len(rets), len(ms), "el cooldown debe reducir la muestra")
        for r in rets:
            self.assertTrue(-100.0 < r < 100.0, "retorno neto razonable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
