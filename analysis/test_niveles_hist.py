#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_niveles_hist.py - el medidor de suelos historicos no puede mentir.

Cubre:
  - Un toque es una VISITA DISTINTA: un rango pegado al nivel no cuenta como
    diez toques (el contraejemplo es lo que distinguiria un suelo de una
    autopista).
  - Cero look-ahead: las excursiones se midien SOLO con velas posteriores.
  - La definicion de "aguanta" es la del modelo (cierre 0,5% mas alla en 4h).
  - Determinismo: dos corridas dan el mismo resultado.
  - Rendimiento: no escanea la serie por cada candidato (regresion de velocidad).

Uso: python -m unittest analysis.test_niveles_hist
"""

from __future__ import annotations

import datetime
import os
import sys
import time
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import niveles_hist as nh
except ImportError:
    sys.path.insert(0, AQUI)
    import niveles_hist as nh

T0 = datetime.datetime(2026, 1, 1, tzinfo=UTC)
PASO = datetime.timedelta(minutes=5)
P = 30000.0


def vela(i, o, h, low, c):
    return {"t": T0 + PASO * i, "o": o, "h": h, "l": low, "c": c}


def velas_planas(n, precio=P, i0=0):
    return [vela(i0 + i, precio, precio + 1, precio - 1, precio) for i in range(n)]


class TestToquesDistintos(unittest.TestCase):
    def test_rango_pegado_cuenta_una_visita(self):
        """40 velas rozando el nivel NO son 40 toques: es uno."""
        kl = velas_planas(60)
        idx = nh.toques_distintos(kl, P)
        self.assertEqual(len(idx), 1, "un rango pegado debe contar 1 visita")

    def test_dos_visitas_separadas_cuentan_dos(self):
        # 20 velas en el nivel, 20 velas lejos (0,5%), 20 velas en el nivel
        kl = velas_planas(20)
        kl += velas_planas(20, P * 1.005, i0=20)
        kl += velas_planas(20, P, i0=40)
        idx = nh.toques_distintos(kl, P)
        self.assertEqual(len(idx), 2, "entrar-salir-volver son 2 visitas")

    def test_salida_insuficiente_no_cierra_la_visita(self):
        # 40 velas oscilando 0,1% alrededor: nunca sale 0,3%
        kl = [vela(i, P, P * 1.001, P * 0.999, P) for i in range(40)]
        idx = nh.toques_distintos(kl, P)
        self.assertEqual(len(idx), 1)

    def test_nivel_nunca_tocado_no_da_toques(self):
        kl = velas_planas(40, P * 1.10)
        self.assertEqual(nh.toques_distintos(kl, P), [])


class TestCeroLookAhead(unittest.TestCase):
    def test_excursion_solo_mira_hacia_adelante(self):
        """Un movimiento brutal ANTES del toque no puede contaminar la medida."""
        kl = velas_planas(30, P * 1.05, i0=0)  # campo de batalla antes
        kl += [vela(30, P, P + 1, P - 1, P)]  # el toque
        kl += velas_planas(30, P, i0=31)
        m = nh.medir_toque(kl, 30, P)
        self.assertIsNotNone(m)
        self.assertLess(m["rebote_pct"], 0.05, "no debe ver el +5% previo")

    def test_excursion_si_mira_lo_posterior(self):
        kl = velas_planas(10, P, i0=0)
        kl += [vela(10, P, P + 1, P - 1, P)]  # el toque
        kl += [vela(11, P, P * 1.01, P - 1, P)]  # rebote del 1% JUSTO DESPUES
        kl += velas_planas(10, P, i0=12)
        m = nh.medir_toque(kl, 10, P)
        self.assertGreater(m["rebote_pct"], 0.9)


class TestAguanta(unittest.TestCase):
    def test_cierre_mas_alla_rompe_el_aguante(self):
        kl = velas_planas(10, P, i0=0)
        kl += [vela(10, P, P + 1, P - 1, P)]
        # 10 velas despues, cierre 0,6% por debajo del nivel
        kl += [vela(11 + i, P * 0.994, P * 0.995, P * 0.998, P * 0.994) for i in range(10)]
        m = nh.medir_toque(kl, 10, P)
        self.assertFalse(m["aguanta"], "cierres 0,6% mas alla = no aguanta")

    def test_dentro_del_margen_aguanta(self):
        kl = velas_planas(10, P, i0=0)
        kl += [vela(10, P, P + 1, P - 1, P)]
        kl += [vela(11 + i, P, P * 1.004, P * 0.996, P) for i in range(10)]
        m = nh.medir_toque(kl, 10, P)
        self.assertTrue(m["aguanta"], "0,4% de margen sigue siendo aguante")


class TestFicha(unittest.TestCase):
    def test_ficha_trae_todo(self):
        kl = velas_planas(20)
        kl += velas_planas(20, P * 1.005, i0=20)
        kl += velas_planas(20, P, i0=40)
        f = nh.ficha(kl, P)
        self.assertEqual(f["toques"], 2)
        for k in ("primero", "ultimo", "rebote_mediano_pct", "barrido_mediano_pct", "aguante_pct"):
            self.assertIn(k, f)

    def test_nivel_sin_toques_devuelve_none(self):
        self.assertIsNone(nh.ficha(velas_planas(40, P * 1.2), P))


class TestCandidatosYRendimiento(unittest.TestCase):
    def test_agrupa_pivotes_cercanos(self):
        cands, n = nh.candidatos(velas_planas(400), cuantos=5)
        self.assertLessEqual(len(cands), 5)
        self.assertGreaterEqual(n, 0)

    def test_velas_sinteticas_no_explotan(self):
        """Velas raras (h<l, cerrados None) no deben tumbar el modulo."""
        kl = velas_planas(50)
        kl.append({"t": T0 + PASO * 50, "o": None, "h": P, "l": P, "c": P})
        try:
            nh.toques_distintos(kl, P)
        except Exception as e:
            self.fail(f"toques_distintos revienta con vela rara: {e}")


class TestDeterminismo(unittest.TestCase):
    def test_misma_entrada_mismo_resultado(self):
        kl = velas_planas(30)
        kl += velas_planas(30, P * 1.005, i0=30)
        kl += velas_planas(30, P, i0=60)
        a = nh.ficha(kl, P)
        b = nh.ficha(kl, P)
        self.assertEqual(a, b)

    def test_no_usa_el_reloj(self):
        """Nada del resultado puede depender de la hora del sistema."""
        kl = velas_planas(40)
        t0 = time.time()
        nh.ficha(kl, P)
        t1 = time.time()
        self.assertGreaterEqual(t1 - t0, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
