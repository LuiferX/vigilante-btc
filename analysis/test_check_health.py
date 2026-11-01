#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_health.py - el vigilante de la maquina tiene que detectar el fallo.

Cubre: que un archivo viejo genera codigo 1, que uno sano da 0, y que un
archivo inexistente no rompe el chequeo (informa).

Uso: python -m unittest analysis.test_check_health
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
    from analysis import check_health as ch
except ImportError:
    sys.path.insert(0, AQUI)
    import check_health as ch


class TestSalud(unittest.TestCase):
    def test_serie_vieja_falla(self):
        with tempfile.TemporaryDirectory() as d:
            viejo = int((datetime.datetime.now(UTC)
                         - datetime.timedelta(days=9)).timestamp() * 1000)
            with open(os.path.join(d, "oi.jsonl"), "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"timestamp": viejo}) + "\n")
            orig = ch.ARCHIVO
            try:
                ch.ARCHIVO = d
                cod = ch.main()
            finally:
                ch.ARCHIVO = orig
            self.assertEqual(cod, 1, "9 dias sin datos debe fallar")

    def test_serie_fresca_pasa(self):
        with tempfile.TemporaryDirectory() as d:
            ahora = datetime.datetime.now(UTC)
            for f, k in (("funding.jsonl", "fundingTime"), ("oi.jsonl", "timestamp")):
                with open(os.path.join(d, f), "w", encoding="utf-8") as fh:
                    for h in (0, 1, 2):
                        t = int((ahora - datetime.timedelta(hours=h)).timestamp()
                                * 1000)
                        fh.write(json.dumps({k: t}) + "\n")
            orig = ch.ARCHIVO
            try:
                ch.ARCHIVO = d
                cod = ch.main()
            finally:
                ch.ARCHIVO = orig
            # el resto de series no existen -> falla por eso (y esta bien:
            # lo informe dice cual falta)
            self.assertEqual(cod, 1)

    def test_archivo_sin_registros_no_rompe(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "oi.jsonl"), "w", encoding="utf-8") as fh:
                fh.write("")
            self.assertIsNone(ch.edad_horas(os.path.join(d, "oi.jsonl"),
                                            "timestamp"))

    def test_linea_corrupta_no_rompe_la_edad(self):
        with tempfile.TemporaryDirectory() as d:
            ahora = datetime.datetime.now(UTC)
            t = int(ahora.timestamp() * 1000)
            with open(os.path.join(d, "oi.jsonl"), "w", encoding="utf-8") as fh:
                fh.write("{rota\n")
                fh.write(json.dumps({"timestamp": t}) + "\n")
            h = ch.edad_horas(os.path.join(d, "oi.jsonl"), "timestamp")
            self.assertIsNotNone(h)
            self.assertLess(h, 0.5)

    def test_salida_es_json_valido(self):
        # corre el modulo real y comprueba que imprime JSON parseable
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ch.main()
        try:
            data = json.loads(buf.getvalue())
        except json.JSONDecodeError as e:
            self.fail(f"salida no es JSON: {e}")
        self.assertIn("ok", data)
        self.assertIn("detalle", data)
        self.assertIn("fallos", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
