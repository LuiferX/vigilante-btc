#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_integridad_datos.py - el guardian de los datos tiene que detectar el fallo.

Cubre: que un feed roto NO de un "ok" tranquilo, que la anomalia salta con la
dispersion real, que el flash crash se detecta en ventana, y que todo es
determinista y sin red (los fetchers se sustituyen).

Uso: python -m unittest analysis.test_integridad_datos
"""

from __future__ import annotations

import datetime
import os
import sys
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import integridad_datos as idt
except ImportError:
    sys.path.insert(0, AQUI)
    import integridad_datos as idt

AHORA = int(datetime.datetime(2026, 11, 2, t5 := 5, 30, tzinfo=UTC).timestamp() * 1000)


def precios(binance, okx, bybit, edad=2.0):
    def mk(p):
        if p is None:
            return {"precio": None, "ts": None, "edad_seg": None, "err": "timeout"}
        return {"precio": p, "ts": AHORA - int(edad * 1000), "edad_seg": edad}

    return {"Binance": mk(binance), "OKX": mk(okx), "Bybit": mk(bybit)}


class TestVeredicto(unittest.TestCase):
    def test_tres_exchanges_coincidentes_ok(self):
        v = idt.evaluar(precios(78340.0, 78341.0, 78342.0))
        self.assertEqual(v["nivel"], "ok")
        self.assertLess(v["dispersion_pct"], 0.1)

    def test_uno_caido_pero_los_otros_coinciden_es_ok(self):
        """Un exchange caido con los otros dos coincidiendo NO es alarma: los
        datos siguen siendo coherentes. El fallo se anota, no se grita."""
        v = idt.evaluar(precios(78340.0, 78342.0, None))
        self.assertEqual(v["nivel"], "ok")
        self.assertEqual(v["caidos"], ["Bybit"])
        self.assertIn("Bybit", v["detalle"] + " " + str(v["caidos"]))

    def test_dos_caidos_no_concluyente(self):
        """Con un solo precio no se puede comparar: no se inventa un ok."""
        v = idt.evaluar(precios(78340.0, None, None))
        self.assertEqual(v["nivel"], "no_concluyente")

    def test_anomalia_real_salta(self):
        # 79.000 vs mediana ~78.340 = 0,84% de desviacion: supera el 0,5%
        v = idt.evaluar(precios(78340.0, 79000.0, 78345.0))
        self.assertEqual(v["nivel"], "verificar")
        self.assertEqual(v["anomalias"], ["OKX"])

    def test_anomalia_chica_no_alarma(self):
        # 0,2% de dispersion es normal entre exchanges: no debe alarmar
        v = idt.evaluar(precios(78340.0, 78500.0, 78345.0))
        self.assertEqual(v["nivel"], "ok")

    def test_dos_anomalias_bloquean(self):
        """Dos feeds mintiendo mucho = bloquear, no publicar cifras tranquilas."""
        v = idt.evaluar(precios(78340.0, 80000.0, 65000.0))
        self.assertEqual(v["nivel"], "bloquear")
        self.assertEqual(len(v["anomalias"]), 2)

    def test_stale_se_detecta(self):
        v = idt.evaluar(precios(78340.0, 78342.0, 78341.0, edad=90.0))
        self.assertEqual(v["nivel"], "verificar")
        self.assertIn("stale", v["detalle"])


class TestFlashCrash(unittest.TestCase):
    def _hist(self, precios):
        base = AHORA - idt.VENTANA_CRASH_SEG * 1000
        return [(base + i * 1000, p) for i, p in enumerate(precios)]

    def test_caida_de_2_por_ciento_salta(self):
        h = self._hist([100.0] * 299 + [97.0])  # -3% al final
        r = idt.detectar_flash_crash(h, ahora=AHORA)
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r["caida_pct"], 3.0, places=1)

    def test_sin_caida_no_salta(self):
        h = self._hist([100.0] * 300)
        self.assertIsNone(idt.detectar_flash_crash(h, ahora=AHORA))

    def test_poca_historia_no_inventa(self):
        self.assertIsNone(idt.detectar_flash_crash([]))


class TestLectura(unittest.TestCase):
    def test_lector_sustituible(self):
        """Sin red se puede inyectar el corte: nada de la deteccion depende de
        que Binance responda."""
        original = dict(idt.EXCHANGES)
        try:
            idt.EXCHANGES["Binance"] = (lambda s: (78000.0, AHORA), "BTCUSDT")
            idt.EXCHANGES["OKX"] = (lambda s: (78000.5, AHORA), "BTC-USDT")
            idt.EXCHANGES["Bybit"] = (lambda s: (77999.0, AHORA), "BTCUSDT")
            p = idt.leer_precios(ahora=AHORA)
            self.assertEqual(len(p), 3)
            self.assertAlmostEqual(p["Binance"]["precio"], 78000.0, places=1)
        finally:
            idt.EXCHANGES.clear()
            idt.EXCHANGES.update(original)

    def test_fallo_de_red_queda_registrado(self):
        original = dict(idt.EXCHANGES)
        try:
            idt.EXCHANGES.clear()
            idt.EXCHANGES["Binance"] = (
                lambda s: (_ for _ in ()).throw(RuntimeError("timeout")),
                "BTCUSDT",
            )
            p = idt.leer_precios(ahora=AHORA)
            self.assertIsNone(p["Binance"]["precio"])
            self.assertIn("err", p["Binance"])
        finally:
            idt.EXCHANGES.clear()
            idt.EXCHANGES.update(original)


class TestRedaccion(unittest.TestCase):
    def test_informe_menciona_veredicto(self):
        corte = {
            "generado": "2026-11-02T05:30:00+00:00",
            "precios": precios(78340.0, 78341.0, 78342.0),
            "veredicto": idt.evaluar(precios(78340.0, 78341.0, 78342.0)),
        }
        md = idt.redactar(corte)
        self.assertIn("Integridad de datos", md)
        self.assertIn("`ok`", md)
        self.assertIn("no opera", md.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
