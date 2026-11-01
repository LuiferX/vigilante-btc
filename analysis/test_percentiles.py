#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_percentiles.py - el motor de precision no puede mentir.

Cubren:
  - CERO look-ahead: una observacion futura no cambia el percentil de una
    anterior (la regla que hace honesto al informe).
  - El percentil mide la posicion DENTRO de la ventana trailing, no dentro de
    toda la serie (comportamiento correcto, documentado).
  - Degradacion honesta: con <30 obs devuelve None, no inventa un numero.
  - Casteo de los campos numericos que la API entrega como cadena.
  - Orden garantizado (los consumidores hacen bisect).

Uso: python -m unittest analysis.test_percentiles
"""

from __future__ import annotations

import datetime
import os
import sys
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import percentiles as pc
except ImportError:
    sys.path.insert(0, AQUI)
    import percentiles as pc

T0 = int(datetime.datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)
H = 3_600_000                      # 1 h entre obs
V5 = datetime.timedelta(days=5)


def ts_n(n, paso=H):
    return [T0 + i * paso for i in range(n)]


class TestCausaLidad(unittest.TestCase):
    """La regla de oro: el futuro no puede cambiar el pasado medido."""

    def test_observacion_futura_no_cambia_el_percentil_anterior(self):
        ts = ts_n(100)
        vs = [float(i % 20) for i in range(100)]      # oscilante, no monotona
        base = pc.percentil_causal(ts, vs, ts[50], V5)
        self.assertIsNotNone(base)
        # mismo conjunto + un extremo al final (futuro respecto de ts[50])
        ts2 = ts + [ts[-1] + H]
        vs2 = vs + [10000.0]
        despues = pc.percentil_causal(ts2, vs2, ts[50], V5)
        self.assertEqual(base["percentil"], despues["percentil"],
                         "el futuro cambio el percentil pasado: look-ahead")

    def test_ventana_solo_mira_hacia_atras(self):
        ts = ts_n(100)
        vs = [float(i % 20) for i in range(100)]
        r = pc.percentil_causal(ts, vs, ts[50], V5)
        self.assertLessEqual(r["hasta"], pc.dt_ms(ts[50]).isoformat())
        self.assertGreaterEqual(r["n_ventana"], 30)

    def test_percentil_de_una_serie_plana_es_medio(self):
        ts = ts_n(60)
        vs = [5.0] * 60
        r = pc.percentil_causal(ts, vs, ts[-1], V5)
        self.assertEqual(r["valor"], 5.0)
        self.assertGreaterEqual(r["percentil"], 0.9)   # todos empatados arriba

    def test_ventana_trailing_corta_hace_que_el_ultimo_sea_maximo(self):
        """Comportamiento DOCUMENTADO: con serie monotona y ventana corta, el
        valor reciente es el maximo de SU ventana. Es correcto: el percentil
        mide posicion dentro de la ventana, no de toda la serie."""
        ts = ts_n(100)
        vs = [float(i) for i in range(100)]
        r = pc.percentil_causal(ts, vs, ts[-1], datetime.timedelta(days=2))
        self.assertGreater(r["percentil"], 0.9)

    def test_serie_oscilante_da_percentiles_informativos(self):
        # oscila 0..9 y el ultimo valor es 5 (mitad): su percentil debe ser ~0.55
        ts = ts_n(300)
        vs = [float(i % 10) for i in range(300)]
        vs[-1] = 5.0
        r = pc.percentil_causal(ts, vs, ts[-1], V5)
        self.assertLess(r["percentil"], 0.9, "con oscilacion el pct debe ser <0.9")
        self.assertGreater(r["percentil"], 0.4, "y tampoco aparece en el fondo")

    def test_percentil_respeta_empates_hacia_arriba(self):
        # serie plana: el valor debe quedar en el techo de su ventana (1.0),
        # no en 0. Contar los empates como "debajo" subestima el percentil.
        ts = ts_n(60)
        r = pc.percentil_causal(ts, [5.0] * 60, ts[-1], V5)
        self.assertGreaterEqual(r["percentil"], 0.9)


class TestDegradacionHonesta(unittest.TestCase):
    def test_pocas_obs_devuelve_none(self):
        ts = ts_n(5)
        vs = [1.0] * 5
        self.assertIsNone(pc.percentil_causal(ts, vs, ts[-1], V5))

    def test_t_referencia_antes_de_todo_devuelve_none(self):
        ts = ts_n(60)
        vs = [1.0] * 60
        self.assertIsNone(pc.percentil_causal(ts, vs, T0 - H, V5))


class TestCargaDeDatos(unittest.TestCase):
    def test_archivo_real_ordena_y_castea(self):
        for nombre in ("funding", "oi"):
            p = os.path.join(pc.ARCHIVO, pc.SERIES[nombre][0])
            if not os.path.exists(p):
                self.skipTest(f"sin archivo de {nombre}")
            ts, vs = pc.cargar(nombre)
            self.assertGreater(len(ts), 100)
            self.assertEqual(ts, sorted(ts), "debe venir ordenado (bisect)")
            for v in vs:
                self.assertIsInstance(v, float)
            self.assertEqual(len(ts), len(vs))

    def test_linea_corrupta_no_rompe_la_carga(self):
        # escribe un archivo temporal con lineas malas y verifica que solo
        # sobreviven las validas
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "funding.jsonl"), "w", encoding="utf-8") as fh:
                fh.write('{"fundingTime": 1, "fundingRate": "0.0001"}\n')
                fh.write("{linea rota\n")
                fh.write('{"fundingTime": 2, "fundingRate": "no-numero"}\n')
                fh.write('{"fundingTime": 3, "fundingRate": "0.0002"}\n')
            orig = pc.ARCHIVO
            try:
                pc.ARCHIVO = d
                ts, vs = pc.cargar("funding")
            finally:
                pc.ARCHIVO = orig
            self.assertEqual(ts, [1, 3], "las dos lineas validas sobreviven")
            self.assertEqual(vs, [0.0001, 0.0002])


class TestEstadoSerie(unittest.TestCase):
    def test_lectura_extremos(self):
        if not os.path.exists(os.path.join(pc.ARCHIVO, "funding.jsonl")):
            self.skipTest("sin archivo de funding")
        r = pc.estado_serie("funding", 400)
        self.assertIsNotNone(r)
        self.assertIn(r["lectura"], ("alto", "bajo", "normal"))
        self.assertGreaterEqual(r["cobertura_dias"], 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
