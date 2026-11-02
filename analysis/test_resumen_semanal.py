#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_resumen_semanal.py - el digest semanal no puede inflar ni duplicar.

Cubre:
  - El historial de percentiles es idempotente por (fecha, serie): dos corridas
    el mismo dia no duplican filas.
  - La tendencia se calcula sobre cortes ordenados y degrada con < 2 cortes.
  - El digest declara su propio caveat (ventana rodante, archivo joven).
  - Redaccion: la seccion de evolucion solo aparece cuando hay 2+ cortes.

Uso: python -m unittest analysis.test_resumen_semanal
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import resumen_semanal as rs
except ImportError:
    sys.path.insert(0, AQUI)
    import resumen_semanal as rs


def corte(pct, n=8000):
    return {"percentil": pct, "valor": 1.0, "n_ventana": n}


class TestHistorial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = rs.HIST
        rs.HIST = os.path.join(self.tmp, "percentiles_hist.jsonl")

    def tearDown(self):
        rs.HIST = self.orig

    def test_primera_vez_guarda(self):
        rs.guardar_corte("oi", corte(0.7))
        self.assertTrue(os.path.exists(rs.HIST))
        self.assertEqual(len(rs.leer_historial()), 1)

    def test_segunda_vez_el_mismo_dia_no_duplica(self):
        rs.guardar_corte("oi", corte(0.7))
        rs.guardar_corte("oi", corte(0.7))
        self.assertEqual(len(rs.leer_historial()), 1)

    def test_dia_distinto_si_guarda(self):
        rs.guardar_corte("oi", corte(0.7))
        # falsear la fecha: simula el dia siguiente
        fila = rs.leer_historial()[0]
        fila["fecha"] = "2026-11-01"
        with open(rs.HIST, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(fila) + "\n")
        rs.guardar_corte("oi", corte(0.7))
        self.assertEqual(len(rs.leer_historial()), 2)

    def test_historale_quedan_ordenados(self):
        rs.guardar_corte("oi", corte(0.7))
        f = rs.leer_historial()[0]
        f["fecha"] = "2026-10-01"
        with open(rs.HIST, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(f) + "\n")
        rs.guardar_corte("taker", corte(0.5))
        fechas = [x["fecha"] for x in rs.leer_historial()]
        self.assertEqual(fechas, sorted(fechas))


class TestEvolucion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = rs.HIST
        rs.HIST = os.path.join(self.tmp, "percentiles_hist.jsonl")

    def tearDown(self):
        rs.HIST = self.orig

    def _escribir(self, pares):
        with open(rs.HIST, "w", encoding="utf-8") as fh:
            for fecha, pct in pares:
                fh.write(
                    json.dumps(
                        {
                            "fecha": fecha,
                            "serie": "oi",
                            "percentil": pct,
                            "valor": 1.0,
                            "n_ventana": 8000,
                        }
                    )
                    + "\n"
                )

    def test_sin_cortes_no_hay_tendencia(self):
        e = rs.evolucion("oi")
        self.assertEqual(e["n"], 0)
        self.assertIsNone(e["tendencia"])

    def test_un_solo_corte_no_hay_tendencia(self):
        self._escribir([("2026-11-02", 0.5)])
        e = rs.evolucion("oi")
        self.assertEqual(e["n"], 1)
        self.assertIsNone(e["tendencia"])

    def test_subida_clara_se_detecta(self):
        self._escribir(
            [("2026-10-01", 0.30), ("2026-10-08", 0.35), ("2026-10-15", 0.60), ("2026-10-22", 0.70)]
        )
        e = rs.evolucion("oi")
        self.assertEqual(e["tendencia"], "subiendo")
        self.assertGreater(e["delta_pp"], 0)

    def test_bajada_clara_se_detecta(self):
        self._escribir(
            [("2026-10-01", 0.80), ("2026-10-08", 0.75), ("2026-10-15", 0.40), ("2026-10-22", 0.30)]
        )
        e = rs.evolucion("oi")
        self.assertEqual(e["tendencia"], "bajando")

    def test_plano_es_estable(self):
        self._escribir(
            [("2026-10-01", 0.50), ("2026-10-08", 0.52), ("2026-10-15", 0.49), ("2026-10-22", 0.51)]
        )
        self.assertEqual(rs.evolucion("oi")["tendencia"], "estable")

    def test_limita_a_las_ultimas_semanas(self):
        pares = [(f"2026-{m:02d}-01", 0.5) for m in range(1, 11)]
        self._escribir(pares)
        e = rs.evolucion("oi", semanas=4)
        self.assertEqual(e["n"], 4)


class TestRedaccion(unittest.TestCase):
    def test_sin_historial_lo_declara(self):
        md = rs.redactar([], {})
        self.assertIn("Sin datos suficientes", md)

    def test_con_historial_sale_la_tabla(self):
        filas = [
            {
                "serie": "oi",
                "percentil_hoy": 0.7,
                "percentil_hace_7d": 0.4,
                "delta_pp": 30.0,
                "sentido": "subiendo",
                "cobertura_dias": 30,
            }
        ]
        evol = {
            "oi": {
                "n": 3,
                "puntos": [
                    {"fecha": "2026-10-22", "percentil": 0.4},
                    {"fecha": "2026-10-29", "percentil": 0.6},
                    {"fecha": "2026-11-02", "percentil": 0.7},
                ],
                "delta_pp": 30.0,
                "tendencia": "subiendo",
            }
        }
        md = rs.redactar(filas, evol, 7)
        self.assertIn("## B) Evolución", md)
        self.assertIn("| oi | 3 | subiendo", md)
        self.assertIn("ventana rodante", md)

    def test_caveat_del_archivo_joven_presente(self):
        filas = [
            {
                "serie": "oi",
                "percentil_hoy": 0.7,
                "percentil_hace_7d": 0.4,
                "delta_pp": 30.0,
                "sentido": "subiendo",
                "cobertura_dias": 30,
            }
        ]
        md = rs.redactar(filas, {}, 7)
        self.assertIn("2026-11-01", md)
        self.assertIn("no opera", md.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
