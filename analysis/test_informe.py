#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_informe.py - el informe no puede prometer lo que no mide.

Cubren: que el informe NO contiene lenguaje de operacion (objetivos, stops,
planes, entradas), que degrada sin datos, y que las cifras que publica coinciden
con las del motor de percentiles.

Uso: python -m unittest analysis.test_informe
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import informe as inf
except ImportError:
    sys.path.insert(0, AQUI)
    import informe as inf

# lenguaje de OPERACION prohibido en el informe. "entrada" y "objetivo" a secas
# NO estan: son terminos analiticos legitimos ("H4 entrada redisenada", "obs"
# del experimento). Lo prohibido es lo que propone una accion con dinero.
PROHIBIDO = ("objetivo de precio", "objetivo:", "plan 2r", "tp ", "sl ", "r:r",
             "apalancamiento recomendado", "riesgo recomendado", "kelly",
             "tamaño de posición", "comprar", "vender ahora", "entrar en",
             "stop loss", "take profit", "precio de entrada")


class TestInformeNoOpera(unittest.TestCase):
    def _sin_disclaimer(self, rep) -> str:
        """Informe sin la linea del disclaimer (que menciona lo que NO lleva)."""
        lineas = [linea for linea in inf.redactar(rep).split("\n")
                  if not linea.strip().startswith(">")]
        return "\n".join(lineas).lower()

    def test_no_hay_lenguaje_de_operacion(self):
        rep = {
            "generado": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "bloques": {"posicionamiento": [], "sistema": {"archivo": {}}},
        }
        md = self._sin_disclaimer(rep)
        for palabra in PROHIBIDO:
            self.assertNotIn(palabra, md, f"el informe contiene '{palabra}'")

    def test_declara_que_no_opera(self):
        rep = {"generado": "2026-11-01T00:00:00+00:00",
               "bloques": {"posicionamiento": [], "sistema": {"archivo": {}}}}
        md = inf.redactar(rep).lower()
        self.assertIn("no opera", md)

    def test_incluye_el_marcador_de_edge(self):
        rep = {"generado": "2026-11-01T00:00:00+00:00",
               "bloques": {"posicionamiento": [], "sistema": {"archivo": {}}}}
        md = inf.redactar(rep)
        self.assertIn("no hay edge direccional demostrado", md)

    def test_el_disclaimer_existe(self):
        rep = {"generado": "2026-11-01T00:00:00+00:00",
               "bloques": {"posicionamiento": [], "sistema": {"archivo": {}}}}
        self.assertIn("no contiene objetivos", inf.redactar(rep).lower())


class TestInformeDegrada(unittest.TestCase):
    def test_sin_archivo_no_rompe(self):
        orig = inf.PCT_HOY
        try:
            with tempfile.TemporaryDirectory() as d:
                # sin percentiles_hoy: el bloque de posicionamiento queda vacio
                rep = {"generado": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(),
                    "bloques": {"posicionamiento": [], "sistema": {}}}
                md = inf.redactar(rep)
                self.assertIn("Informe de inteligencia", md)
        finally:
            inf.PCT_HOY = orig

    def test_bloque_sistema_sin_archivo(self):
        orig = inf.DATA
        try:
            with tempfile.TemporaryDirectory() as d:
                inf.DATA = d
                inf.PCT_HOY = os.path.join(d, "percentiles_hoy.json")
                s = inf.bloque_sistema()
                self.assertIsInstance(s, dict)
        finally:
            inf.DATA = orig
            inf.PCT_HOY = os.path.join(AQUI, "data", "percentiles_hoy.json")

    def test_min_conteo_tolera_archivo_inexistente(self):
        self.assertEqual(inf.min_conteo("/no/existe/archivo.jsonl"), -1)


class TestCifrasCoinciden(unittest.TestCase):
    def test_percentiles_del_informe_los_del_motor(self):
        import percentiles as pc
        p = os.path.join(pc.ARCHIVO, "funding.jsonl")
        if not os.path.exists(p):
            self.skipTest("sin archivo de funding")
        filas = inf.bloque_posicionamiento()
        self.assertGreater(len(filas), 0)
        r = pc.estado_serie("funding", 400)
        fila = next(f for f in filas if f["serie"] == "funding")
        self.assertAlmostEqual(fila["percentil"], r["corte"]["percentil"], places=6)
        self.assertEqual(fila["n_ventana"], r["corte"]["n_ventana"])

    def test_percentil_dentro_de_rango(self):
        filas = inf.bloque_posicionamiento() if os.path.exists(
            os.path.join(AQUI, "data", "archivo", "funding.jsonl")) else []
        for f in filas:
            self.assertGreaterEqual(f["percentil"], 0.0)
            self.assertLessEqual(f["percentil"], 1.0)
            self.assertIn(f["lectura"], ("alto", "bajo", "normal"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
