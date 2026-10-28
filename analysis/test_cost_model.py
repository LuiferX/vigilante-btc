#!/usr/bin/env python3
"""test_cost_model.py - el modelo de costos con cuentas hechas a mano."""
import unittest

import cost_model as cm

# Caso base de referencia: taker 0.05%/lado + slippage 0.02%/lado
# -> ida y vuelta 0.14% del precio.
C_PCT = 0.14


class TestCostModel(unittest.TestCase):
    def test_coste_ida_y_vuelta(self):
        self.assertAlmostEqual(cm.coste_rt_pct(0.05, 0.02), C_PCT, places=9)

    def test_prob_minima_cubre_costos(self):
        # marco 1% -> coste 0.14R -> p_min = (1+0.14)/2 = 0.57
        self.assertAlmostEqual(cm.prob_minima(0.14), 0.57, places=9)
        # sin costos, p_min = 0.5 exacto
        self.assertAlmostEqual(cm.prob_minima(0.0), 0.5, places=9)

    def test_ev_simetrico(self):
        # p=0.6, c=0.1 -> 1.2-1-0.1 = 0.1 R
        self.assertAlmostEqual(cm.ev_por_operacion(0.6, 0.1), 0.1, places=9)
        # p=0.55, c=0.1 -> 1.1-1-0.1 = 0.0 (justo en el breakeven)
        self.assertAlmostEqual(cm.ev_por_operacion(0.55, 0.1), 0.0, places=9)
        # p=0.5 (moneda), c=0 -> 0
        self.assertAlmostEqual(cm.ev_por_operacion(0.5, 0.0), 0.0, places=9)

    def test_edge_neto_bp(self):
        # EV=0.1R sobre marco 0.5% -> 0.1*0.5 = 0.05% = 5 bp
        self.assertAlmostEqual(cm.edge_neto_bp(0.6, 0.1, 0.5), 5.0, places=9)

    def test_prob_ajustada_resta_mitad_del_coste(self):
        # c=0.14 -> ajuste -0.07 de probabilidad
        self.assertAlmostEqual(cm.prob_ajustada(0.85, 0.14), 0.78, places=9)

    def test_slippage_modelo(self):
        # sin ATR conocido -> solo la base
        self.assertAlmostEqual(cm.slippage_pct(0.0, 0.02, 0.25), 0.02, places=9)
        # ATR 0.4% -> 0.02 + 0.25*0.4 = 0.12%
        self.assertAlmostEqual(cm.slippage_pct(0.4, 0.02, 0.25), 0.12, places=9)

    def test_tabla_breakeven_coherente(self):
        filas = cm.tabla_breakeven(marcos=(0.5, 1.0))
        # marco 0.5%: coste 0.14/0.5 = 0.28R -> p_min 0.64
        f0 = filas[0]
        self.assertAlmostEqual(f0["coste_en_R"], 0.28, places=9)
        self.assertAlmostEqual(f0["prob_minima"], 0.64, places=9)
        # colchon x2 exige mas
        self.assertGreater(f0["prob_minima_colchon"], f0["prob_minima"])
        # marco mayor -> coste en R menor -> p_min mas baja
        self.assertLess(filas[1]["prob_minima"], filas[0]["prob_minima"])

    def test_evaluar_senal_caso_real(self):
        # base real del bot: ~85% de aguante, marco 0.5%
        s = cm.evaluar_senal(0.85, 0.5, 0.05)
        # coste 0.14% -> 0.28R; EV = 2*0.85-1-0.28 = 0.42R
        self.assertAlmostEqual(s["coste_en_R"], 0.28, places=4)
        self.assertAlmostEqual(s["ev_R"], 0.42, places=4)
        # 0.42R * 0.5% = 0.21% = 21 bp
        self.assertAlmostEqual(s["edge_neto_bp"], 21.0, places=2)
        self.assertTrue(s["viable"])
        # justo por debajo del minimo (0.64) NO es viable: el breakeven manda
        self.assertFalse(cm.evaluar_senal(0.639, 0.5, 0.05)["viable"])
        # la tasa base pelada, sin skill del modelo, queda al borde del minimo:
        # con marco 0.5% el 85% apenas cubre. La skill es lo unico que pone
        # el EV del lado positivo de forma holgada.
        self.assertLessEqual(cm.evaluar_senal(0.85, 0.5, 0.05)["ev_R"], 0.43)

    def test_marco_invalido(self):
        with self.assertRaises(ValueError):
            cm.edge_neto_bp(0.6, 0.1, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
