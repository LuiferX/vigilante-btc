#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_expr_sesiones.py - el experimento de sesiones no puede hacer trampa.

Lo delicado aqui es el LOOK-AHEAD DE SESION: el rango asiatico solo puede
usarse con la sesion Asia CERRADA, y la entrada debe ser el open de la vela
SIGUIENTE a la que confirma el barrido. Los tests lo comprueban con velas
sinteticas donde la trampa se detecta.

Uso: python -m unittest analysis.test_expr_sesiones
"""

from __future__ import annotations

import datetime
import os
import sys
import unittest

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    from analysis import expr_sesiones as es
except ImportError:
    sys.path.insert(0, AQUI)
    import expr_sesiones as es

# un dia concreto: 2026-03-02 (lunes)
BASE = datetime.datetime(2026, 3, 2, tzinfo=UTC)


def vela(minutos, o, h, low, c):
    return {"t": BASE + datetime.timedelta(minutes=minutos), "o": o, "h": h, "l": low, "c": c}


def dia_asiatico(high=31000.0, low=29000.0):
    """Velas de una sesion Asia completa (00:00-08:00) con rango conocido."""
    velas = []
    for i in range(96):  # 96 velas de 5m = 8h
        m = i * 5
        precio = (high + low) / 2
        velas.append(vela(m, precio, precio + 1, precio - 1, precio))
    # fuerza el maximo y el minimo del rango en dos velas concretas
    velas[10] = vela(50, high, high, high, high)
    velas[80] = vela(400, low, low, low, low)
    return velas


class TestSesiones(unittest.TestCase):
    def test_buckets_cubren_el_dia(self):
        self.assertEqual(es.ASIA, (0.0, 8.0))
        self.assertEqual(es.LONDRES, (8.0, 13.5))

    def test_hora_y_sesion(self):
        v = vela(60, 1, 1, 1, 1)  # 01:00 UTC
        self.assertAlmostEqual(es.hora(v), 1.0)
        self.assertTrue(es.en_sesion(v, es.ASIA))
        self.assertFalse(es.en_sesion(v, es.LONDRES))

    def test_sesion_londres_en_su_ventana(self):
        v = vela(9 * 60, 1, 1, 1, 1)  # 09:00 UTC
        self.assertTrue(es.en_sesion(v, es.LONDRES))
        self.assertFalse(es.en_sesion(v, es.ASIA))

    def test_solape_no_es_londres(self):
        v = vela(14 * 60, 1, 1, 1, 1)  # 14:00 UTC
        self.assertFalse(es.en_sesion(v, es.LONDRES))


class TestRangoAsiatico(unittest.TestCase):
    def test_rango_correcto(self):
        kl = dia_asiatico()
        rangs = es.rangos_asiaticos(kl)
        self.assertEqual(len(rangs), 1)
        self.assertEqual(rangs[0]["high"], 31000.0)
        self.assertEqual(rangs[0]["low"], 29000.0)

    def test_dia_incompleto_se_descarta(self):
        """Un dia con pocas velas de Asia no debe usarse (evita sesiones
        partidas por huecos o por el inicio/fin de la historia)."""
        kl = dia_asiatico()[:30]  # solo 30 velas de Asia
        self.assertEqual(es.rangos_asiaticos(kl), [])

    def test_fin_asia_es_la_ultima_vela_asiatica(self):
        kl = dia_asiatico()
        r = es.rangos_asiaticos(kl)[0]
        # 96 velas x 5min -> la ultima empieza a los 475 min
        self.assertEqual(r["fin_asia"].hour, 7)
        self.assertEqual(r["fin_asia"].minute, 55)


class TestBarrido(unittest.TestCase):
    def _kl_con_barrido(self, lado: str):
        """Un dia completo: Asia + Londres que barrea el alto (o el bajo)."""
        kl = dia_asiatico()
        m_ini = 96 * 5  # 08:00 UTC
        for i in range(66):  # Londres 08:00-13:30
            m = m_ini + i * 5
            if i == 10:  # la vela del barrido
                if lado == "alto":
                    kl.append(vela(m, 30950, 31050, 30900, 30920))  # mecha sobre 31000
                else:
                    kl.append(vela(m, 29050, 29080, 28950, 29020))  # mecha bajo 29000
            elif i == 12:  # confirmacion dentro
                if lado == "alto":
                    kl.append(vela(m, 30920, 30940, 30900, 30910))
                else:
                    kl.append(vela(m, 29010, 29040, 29000, 29030))
            else:
                p = 30000.0
                kl.append(vela(m, p, p + 5, p - 5, p))
        return kl

    def test_barrido_alto_se_detecta(self):
        kl = self._kl_con_barrido("alto")
        evs = es.eventos_barrido(kl, es.rangos_asiaticos(kl))
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["lado"], "alto")
        self.assertEqual(evs[0]["high_asia"], 31000.0)

    def test_barrido_bajo_se_detecta(self):
        kl = self._kl_con_barrido("bajo")
        evs = es.eventos_barrido(kl, es.rangos_asiaticos(kl))
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["lado"], "bajo")

    def test_sin_barrido_no_hay_evento(self):
        kl = dia_asiatico()
        m_ini = 96 * 5
        for i in range(66):  # Londres sin barrido
            p = 30000.0
            kl.append(vela(m_ini + i * 5, p, p + 5, p - 5, p))
        self.assertEqual(es.eventos_barrido(kl, es.rangos_asiaticos(kl)), [])

    def test_entrada_es_la_vela_siguiente_a_la_confirmacion(self):
        kl = self._kl_con_barrido("alto")
        evs = es.eventos_barrido(kl, es.rangos_asiaticos(kl))[0]
        r = es.resolver_barrido(kl, "reversion", 12)(dict(evs, barras=12))
        self.assertIsNotNone(r)
        i_conf = evs["idx_confirma"]
        # la entrada es el open de la vela i_conf+1
        self.assertEqual(r["t"], kl[i_conf + 1]["t"])
        self.assertGreater(r["t"], kl[i_conf]["t"])

    def test_direccion_reversion_vs_control(self):
        kl = self._kl_con_barrido("alto")  # barrido del ALTO
        evs = es.eventos_barrido(kl, es.rangos_asiaticos(kl))[0]
        rev = es.resolver_barrido(kl, "reversion", 12)(dict(evs, barras=12))
        ctl = es.resolver_barrido(kl, "control", 12)(dict(evs, barras=12))
        self.assertFalse(rev["largo"], "barrido alto -> reversion = CORTO")
        self.assertTrue(ctl["largo"], "control = continuacion = LARGO")

        kl_b = self._kl_con_barrido("bajo")
        evs_b = es.eventos_barrido(kl_b, es.rangos_asiaticos(kl_b))[0]
        rev_b = es.resolver_barrido(kl_b, "reversion", 12)(dict(evs_b, barras=12))
        self.assertTrue(rev_b["largo"], "barrido bajo -> reversion = LARGO")


class TestPerfil(unittest.TestCase):
    def test_perfil_suma_100_los_extremos(self):
        """Las cuentas de maximo/minimo por sesion deben sumar ~100%."""
        kl = dia_asiatico()
        m_ini = 96 * 5
        for i in range(66):
            p = 30000.0
            kl.append(vela(m_ini + i * 5, p, p + 5, p - 5, p))
        # un dia mas
        base2 = BASE + datetime.timedelta(days=1)
        for i in range(96):
            kl.append(
                {
                    "t": base2 + datetime.timedelta(minutes=5 * i),
                    "o": 30000.0,
                    "h": 30001.0,
                    "l": 29999.0,
                    "c": 30000.0,
                }
            )
        perfil = es.perfil_sesiones(kl)
        tot_h = sum(d["hace_max_del_dia_pct"] for d in perfil.values())
        tot_l = sum(d["hace_min_del_dia_pct"] for d in perfil.values())
        self.assertAlmostEqual(tot_h, 100.0, delta=1.0)
        self.assertAlmostEqual(tot_l, 100.0, delta=1.0)

    def test_perfil_no_rompe_con_pocas_velas(self):
        self.assertIsInstance(es.perfil_sesiones([]), dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
