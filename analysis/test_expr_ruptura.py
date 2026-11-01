#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_expr_ruptura.py - reglas duras de expr_ruptura.py (H5).

Cubren: deteccion de ruptura en tiempo real (entrada al open de la vela
siguiente al cierre que confirma), direccion invertida vs control, salida
"fallo", costes, independencia por cooldown y bootstrap determinista.

Uso: python -m unittest analysis.test_expr_ruptura
"""

from __future__ import annotations

import datetime
import os
import sys
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import expr_ruptura as er
except ImportError:
    sys.path.insert(0, AQUI)
    import expr_ruptura as er

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


def muestra(t, lado="resistencia", nivel=30000.0, vol="normal"):
    return {"t": t.isoformat(), "nivel": nivel, "lado": lado, "prob_modelo": 0.9,
            "volatilidad": vol, "mae_pct": 0.1, "mfe_pct": 0.1}


class TestDeteccionRuptura(unittest.TestCase):
    def test_ruptura_es_el_primer_cierre_mas_alla(self):
        b = kl(200)
        b[20]["c"] = 30000.0 * 1.002          # primer cierre por encima
        tiempos = [v["t"] for v in b]
        ic = er.detectar_ruptura(muestra(T0, lado="resistencia"), b, tiempos)
        self.assertEqual(ic, 20)
        # y la entrada es el open de la vela SIGUIENTE (71)
        r = er.resolver(muestra(T0, lado="resistencia"), b, tiempos, "ruptura", "h4")
        self.assertGreater(r["t"], b[20]["t"])
        self.assertAlmostEqual(r["t"], b[21]["t"])

    def test_sin_ruptura_no_hay_trade(self):
        b = kl(200, paso=0.0)                  # plano: nunca rompe
        tiempos = [v["t"] for v in b]
        self.assertIsNone(er.detectar_ruptura(muestra(T0), b, tiempos))
        self.assertIsNone(er.resolver(muestra(T0), b, tiempos, "ruptura", "h4"))

    def test_soporte_roto_hacia_abajo(self):
        b = kl(200)
        b[20]["c"] = 30000.0 * 0.998
        tiempos = [v["t"] for v in b]
        ic = er.detectar_ruptura(muestra(T0, lado="soporte"), b, tiempos)
        self.assertEqual(ic, 20)

    def test_ventana_de_48_velas(self):
        b = kl(300)
        b[100]["c"] = 30000.0 * 1.002          # rompe demasiado tarde
        tiempos = [v["t"] for v in b]
        self.assertIsNone(er.detectar_ruptura(muestra(T0), b, tiempos))


class TestDireccion(unittest.TestCase):
    def test_ruptura_invierte_la_direccion_del_modelo(self):
        b = kl(300, paso=0.0)
        b[20]["c"] = 30000.0 * 1.002           # resistencia rota ->continuacion
        for i in range(21, 300):
            b[i]["c"] = 30000.0 * 1.004        # y sube
        tiempos = [v["t"] for v in b]
        r_rot = er.resolver(muestra(T0, lado="resistencia"), b, tiempos, "ruptura", "h4")
        r_ctl = er.resolver(muestra(T0, lado="resistencia"), b, tiempos, "control", "h4")
        self.assertGreater(r_rot["bruto"], 0.0, "ruptura en resistencia = largo")
        self.assertLess(r_ctl["bruto"], 0.0, "control = la direccion del modelo")

    def test_ruptura_de_soporte_es_corta(self):
        b = kl(300, paso=0.0)
        b[20]["c"] = 30000.0 * 0.998
        for i in range(21, 300):
            b[i]["c"] = 30000.0 * 0.996
        tiempos = [v["t"] for v in b]
        r = er.resolver(muestra(T0, lado="soporte"), b, tiempos, "ruptura", "h4")
        self.assertGreater(r["bruto"], 0.0, "corto en caida gana")

    def test_los_dos_lados_son_espejo(self):
        b = kl(300, paso=0.0)
        b[20]["c"] = 30000.0 * 1.002
        tiempos = [v["t"] for v in b]
        r1 = er.resolver(muestra(T0, lado="resistencia"), b, tiempos, "ruptura", "h4")
        r2 = er.resolver(muestra(T0, lado="resistencia"), b, tiempos, "control", "h4")
        self.assertAlmostEqual(r1["bruto"], -r2["bruto"], places=9)


class TestSalidaFallo(unittest.TestCase):
    def test_sale_al_primer_cierre_dentro_del_nivel(self):
        b = kl(300, paso=0.0)
        b[20]["c"] = 30000.0 * 1.002           # rompe
        b[40]["c"] = 30000.0 * 0.999           # vuelve dentro -> falla
        tiempos = [v["t"] for v in b]
        r = er.resolver(muestra(T0, lado="resistencia"), b, tiempos, "ruptura", "fallo")
        esperado = (30000.0 * 0.999 - b[21]["o"]) / b[21]["o"] * 100.0
        self.assertAlmostEqual(r["bruto"], esperado, places=9)

    def test_si_no_falla_cierra_a_48(self):
        b = kl(300, paso=0.0)
        b[20]["c"] = 30000.0 * 1.002
        tiempos = [v["t"] for v in b]
        r = er.resolver(muestra(T0, lado="resistencia"), b, tiempos, "ruptura", "fallo")
        self.assertAlmostEqual(r["bruto"], 0.0, places=9)   # plano -> 0


class TestCostes(unittest.TestCase):
    def test_neto_resta_el_coste(self):
        b = kl(300, paso=0.0)
        b[20]["c"] = 30000.0 * 1.002
        tiempos = [v["t"] for v in b]
        r = er.resolver(muestra(T0, lado="resistencia"), b, tiempos, "ruptura", "h4")
        self.assertAlmostEqual(r["neto"], r["bruto"] - r["coste"], places=9)


class TestIndependencia(unittest.TestCase):
    def test_cooldown_de_2h(self):
        b = kl(4000)
        for i in range(60, 4000, 60):          # rupturas each 5h
            b[i]["c"] = 30000.0 * 1.002
        tiempos = [v["t"] for v in b]
        ms = [muestra(T0 + PASO * (i - 10)) for i in range(60, 4000, 60)]
        rets, _ = er.secuencia_independiente(ms, b, tiempos, "todas", "ruptura", "h4")
        self.assertGreater(len(rets), 10)
        for i in range(1, len(rets)):
            pass                                  # la separacion se chequea abajo

    def test_una_posicion_a_la_vez(self):
        b = kl(4000)
        for i in range(60, 4000, 25):          # rupturas cada ~2h -> solapan
            b[i]["c"] = 30000.0 * 1.002
        tiempos = [v["t"] for v in b]
        ms = [muestra(T0 + PASO * (i - 10)) for i in range(60, 4000, 25)]
        rets, detalle = er.secuencia_independiente(ms, b, tiempos, "todas", "ruptura", "h4")
        for a, c in zip(detalle, detalle[1:]):
            self.assertGreaterEqual((c["t"] - a["t"]).total_seconds(), 2 * 3600)


class TestBootstrap(unittest.TestCase):
    def test_determinista(self):
        v = [(-1) ** i * 0.2 for i in range(200)]
        self.assertEqual(er.bootstrap_ci(v, semilla=42), er.bootstrap_ci(v, semilla=42))


class TestDatosReales(unittest.TestCase):
    def test_universo_y_potencia(self):
        for f in ("expr_muestras.jsonl", "klines_5m.jsonl"):
            if not os.path.exists(os.path.join(er.CACHE, f)):
                self.skipTest("cache no disponible")
        ms = er.cargar_muestras()
        b = er.cargar_klines()
        tiempos = [v["t"] for v in b]
        # el universo debe ser el de rupturas (16% de las muestras)
        con_rot = sum(1 for m in ms if m.get("barras_ruptura") is not None)
        rets, _ = er.secuencia_independiente(ms, b, tiempos, "todas", "ruptura", "h4")
        self.assertGreater(con_rot, 1000)
        self.assertGreater(len(rets), 300, "potencia para el Bonferroni")
        self.assertLess(len(rets), con_rot * 2, "cooldown debe reducir, no inflar")


if __name__ == "__main__":
    unittest.main(verbosity=2)


