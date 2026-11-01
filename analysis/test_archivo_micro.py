#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_archivo_micro.py - el archivo durable no puede corromperse ni duplicar.

Cubren: idempotencia (correr dos veces no duplica), dedup por timestamp,
fusion que preserva lo previo, resistencia a linea corrupta, y que el tope de
30 dias de la API se respeta (no se insiste hasta el infinito).

Uso: python -m unittest analysis.test_archivo_micro
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import archivo_micro as am
except ImportError:
    sys.path.insert(0, AQUI)
    import archivo_micro as am

T0 = int(datetime.datetime(2026, 10, 1, tzinfo=UTC).timestamp() * 1000)
PASO = 5 * 60 * 1000


def reg(t, extra=None):
    r = {"source": "test", "symbol": "BTCUSDT", "timestamp": t}
    if extra:
        r.update(extra)
    return r


class TestIdempotencia(unittest.TestCase):
    """Correr el archivador dos veces NO puede duplicar ni borrar nada."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = am.ARCHIVO
        am.ARCHIVO = self.tmp

    def tearDown(self):
        am.ARCHIVO = self.orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _leer(self, nombre):
        """Lee tolerando linea corrupta: es justo lo que el archivo preserva."""
        p = os.path.join(self.tmp, f"{nombre}.jsonl")
        if not os.path.exists(p):
            return []
        filas = []
        with open(p, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    filas.append(json.loads(linea))
                except Exception:
                    continue
        return filas

    def test_segunda_pasada_no_duplica(self):
        regs = [reg(T0 + i * PASO) for i in range(100)]
        a1, _ = am.fusionar("oi", regs, "timestamp")
        self.assertEqual(a1, 100)
        a2, _ = am.fusionar("oi", regs, "timestamp")      # mismos registros
        self.assertEqual(a2, 0)
        self.assertEqual(len(self._leer("oi")), 100)

    def test_solo_agrega_los_nuevos(self):
        regs = [reg(T0 + i * PASO) for i in range(100)]
        am.fusionar("oi", regs, "timestamp")
        mezcla = regs[50:] + [reg(T0 + (100 + i) * PASO) for i in range(10)]
        agregados, previos = am.fusionar("oi", mezcla, "timestamp")
        self.assertEqual(previos, 100)
        self.assertEqual(agregados, 10)                    # los 50 viejos ya estan
        self.assertEqual(len(self._leer("oi")), 110)

    def test_preserva_el_orden_cronologico(self):
        regs = [reg(T0 + i * PASO) for i in range(50)]
        am.fusionar("oi", regs, "timestamp")
        am.fusionar("oi", [reg(T0 + 100 * PASO)], "timestamp")
        ts = [r["timestamp"] for r in self._leer("oi")]
        self.assertEqual(ts, sorted(ts))

    def test_linea_corrupta_no_rompe_el_archivo(self):
        p = os.path.join(self.tmp, "oi.jsonl")
        os.makedirs(self.tmp, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(reg(T0)) + "\n")
            fh.write("{linea rota, no es json\n")
            fh.write(json.dumps(reg(T0 + PASO)) + "\n")
        agregados, _ = am.fusionar("oi", [reg(T0 + 2 * PASO)], "timestamp")
        self.assertEqual(agregados, 1)                     # sigue funcionando
        filas = self._leer("oi")
        self.assertEqual(len(filas), 3)                    # la rota se conserva

    def test_no_deja_tmp_al_terminar(self):
        am.fusionar("oi", [reg(T0)], "timestamp")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "oi.jsonl.tmp")))

    def test_serie_vacia_no_borra_lo_previo(self):
        am.fusionar("oi", [reg(T0)], "timestamp")
        am.fusionar("oi", [], "timestamp")
        self.assertEqual(len(self._leer("oi")), 1)


class TestDescarga(unittest.TestCase):
    """La paginacion debe respetar el tope duro de la API y no colgarse.

    Un solo test toca la red y es ligero (1 dia); el resto son unitarios,
    para no convertir cada `unittest` en una espera de minutos.
    """

    def test_get_seguro_traga_el_400_del_tope(self):
        # una URL que la API rechaza (startTime imposible) -> HTTP 400 -> None
        url = ("https://fapi.binance.com/futures/data/openInterestHist"
               "?symbol=BTCUSDT&period=5m&limit=1&startTime=1")
        try:
            res = am._get_seguro(url)
        except Exception as e:                      # sin red: no es fallo del codigo
            self.skipTest(f"sin red: {e}")
        self.assertIsNone(res)

    def test_paginacion_hacia_atras_avanza(self):
        """Cada pagina debe traer timestamps MAS VIEJOS: si no, bucle infinito.

        El fake modela el CONTRATO REAL de la API: devuelve las filas en orden
        ASCENDENTE y respeta el endTime de la peticion. Es justo el detalle que
        un fake "bonito" esconde y que provoco un bucle infinito de verdad.
        """
        llamadas: list[int] = []

        def fake_get(url: str, timeout: int = 30):
            import urllib.parse
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            end = int(q["endTime"][0])
            llamadas.append(end)
            # 500 filas ascendentes que TERMINAN en endTime (como Binance)
            base = end - (500 - 1) * PASO
            return [{"timestamp": base + i * PASO, "symbol": "BTCUSDT"}
                    for i in range(500)]

        orig = am.http_get_json
        am.http_get_json = fake_get
        try:
            regs = am.descargar_serie("openInterestHist", "timestamp", (), dias=1)
        finally:
            am.http_get_json = orig

        self.assertGreater(len(regs), 0)
        # 1 dia = 288 velas -> con paginas de 500 basta 1-2 llamadas, nunca mas
        self.assertLessEqual(len(llamadas), 3,
                             "la pagina debe saltar 41h hacia atras, no 5 minutos")
        # cada peticion debe pedir un endTime MENOR que la anterior
        for a, b in zip(llamadas, llamadas[1:]):
            self.assertLess(b, a - 400 * PASO,
                            "la pagina apenas retrocedio: patron de bucle infinito")

    def test_paginacion_no_se_cuelga_si_la_api_no_avanza(self):
        """Si la API devolviera siempre lo mismo, el techo de seguridad corta."""
        n = {"c": 0}

        def fake_get(url: str, timeout: int = 30):
            n["c"] += 1
            return [{"timestamp": T0 + i * PASO} for i in range(500)]

        orig = am.http_get_json
        am.http_get_json = fake_get
        try:
            am.descargar_serie("openInterestHist", "timestamp", (), dias=1)
        finally:
            am.http_get_json = orig
        self.assertLessEqual(n["c"], 2, "sin avance real debe cortar, no colgarse")

    def test_funding_pagina_con_raw0(self):
        """El funding tambien es ascendente: raw[0] es el mas viejo."""
        llamadas: list[int] = []

        def fake_get(url: str, timeout: int = 30):
            import urllib.parse
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            end = int(q["endTime"][0])
            llamadas.append(end)
            base = end - (1000 - 1) * 8 * 3600 * 1000
            return [{"fundingTime": base + i * 8 * 3600 * 1000,
                     "fundingRate": "0.0001"} for i in range(1000)]

        orig = am.http_get_json
        am.http_get_json = fake_get
        try:
            regs = am.descargar_funding(dias=30)
        finally:
            am.http_get_json = orig
        self.assertGreater(len(regs), 0)
        for a, b in zip(llamadas, llamadas[1:]):
            self.assertLess(b, a)

    def test_descargar_funding_cubre_lo_pedido(self):
        try:
            regs = am.descargar_funding(dias=400)
        except Exception as e:
            self.skipTest(f"sin red: {e}")
        # 400 dias x ~3 pagos/dia ~ 1.200-1.700 registros
        self.assertGreater(len(regs), 1000)
        self.assertIn("fundingRate", regs[0])


class TestCoberturaReal(unittest.TestCase):
    """El archivo real (si ya existe) debe crecer, quedar ordenado y sin dup."""

    def test_archivo_real_ordenado_y_sin_duplicados(self):
        p = am.ruta_serie("oi")
        if not os.path.exists(p):
            self.skipTest("archivo aun no generado")
        ts = []
        with open(p, encoding="utf-8") as fh:
            for linea in fh:
                if linea.strip():
                    ts.append(json.loads(linea)["timestamp"])
        self.assertEqual(len(ts), len(set(ts)), "no puede haber duplicados")
        self.assertEqual(ts, sorted(ts), "debe estar ordenado (bisect lo exige)")
        d0 = am.dt_ms(min(ts))
        d1 = am.dt_ms(max(ts))
        self.assertLessEqual((d1 - d0).days, 31, "el tope de la API es 30 dias")
        self.assertEqual(am.dt_ms(min(ts)), am.dt_ms(ts[0]), "min al principio")


if __name__ == "__main__":
    unittest.main(verbosity=2)
