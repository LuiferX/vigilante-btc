#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_expr_edge.py - pruebas de las reglas duras de expr_edge.py.

Cubren lo exigido por la mision:
  1. CERO look-ahead (entrada al open de t+1, percentiles causales).
  2. Costes SIEMPRE aplicados (fee + slippage + funding con signo correcto).
  3. Dedup de eventos solapados (cooldown explicito).
  4. Bootstrap deterministico (semilla fija).

Uso: python -m unittest analysis.test_expr_edge
"""

from __future__ import annotations

import datetime
import os
import sys
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))

try:
    from analysis import expr_edge as ee
except ImportError:  # ejecucion directa: python analysis/test_expr_edge.py
    sys.path.insert(0, AQUI)
    import expr_edge as ee

T0 = datetime.datetime(2023, 6, 1, tzinfo=UTC)
PASO = datetime.timedelta(minutes=5)
ESPACIO_F = datetime.timedelta(minutes=5)   # obs densas: la logica solo mira timestamps


def klines_sinteticas(n, base=30000.0, paso_precio=0.0):
    """n velas 5m; paso_precio fuerza el bruto (0 = plano)."""
    kl = []
    for i in range(n):
        t = T0 + PASO * i
        o = base + paso_precio * i
        c = o + paso_precio
        kl.append({"t": t, "o": o, "h": max(o, c) + 1, "l": min(o, c) - 1, "c": c})
    return kl


def funding_sintetico(valores, espacio=ESPACIO_F, inicio=T0):
    return [(inicio + espacio * i, v) for i, v in enumerate(valores)]


def kl_para(funding, extra_barras=200):
    """Klines 5m que cubren toda la serie de funding + margen de holder."""
    n = int((funding[-1][0] - funding[0][0]) / PASO) + extra_barras
    return klines_sinteticas(max(n, 300))


class TestSinLookAhead(unittest.TestCase):
    """Regla 1: la senal usa datos hasta t; la entrada es el open de t+1."""

    def test_entrada_es_open_de_la_vela_siguiente(self):
        kl = kl_para(funding_sintetico([0.0001] * 41))
        vals = [0.0001] * 40 + [0.0100]      # spike al final (>= p95 causal)
        f = funding_sintetico(vals)
        ee._indexar_funding(f)
        evs = ee.eventos_h1(f, kl, cooldown_h=8)
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["t"], f[40][0])          # timestamp exacto del spike
        self.assertGreater(e["t_ent"], e["t"])      # entrada ESTRICTAMENTE posterior
        idx = next(i for i, v in enumerate(kl) if v["t"] == e["t_ent"])
        self.assertEqual(idx, 41)                   # el bar siguiente al spike
        self.assertEqual(e["entrada"], kl[idx]["o"])
        self.assertEqual(e["lado"], "SHORT")        # funding alto -> corto

    def test_percentiles_causales_no_se_miran_a_si_mismos(self):
        """El spike no puede subir su propio umbral (look-ahead clasico)."""
        kl = kl_para(funding_sintetico([0.0001] * 41))
        vals = [0.0001] * 40 + [0.0100]
        f = funding_sintetico(vals)
        evs = ee.eventos_h1(f, kl, cooldown_h=8)
        self.assertEqual(len(evs), 1)
        e = evs[0]
        # si el umbral se calculara CON el spike, este no dispararia
        self.assertLess(e["umbral_alto"], e["funding"])
        self.assertGreaterEqual(e["funding"], e["umbral_alto"])

    def test_funding_extremo_bajo_genera_largo(self):
        kl = kl_para(funding_sintetico([0.0001] * 41))
        vals = [0.0001] * 40 + [-0.0100]     # spike negativo -> largo
        f = funding_sintetico(vals)
        evs = ee.eventos_h1(f, kl, cooldown_h=8)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["lado"], "LONG")
        self.assertLessEqual(evs[0]["funding"], evs[0]["umbral_bajo"])

    def test_min_obs_minimo(self):
        kl = kl_para(funding_sintetico([0.0100] * 5))
        f = funding_sintetico([0.0100] * 5)      # 5 obs < MIN_OBS
        self.assertEqual(ee.eventos_h1(f, kl, cooldown_h=8), [])

    def test_empate_con_el_default_no_dispara(self):
        """Regresion: el 27% de registros es exactamente +0.0001 (default).

        Con >= el p95 empataba con el default y generaba eventos falsos en el
        16,6% de las ventanas. La comparacion debe ser ESTRICTA.
        """
        kl = kl_para(funding_sintetico([0.0001] * 60))
        # 59 default + 1 default mas: NO hay extremo, no debe disparar nada
        f = funding_sintetico([0.0001] * 60)
        self.assertEqual(ee.eventos_h1(f, kl, cooldown_h=8), [])
        # y cualquier mezcla de defaults sigue sin disparar
        f2 = funding_sintetico([0.0001] * 30 + [0.0002] + [0.0001] * 29)
        evs = ee.eventos_h1(f2, kl, cooldown_h=8)
        # 0.0002 > p95(=0.0001) si es extremo real; defaults nunca
        for e in evs:
            self.assertNotEqual(e["funding"], 0.0001)


class TestCostes(unittest.TestCase):
    """Regla 2: costes siempre; signo del funding correcto."""

    def _evento(self, lado, atr_pct=0.10):
        t_ent = T0 + PASO * 10
        return {"t": T0, "t_ent": t_ent, "lado": lado, "funding": 0.0005,
                "entrada": 30000.0, "atr_pct": atr_pct}

    def test_neto_resta_fee_slippage(self):
        kl = klines_sinteticas(300, paso_precio=0.0)     # plano -> bruto 0
        ee._indexar_funding([])
        e = self._evento("SHORT")
        r = ee.resolver(e, kl, [v["t"] for v in kl], 96)
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r["bruto"], 0.0, places=9)
        self.assertAlmostEqual(r["funding_pct"], 0.0, places=9)
        esperado = ee.FEE_PCT * 2 + ee.SLIP_BASE * 2 + ee.SLIP_K * 0.10 * 2
        self.assertAlmostEqual(r["coste"], esperado, places=9)
        self.assertAlmostEqual(r["neto"], -esperado, places=9)
        self.assertLess(r["neto"], 0.0)

    def test_largo_cobra_funding_negativo(self):
        kl = klines_sinteticas(300, paso_precio=0.0)
        e = self._evento("LONG")
        # pago de -0.05% dentro del hold: el largo COBRA -> aporte +0.05%
        ee._indexar_funding([(e["t_ent"] + PASO * 2, -0.0005)])
        r = ee.resolver(e, kl, [v["t"] for v in kl], 96)
        self.assertGreater(r["funding_pct"], 0.0)
        self.assertAlmostEqual(r["funding_pct"], 0.05, places=9)

    def test_corto_cobra_funding_positivo(self):
        kl = klines_sinteticas(300, paso_precio=0.0)
        e = self._evento("SHORT")
        ee._indexar_funding([(e["t_ent"] + PASO * 2, 0.0005)])
        r = ee.resolver(e, kl, [v["t"] for v in kl], 96)
        self.assertGreater(r["funding_pct"], 0.0)
        self.assertAlmostEqual(r["funding_pct"], 0.05, places=9)

    def test_fuera_del_hold_no_cuenta(self):
        kl = klines_sinteticas(300, paso_precio=0.0)
        e = self._evento("SHORT")
        # pago DESPUES del cierre del hold (96 velas x 5min = 8h despues)
        ee._indexar_funding([(e["t_ent"] + datetime.timedelta(hours=20), 0.0005)])
        r = ee.resolver(e, kl, [v["t"] for v in kl], 96)
        self.assertAlmostEqual(r["funding_pct"], 0.0, places=9)

    def test_bruto_correcto_en_ambos_lados(self):
        kl = klines_sinteticas(300, paso_precio=1.0)      # sube 1 punto por vela
        e = self._evento("LONG")
        ee._indexar_funding([])
        r = ee.resolver(e, kl, [v["t"] for v in kl], 2)
        self.assertGreater(r["bruto"], 0.0)               # largo en suba gana
        e2 = self._evento("SHORT")
        r2 = ee.resolver(e2, kl, [v["t"] for v in kl], 2)
        self.assertLess(r2["bruto"], 0.0)                 # corto en suba pierde


class TestIndependencia(unittest.TestCase):
    """Regla 3: un evento por cascada, cooldown explicito."""

    def test_cooldown_respeta_separacion_minima(self):
        vals = [0.0001] * 40
        f = funding_sintetico(vals)
        base = f[-1][0]
        for k in range(1, 4):                             # 3 spikes cada 8h
            f.append((base + datetime.timedelta(hours=8 * k), 0.0100))
        f.append((base + datetime.timedelta(hours=8 * 4), 0.0001))
        kl = kl_para(f)
        evs = ee.eventos_h1(f, kl, cooldown_h=24)
        self.assertGreaterEqual(len(evs), 1)
        for a, b in zip(evs, evs[1:]):
            self.assertGreaterEqual((b["t"] - a["t"]).total_seconds(), 24 * 3600)

    deftest = None  # marcador (se elimina)

    def test_cooldown_menor_deja_pasar_mas(self):
        vals = [0.0001] * 40
        f = funding_sintetico(vals)
        base = f[-1][0]
        for k in range(1, 4):
            f.append((base + datetime.timedelta(hours=8 * k), 0.0100))
        f.append((base + datetime.timedelta(hours=8 * 4), 0.0001))
        kl = kl_para(f)
        ev24 = ee.eventos_h1(f, kl, cooldown_h=24)
        ev8 = ee.eventos_h1(f, kl, cooldown_h=8)
        # con cooldown 8h los spikes de 8h de separacion si pasan
        self.assertGreaterEqual(len(ev8), len(ev24))
        for a, b in zip(ev8, ev8[1:]):
            self.assertGreaterEqual((b["t"] - a["t"]).total_seconds(), 8 * 3600)


class TestBootstrap(unittest.TestCase):
    """Regla: bootstrap deterministico con semilla fija."""

    def test_misma_semilla_mismo_intervalo(self):
        vals = [(-1) ** i * (0.1 + 0.01 * i) for i in range(300)]
        self.assertEqual(ee.bootstrap_ci(vals, semilla=42), ee.bootstrap_ci(vals, semilla=42))

    def test_semillas_distintas_estables_cada_una(self):
        vals = [(-1) ** i * (0.1 + 0.01 * i) for i in range(300)]
        a = ee.bootstrap_ci(vals, semilla=42)
        b = ee.bootstrap_ci(vals, semilla=7)
        self.assertEqual(a, ee.bootstrap_ci(vals, semilla=42))
        self.assertEqual(b, ee.bootstrap_ci(vals, semilla=7))
        for lo, hi, p in (a, b):
            self.assertLessEqual(lo, hi)
            self.assertTrue(0.0 <= p <= 1.0)

    def test_serie_constante_positiva(self):
        lo, hi, p = ee.bootstrap_ci([0.25] * 200, semilla=42)
        self.assertAlmostEqual(lo, 0.25, places=9)
        self.assertAlmostEqual(hi, 0.25, places=9)
        self.assertAlmostEqual(p, 0.0, places=9)

    def test_serie_constante_negativa(self):
        lo, hi, p = ee.bootstrap_ci([-0.25] * 200, semilla=42)
        self.assertAlmostEqual(p, 1.0, places=9)


class TestDatosReales(unittest.TestCase):
    """Anti-look-ahead verificado sobre los datos reales del experimento."""

    def test_eventos_reales_entran_despues_de_la_senal(self):
        p_fund = os.path.join(ee.CACHE, "funding.jsonl")
        p_kl = os.path.join(ee.CACHE, "klines_5m.jsonl")
        if not (os.path.exists(p_fund) and os.path.exists(p_kl)):
            self.skipTest("cache no disponible")
        f = ee.cargar_funding()
        kl = ee.cargar_klines()
        # Dos hechos reales y honestos de los datos corregidos (comparacion
        # estricta): la variante canonica A24h NO llega al gate de 300 eventos
        # (de ahi su veredicto no_concluyente), y la variante B8h si lo supera.
        evs24 = ee.eventos_h1(f, kl, cooldown_h=24)
        evs8 = ee.eventos_h1(f, kl, cooldown_h=8)
        self.assertLess(len(evs24), 300, "A24h corregida queda bajo el gate")
        self.assertGreaterEqual(len(evs8), 300, "el gate exige >= 300 eventos")
        for e in evs8:
            self.assertGreater(e["t_ent"], e["t"], "entrada debe ser posterior")
            self.assertTrue(e["funding"] >= e["umbral_alto"]
                            or e["funding"] <= e["umbral_bajo"],
                            "la senal debe violar el umbral causal")
        for a, b in zip(evs8, evs8[1:]):
            self.assertGreaterEqual((b["t"] - a["t"]).total_seconds(), 8 * 3600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
