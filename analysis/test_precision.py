#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_precision.py - el aviso de nivel no puede volver a inflarse.

Contexto: el mensaje decia "NIVEL DEFENDIDO" con "aguante estimado 85 %". El
operador se quejo con razon: 85 % es la TASA BASE (83,9% medido sobre 11.049
muestras del replay, por construccion del target `hold_4h_0.5pct`), no un
hallazgo. Estos tests fijan el mensaje honesto.

Uso: python -m unittest analysis.test_precision
"""

from __future__ import annotations

import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)

import vigilante.precision as pr  # noqa: E402

NIV = {
    "nivel": 84280.0,
    "lado": "resistencia",
    "prob": 0.86,
    "calidad": 8.5,
    "toques": 4,
    "cerca": 0.12,
    "confluencia": 3,
}


class TestMensajeHonesto(unittest.TestCase):
    def setUp(self):
        self.msg = pr.texto_alerta_precision(NIV, 84180.0).lower()

    def test_no_dice_defendido(self):
        """La palabra era una afirmacion que el dato no sostiene."""
        self.assertNotIn("defendido", self.msg)

    def test_dice_nivel_activo(self):
        self.assertIn("nivel activo", self.msg)

    def test_cita_la_base(self):
        """Sin la base, un 85% parece un hallazgo cuando es el punto de partida."""
        self.assertIn("base sin modelo", self.msg)
        self.assertIn("84%", self.msg)

    def test_dice_que_el_modelo_aporta_poco(self):
        self.assertIn("el modelo suma", self.msg)

    def test_dice_que_aguantar_no_es_moverse(self):
        self.assertIn("aguantar no es moverse", self.msg)
        self.assertIn("0,45 %", self.msg)

    def test_dice_que_no_es_orden(self):
        self.assertIn("no es orden", self.msg)

    def test_mantiene_la_advertencia_de_invalidacion(self):
        self.assertIn("cierre 4h", self.msg)

    def test_no_hay_plan_ni_objetivo(self):
        """Nada que suene a accion. 'ni entrada' esta permitido porque aparece
        NEGADO ('no es orden ni entrada'), que es justo lo que se quiere."""
        for palabra in (
            "objetivo de precio",
            "stop loss",
            "take profit",
            "plan 2r",
            "r:r",
            "apalancamiento",
            "tamaño",
        ):
            self.assertNotIn(palabra, self.msg, f"el mensaje no debe decir '{palabra}'")
        self.assertIn("no es orden ni entrada", self.msg)


class TestBaseDeclarada(unittest.TestCase):
    def test_base_es_la_medida_real(self):
        """0.839 = tasa base medida sobre las 11.049 muestras, no un numero
        decorativo. Si alguien la cambia sin medir, este test lo ve."""
        self.assertAlmostEqual(pr.PRECISION_BASE_AGUANTE, 0.839, places=3)

    def test_probabilidad_del_ejemplo_es_creible(self):
        self.assertGreaterEqual(NIV["prob"], pr.PRECISION_BASE_AGUANTE)


class TestNivelPrecision(unittest.TestCase):
    def test_sin_motor_no_hay_aviso(self):
        self.assertIsNone(pr.nivel_precision({}, 84180.0))
        self.assertIsNone(pr.nivel_precision({}, 0))

    def test_nivel_roto_no_califica(self):
        motor = {
            "levels": [
                {
                    "hold_prob": 0.95,
                    "quality": 9.0,
                    "touches_6h": 5,
                    "center": 84280.0,
                    "break_confirmed": True,
                    "role": "resistencia",
                }
            ],
            "decision": {"action": "algo"},
            "_edad_min": 1,
        }
        self.assertIsNone(
            pr.nivel_precision(motor, 84180.0), "un nivel roto no puede avisarse como activo"
        )

    def test_probabilidad_baja_no_califica(self):
        motor = {
            "levels": [
                {
                    "hold_prob": 0.50,
                    "quality": 9.0,
                    "touches_6h": 5,
                    "center": 84280.0,
                    "role": "resistencia",
                }
            ],
            "decision": {"action": "algo"},
            "_edad_min": 1,
        }
        self.assertIsNone(pr.nivel_precision(motor, 84180.0))

    def test_datos_viejos_no_califican(self):
        motor = {
            "levels": [
                {
                    "hold_prob": 0.95,
                    "quality": 9.0,
                    "touches_6h": 5,
                    "center": 84280.0,
                    "role": "resistencia",
                }
            ],
            "decision": {"action": "algo"},
            "_edad_min": 999,
        }
        self.assertIsNone(pr.nivel_precision(motor, 84180.0))

    def test_nivel_valido_califica(self):
        motor = {
            "levels": [
                {
                    "hold_prob": 0.95,
                    "quality": 9.0,
                    "touches_6h": 5,
                    "center": 84280.0,
                    "role": "resistencia",
                }
            ],
            "decision": {"action": "algo"},
            "_edad_min": 1,
        }
        r = pr.nivel_precision(motor, 84180.0)
        self.assertIsNotNone(r)
        self.assertEqual(r["nivel"], 84280.0)
        self.assertAlmostEqual(r["prob"], 0.95, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
