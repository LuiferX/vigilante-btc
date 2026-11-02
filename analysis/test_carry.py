#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_carry.py - la medida del carry no puede inflarse.

Cubre: el peor ventana rodante (que la media no esconda perdidas), el neto tras
coste amortizado, y que los datos se lean como numero (la API los da como
cadena).

Uso: python -m unittest analysis.test_carry
"""

from __future__ import annotations

import datetime
import os
import sys
import tempfile
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import carry
except ImportError:
    sys.path.insert(0, AQUI)
    import carry

P = int(datetime.datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)
H8 = 8 * 3600 * 1000


def filas(vals, n=None):
    out = []
    for i, v in enumerate(vals if n is None else vals[:n]):
        out.append((datetime.datetime.fromtimestamp((P + i * H8) / 1000, tz=UTC), v))
    return out


class TestPeorVentana(unittest.TestCase):
    def test_peor_ventana_encuentra_el_minimo(self):
        # 100 pagos positivos y 30 negativos al final
        vals = [0.0001] * 100 + [-0.001] * 30
        r = carry.peor_ventana(filas(vals), 10)  # 10 dias = 30 pagos
        # el peor tramo empieza en el pago 100: 100 x 8h = 33,3 dias -> 3-feb
        self.assertEqual(r["inicio"], "2026-02-03")
        # 30 pagos de -0,001 (= -0,1% cada uno) -> -3,0%
        self.assertEqual(r["suma_pct"], -3.0)

    def test_ventana_mayor_que_los_datos_devuelve_none(self):
        self.assertIsNone(carry.peor_ventana(filas([0.0001] * 10), 10))

    def test_todo_positivo_no_da_ventana_negativa(self):
        vals = [0.0001] * 200
        r = carry.peor_ventana(filas(vals), 30)
        self.assertGreater(r["suma_pct"], 0)


class TestNetoPorHold(unittest.TestCase):
    def test_hold_corto_pierde_por_el_coste(self):
        """Con 7 dias el carry no llega a pagar el viaje: la estructura exige
        aguantar, y eso es informacion, no un detalle."""
        m = carry.medir(holds=(7,))
        self.assertLess(m["neto_por_hold"]["7d"]["neto_pct"], 0)

    def test_hold_largo_es_positivo(self):
        m = carry.medir(holds=(30, 90))
        self.assertGreater(m["neto_por_hold"]["30d"]["neto_pct"], 0)
        self.assertGreater(m["neto_por_hold"]["90d"]["neto_pct"], 0)

    def test_anualizado_es_coherente(self):
        m = carry.medir(holds=(30,))
        d = m["neto_por_hold"]["30d"]
        self.assertAlmostEqual(
            d["anualizado_neto_pct"], round(d["neto_pct"] * 365 / 30, 2), places=1
        )


class TestLecturaDeDatos(unittest.TestCase):
    def test_funding_como_cadena_se_castea(self):
        """La API devuelve fundingRate como string; si no se castea, la media
        revienta o miente."""
        import json

        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "funding.jsonl"), "w", encoding="utf-8") as fh:
                for i in range(10):
                    fh.write(
                        json.dumps(
                            {
                                "source": "binance_fundingRate",
                                "fundingTime": P + i * H8,
                                "fundingRate": "0.0001",
                            }
                        )
                        + "\n"
                    )
            orig = None
            try:
                import percentiles as pc

                orig = pc.ARCHIVO
                pc.ARCHIVO = d
                ts, vs = pc.cargar("funding")
            finally:
                if orig:
                    pc.ARCHIVO = orig
            self.assertTrue(all(isinstance(v, float) for v in vs))
            self.assertAlmostEqual(vs[0], 0.0001)


class TestRiesgo(unittest.TestCase):
    def test_meses_negativos_se_cuentan(self):
        m = carry.medir()
        r = m["riesgo"]
        self.assertIn("peor_30d", r)
        self.assertGreaterEqual(r["meses_totales"], 50)
        self.assertLessEqual(r["meses_negativos"], r["meses_totales"])
        self.assertLessEqual(r["peor_mes_pct"], r["mediana_mes_pct"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
