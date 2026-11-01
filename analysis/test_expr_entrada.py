#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_expr_entrada.py - reglas duras de expr_entrada.py (H4).

Cubren: cero look-ahead en las 4 variantes de entrada (la entrada es siempre
el open de la vela SIGUIENTE a la que verifico la condicion), coste siempre
aplicado, independencia por cooldown y bootstrap determinista.

Uso: python -m unittest analysis.test_expr_entrada
"""

from __future__ import annotations

import datetime
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import expr_entrada as ea
except ImportError:
    sys.path.insert(0, AQUI)
    import expr_entrada as ea

UTC = datetime.timezone.utc
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


def muestra(t, lado="soporte", nivel=30000.0, prob=0.9, vol="normal"):
    return {"t": t.isoformat(), "nivel": nivel, "lado": lado, "prob_modelo": prob,
            "volatilidad": vol, "mae_pct": 0.1, "mfe_pct": 0.1}


class TestEntradaSinLookAhead(unittest.TestCase):
    """La entrada debe ser SIEMPRE el open de la vela siguiente a la
    comprobacion. Si la condicion se da en la vela i, se entra en i+1."""

    def test_base_entra_en_la_vela_siguiente(self):
        b = kl(200)
        tiempos = [v["t"] for v in b]
        t = T0 + PASO * 50
        e = ea.buscar_entrada(muestra(t), b, tiempos, "base")
        self.assertIsNotNone(e)
        j, px = e
        self.assertEqual(j, 51)
        self.assertEqual(px, b[51]["o"])
        self.assertGreater(b[j]["t"], t)

    def test_retardo_entra_dos_velas_despues_de_la_base(self):
        b = kl(200)
        tiempos = [v["t"] for v in b]
        # control de tiempo puro: +10 minutos respecto a la entrada base (51)
        e = ea.buscar_entrada(muestra(T0 + PASO * 50), b, tiempos, "retardo")
        self.assertEqual(e[0], 53)

    def test_confirm_entra_despues_del_cierre_que_confirma(self):
        b = kl(300)
        # la vela 60 cierra 0,5% por encima del nivel -> confirma el largo
        b[60]["c"] = 30000.0 * 1.005
        tiempos = [v["t"] for v in b]
        e = ea.buscar_entrada(muestra(T0 + PASO * 50), b, tiempos, "confirm")
        self.assertIsNotNone(e)
        j, px = e
        self.assertEqual(j, 61)                    # open de la SIGUIENTE
        self.assertEqual(px, b[61]["o"])

    def test_confirm_no_dispara_con_el_nivel_roto(self):
        b = kl(300, paso=0.0)                      # plano: nunca confirma
        tiempos = [v["t"] for v in b]
        self.assertIsNone(ea.buscar_entrada(muestra(T0 + PASO * 50),
                                            b, tiempos, "confirm"))

    def test_barrido_exige_perforar_y_recuperar(self):
        b = kl(300)
        # vela 55 perfora el soporte (low por debajo del -0,2%) y
        # vela 60 recupera el nivel (cierre por encima)
        b[55]["l"] = 30000.0 * 0.997
        b[60]["c"] = 30000.0 * 1.001
        tiempos = [v["t"] for v in b]
        e = ea.buscar_entrada(muestra(T0 + PASO * 50), b, tiempos, "barrido")
        self.assertIsNotNone(e)
        self.assertEqual(e[0], 61)                 # tras la recuperacion

    def test_barrido_sin_perforar_no_dispara(self):
        b = kl(300)
        b[60]["c"] = 30000.0 * 1.001               # recupera pero nadie perforo
        tiempos = [v["t"] for v in b]
        self.assertIsNone(ea.buscar_entrada(muestra(T0 + PASO * 50),
                                            b, tiempos, "barrido"))

    def test_ventana_de_espera_maxima(self):
        b = kl(200)
        b[199]["c"] = 30000.0 * 1.02               # confirma demasiado tarde
        tiempos = [v["t"] for v in b]
        # la senal esta en la vela 50; W=24 velas -> solo hasta la 75
        self.assertIsNone(ea.buscar_entrada(muestra(T0 + PASO * 50),
                                            b, tiempos, "confirm"))


class TestCostes(unittest.TestCase):
    def test_neto_resta_el_coste(self):
        b = kl(200, paso=0.0)
        tiempos = [v["t"] for v in b]
        r = ea.resolver(muestra(T0), b, tiempos, "base", "h4")
        self.assertAlmostEqual(r["bruto"], 0.0, places=9)
        self.assertAlmostEqual(r["neto"], -r["coste"], places=9)


class TestIndependencia(unittest.TestCase):
    def test_cooldown_deja_pasar_uno(self):
        b = kl(3000)
        tiempos = [v["t"] for v in b]
        ms = [muestra(T0 + PASO * i * 7) for i in range(10)]
        rets, _ = ea.secuencia_independiente(ms, b, tiempos, "base", "h4")
        self.assertEqual(len(rets), 1)

    def test_fuera_de_cooldown_pasan_todas(self):
        b = kl(5000)
        tiempos = [v["t"] for v in b]
        ms = [muestra(T0 + PASO * i * 120) for i in range(3)]
        rets, _ = ea.secuencia_independiente(ms, b, tiempos, "base", "h4")
        self.assertEqual(len(rets), 3)


class TestBootstrap(unittest.TestCase):
    def test_determinista(self):
        v = [(-1) ** i * 0.2 for i in range(200)]
        self.assertEqual(ea.bootstrap_ci(v, semilla=42), ea.bootstrap_ci(v, semilla=42))


class TestDatosReales(unittest.TestCase):
    def test_replay_real_8_celdas(self):
        for f in ("expr_muestras.jsonl", "klines_5m.jsonl"):
            if not os.path.exists(os.path.join(ea.CACHE, f)):
                self.skipTest("cache no disponible")
        ms = ea.cargar_muestras()
        b = ea.cargar_klines()
        tiempos = [v["t"] for v in b]
        for variante in ("base", "confirm", "barrido"):
            rets, _ = ea.secuencia_independiente(ms, b, tiempos, variante, "h4")
            self.assertGreater(len(rets), 300, f"{variante} debe tener >=300 indep.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
