"""Tests hermeticos de paper_report.py. No tocan red ni el estado real.

Ejecutar: python test_paper_report.py

Casos:
  1. estado sin operaciones (vacio) -> todo n/d, no rompe.
  2. caso sintetico de 5 operaciones conocidas -> win rate, R total y drawdown
     calculados A MANO sobre el papel.
  3. datos corruptos (basura en la lista, pnl no numerico, fechas invalidas) ->
     no rompe, descarta y declara.
  4. integracion: el workflow y el dashboard conocen el informe.
"""

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timezone

import paper_report as pr


def _op(dire, res, pnl, r, t):
    return {"dir": dire, "res": res, "pnl": pnl, "r": r, "t": t}


# caso sintetico: 5 operaciones, TODAS las cifras esperadas estan calculadas
# a mano en los asserts de mas abajo (ver caso_sintetico).
OPS_SINTETICAS = [
    _op("LONG", "TP", 2.00, 1.00, "2026-10-01T10:00:00+00:00"),
    _op("SHORT", "SL", -0.50, -1.00, "2026-10-02T11:00:00+00:00"),
    _op("LONG", "TP", 1.00, 0.50, "2026-10-08T09:00:00+00:00"),
    _op("SHORT", "TP", 0.30, 0.25, "2026-10-16T12:00:00+00:00"),
    _op("LONG", "SL", -1.30, -1.00, "2026-11-01T08:00:00+00:00"),
]

# A MANO:
#   PnL total   = 2.00 - 0.50 + 1.00 + 0.30 - 1.30        = 1.50
#   R total     = 1.00 - 1.00 + 0.50 + 0.25 - 1.00        = -0.25
#   R medio     = -0.25 / 5                               = -0.05
#   ganadas 3 / 5 -> win rate 60.0% (perdidas 2)
#   Sharpe: media -0.05; varianza ((1.05^2 + 0.95^2 + 0.55^2 + 0.30^2 + 0.95^2)/5)
#           = (1.1025 + 0.9025 + 0.3025 + 0.09 + 0.9025)/5 = 3.30/5 = 0.66
#           desvio = sqrt(0.66) = 0.81240 -> Sharpe = -0.05/0.81240 = -0.0615 -> -0.06
#   Curva de PnL acumulado: 2.00, 1.50, 2.50, 2.80, 1.50
#           max drawdown = 2.80 - 1.50 = 1.30 USDT
#   Banco: inicio 100 + 1.50 = 101.50; pico 102.50 -> drawdown banco
#          = (102.50 - 101.50)/102.50 = 0.98%
#   Por lado LONG: ops 1,3,5 -> PnL 2.00 + 1.00 - 1.30 = 1.70, R = 1.00+0.50-1.00 = 0.50,
#                  ganadas 2 de 3 -> 66.7%
#   Por lado SHORT: ops 2,4 -> PnL -0.50 + 0.30 = -0.20, R = -1.00+0.25 = -0.75,
#                  ganadas 1 de 2 -> 50.0%
#   Por cierre TP: 3 ops, PnL 3.30, R 1.75 | SL: 2 ops, PnL -1.80, R -2.00
#   Por mes: 2026-10 -> 4 ops, PnL 2.80 | 2026-11 -> 1 op, PnL -1.30
#   Por semana ISO: 2026-W40 (1 y 2 oct) 2 ops PnL 1.50 | W41 (8 oct) 1 op 1.00
#                   W42 (16 oct) 1 op 0.30 | W44 (1 nov) 1 op -1.30


class VacioTest(unittest.TestCase):
    def test_sin_operaciones_todo_nd(self):
        est = {"banco": 100.0, "banco_pico": 100.0, "paper_cerradas": []}
        rep = pr.construir_reporte(est, "local:estado.json")
        self.assertTrue(rep["sin_datos"])
        r = rep["resumen"]
        self.assertEqual(r["n"], 0)
        self.assertEqual(r["win_rate"], pr.ND)
        self.assertEqual(r["r_total"], pr.ND)
        self.assertEqual(r["r_medio"], pr.ND)
        self.assertEqual(r["pnl_total"], pr.ND)
        self.assertEqual(r["sharpe"], pr.ND)
        self.assertEqual(r["max_dd_curva_usdt"], pr.ND)
        self.assertEqual(r["max_dd_curva_pct"], pr.ND)
        # con banco == banco_pico el drawdown del banco es 0.0: es un dato, no n/d
        self.assertEqual(r["max_dd_banco_pct"], 0.0)
        self.assertEqual(r["max_dd_curva_usdt"], pr.ND)
        self.assertEqual(rep["por_semana"], {})
        self.assertEqual(rep["por_mes"], {})
        self.assertEqual(rep["por_lado"], {})
        self.assertEqual(rep["por_res"], {})
        self.assertTrue(any("Sin operaciones cerradas" in n for n in rep["notas"]))
        self.assertIn("no hay rendimiento que medir", rep["texto"])

    def test_sin_clave_paper_cerradas(self):
        rep = pr.construir_reporte({"banco": 100.0}, "local:x")
        self.assertTrue(rep["sin_datos"])
        self.assertEqual(rep["resumen"]["n"], 0)

    def test_sin_estado_no_rompe(self):
        rep = pr.construir_reporte(None, "local:x", "archivo inexistente")
        self.assertTrue(rep["sin_datos"])
        self.assertEqual(rep["resumen"]["n"], 0)
        self.assertTrue(any("No se pudo leer el estado" in n for n in rep["notas"]))


class CasoSinteticoTest(unittest.TestCase):
    def setUp(self):
        self.est = {
            "banco": 101.50,
            "banco_pico": 102.50,
            "paper_cerradas": list(OPS_SINTETICAS),
            "paper_abiertas": [{"dir": "SHORT", "entrada": 80000}],
        }
        self.rep = pr.construir_reporte(self.est, "local:sintetico")
        self.r = self.rep["resumen"]

    def test_conteo_y_win_rate(self):
        self.assertEqual(self.r["n"], 5)
        self.assertEqual(self.r["ganadas"], 3)
        self.assertEqual(self.r["perdidas"], 2)
        self.assertEqual(self.r["win_rate"], 60.0)

    def test_r_multiple(self):
        self.assertEqual(self.r["r_total"], -0.25)
        self.assertEqual(self.r["r_medio"], -0.05)
        self.assertEqual(self.r["r_mejor"], 1.0)
        self.assertEqual(self.r["r_peor"], -1.0)
        self.assertEqual(self.r["sharpe"], -0.06)
        self.assertEqual(self.r["sharpe_n"], 5)

    def test_pnl(self):
        self.assertEqual(self.r["pnl_total"], 1.5)
        self.assertEqual(self.r["pnl_medio"], 0.3)
        self.assertEqual(self.r["pnl_peor"], -1.3)
        # profit factor: ganado 3.30 / perdido 1.80 = 1.8333 -> 1.83
        self.assertEqual(self.r["profit_factor"], 1.83)

    def test_drawdown_banco_y_curva(self):
        # (102.50 - 101.50) / 102.50 = 0.9756% -> 0.98
        self.assertEqual(self.r["max_dd_banco_pct"], 0.98)
        # curva 2.00,1.50,2.50,2.80,1.50 -> pico 2.80 a valle 1.50 = 1.30
        self.assertEqual(self.r["max_dd_curva_usdt"], 1.3)
        self.assertEqual(self.r["curva_pnl"], [2.0, 1.5, 2.5, 2.8, 1.5])
        # banco anclado: inicio 100 -> equity 102.00,101.50,102.50,102.80,101.50
        # pico 102.80 a valle 101.50 = 1.30 -> 1.30/102.80 = 1.2647% -> 1.26
        self.assertEqual(self.r["max_dd_curva_pct"], 1.26)

    def test_por_periodo(self):
        mes = self.rep["por_mes"]
        self.assertEqual(sorted(mes), ["2026-10", "2026-11"])
        self.assertEqual(mes["2026-10"]["n"], 4)
        self.assertEqual(mes["2026-10"]["pnl_total"], 2.8)  # 2.00-0.50+1.00+0.30
        self.assertEqual(mes["2026-11"]["n"], 1)
        self.assertEqual(mes["2026-11"]["pnl_total"], -1.3)
        semana = self.rep["por_semana"]
        self.assertEqual(sorted(semana), ["2026-W40", "2026-W41", "2026-W42", "2026-W44"])
        self.assertEqual(semana["2026-W40"]["n"], 2)
        self.assertEqual(semana["2026-W40"]["pnl_total"], 1.5)
        self.assertEqual(semana["2026-W41"]["pnl_total"], 1.0)
        self.assertEqual(semana["2026-W42"]["pnl_total"], 0.3)
        self.assertEqual(semana["2026-W44"]["pnl_total"], -1.3)

    def test_por_lado_y_por_cierre(self):
        lado = self.rep["por_lado"]
        self.assertEqual(sorted(lado), ["LONG", "SHORT"])
        self.assertEqual(lado["LONG"]["n"], 3)
        self.assertEqual(lado["LONG"]["pnl_total"], 1.7)
        self.assertEqual(lado["LONG"]["r_total"], 0.5)
        self.assertEqual(lado["LONG"]["win_rate"], 66.7)
        self.assertEqual(lado["SHORT"]["n"], 2)
        self.assertEqual(lado["SHORT"]["pnl_total"], -0.2)
        self.assertEqual(lado["SHORT"]["r_total"], -0.75)
        self.assertEqual(lado["SHORT"]["win_rate"], 50.0)
        res = self.rep["por_res"]
        self.assertEqual(sorted(res), ["SL", "TP"])
        self.assertEqual(res["TP"]["n"], 3)
        self.assertEqual(res["TP"]["pnl_total"], 3.3)
        self.assertEqual(res["TP"]["r_total"], 1.75)
        self.assertEqual(res["SL"]["n"], 2)
        self.assertEqual(res["SL"]["pnl_total"], -1.8)
        self.assertEqual(res["SL"]["r_total"], -2.0)

    def test_honestidad_y_contexto(self):
        self.assertEqual(self.rep["abiertas"], 1)
        self.assertFalse(self.rep["sin_datos"])
        self.assertEqual(self.rep["meta"]["clave"], "paper_cerradas")
        self.assertTrue(any("Muestra chica (5" in n for n in self.rep["notas"]))
        self.assertIn("n/d = no dato", self.rep["texto"])
        self.assertIn("win rate 60.0%", self.rep["texto"])


class CorruptosTest(unittest.TestCase):
    def setUp(self):
        self.est = {
            "banco": "no-es-numero",
            "paper_cerradas": [
                "soy un texto",
                None,
                42,
                {"dir": "LONG", "res": "TP"},  # sin pnl ni r -> se descarta
                {"dir": "LONG", "res": "TP", "pnl": "1,50", "r": "0,75",
                 "t": "2026-10-05T10:00:00+00:00"},
                {"dir": None, "res": "SL", "pnl": -2.0, "r": -1.0,
                 "t": "no-es-una-fecha"},
                {"dir": "SHORT", "res": "SL", "pnl": "???", "r": -1.0,
                 "t": "2026-10-06T10:00:00+00:00"},
                {"dir": "SHORT", "res": "SL", "pnl": -3.0, "r": -1.0,
                 "t": "2026-10-06T10:00:00+00:00"},
                [],
            ],
        }
        self.rep = pr.construir_reporte(self.est, "local:corrupto")

    def test_no_rompe_y_descarta(self):
        # se queda con 4 operaciones utiles (texto/None/42/[]/sin datos -> fuera)
        self.assertEqual(self.rep["resumen"]["n"], 4)
        self.assertEqual(self.rep["meta"]["descartadas"], 5)
        self.assertTrue(self.rep["meta"]["sin_fecha"] >= 1)
        self.assertTrue(any("corruptas" in n for n in self.rep["notas"]))

    def test_numeros_en_texto_y_fecha_invalida(self):
        r = self.rep["resumen"]
        # pnl "1,50" -> 1.5 y r "0,75" -> 0.75 (coma decimal)
        self.assertEqual(r["pnl_total"], -3.5)  # 1.5 - 2.0 - 3.0
        self.assertEqual(r["r_total"], -2.25)  # 0.75 - 1.0 - 1.0 - 1.0
        self.assertEqual(r["ganadas"], 1)
        self.assertEqual(r["win_rate"], 25.0)
        # la operacion sin fecha valida no entra a por_semana/por_mes
        self.assertEqual(sum(v["n"] for v in self.rep["por_semana"].values()), 3)
        self.assertEqual(self.rep["por_mes"]["2026-10"]["n"], 3)

    def test_banco_no_numerico_es_nd(self):
        self.assertEqual(self.rep["resumen"]["banco"], pr.ND)
        self.assertEqual(self.rep["resumen"]["max_dd_banco_pct"], pr.ND)

    def test_json_ilegible_no_rompe(self):
        with tempfile.TemporaryDirectory() as td:
            ruta = os.path.join(td, "estado.json")
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write("{no esto no es json")
            estado, fuente, error = pr.leer_estado(ruta)
            self.assertIsNone(estado)
            self.assertIn("ilegible", error)
            rep = pr.construir_reporte(estado, fuente, error)
            self.assertTrue(rep["sin_datos"])
            self.assertEqual(rep["resumen"]["n"], 0)


class JournalTest(unittest.TestCase):
    def test_journal_sin_pnl_declara_nd(self):
        est = {
            "journal": [
                {"dir": "LONG", "res": "MANUAL", "r": 1.0, "t": "2026-10-01T10:00:00+00:00"},
                {"dir": "SHORT", "res": "MANUAL", "r": -1.0, "t": "2026-10-02T10:00:00+00:00"},
            ]
        }
        rep = pr.construir_reporte(est, "local:journal")
        r = rep["resumen"]
        self.assertEqual(r["n"], 2)
        self.assertEqual(r["r_total"], 0.0)
        self.assertEqual(r["pnl_total"], pr.ND)
        self.assertEqual(r["win_rate"], pr.ND)
        self.assertEqual(r["sharpe"], pr.ND)  # 2 datos: no opina
        self.assertTrue(any("no guarda PnL" in n for n in rep["notas"]))
        self.assertEqual(rep["fuente"]["origen_datos"], "journal")


class UtilidadesTest(unittest.TestCase):
    def test_sharpe_pide_5_datos(self):
        self.assertIsNone(pr.sharpe_por_op([1.0, 1.0, 1.0, 1.0]))
        self.assertIsNone(pr.sharpe_por_op([1.0, 1.0, 1.0, 1.0, 1.0]))  # varianza 0
        self.assertEqual(pr.sharpe_por_op([1, 0, 1, 0, 1]), 1.22)
        self.assertEqual(pr.sharpe_por_op([1, 0, 1, 0, 1, 0]), 1.0)
        self.assertIsNone(pr.sharpe_por_op([1, 1, 1, 1, 1]))  # varianza 0

    def test_drawdown_curva(self):
        self.assertEqual(pr.drawdown_curva([1.0, 2.0, 1.0, 3.0, 0.5])[0], 2.5)
        self.assertEqual(pr.drawdown_curva([1.0, 2.0, 3.0])[0], 0.0)
        self.assertIsNone(pr.drawdown_curva([]))

    def test_num_y_fecha(self):
        self.assertEqual(pr._num("1,5"), 1.5)
        self.assertIsNone(pr._num("abc"))
        self.assertIsNone(pr._num(True))
        self.assertEqual(pr._num(3), 3.0)
        self.assertIsNone(pr._fecha("no-es-fecha"))
        self.assertIsNone(pr._fecha(True))
        self.assertEqual(pr._fecha("2026-10-01T10:00:00Z").tzinfo, UTC)

    def test_claves_de_periodo(self):
        dt = datetime(2026, 10, 16, tzinfo=UTC)
        self.assertEqual(pr.clave_semana(dt), "2026-W42")
        self.assertEqual(pr.clave_mes(dt), "2026-10")

    def test_cli_escribe_json(self):
        with tempfile.TemporaryDirectory() as td:
            ruta = os.path.join(td, "sintetico.json")
            salida = os.path.join(td, "sub", "paper_summary.json")
            with open(ruta, "w", encoding="utf-8") as fh:
                json.dump({"banco": 101.5, "banco_pico": 102.5,
                           "paper_cerradas": list(OPS_SINTETICAS)}, fh)
            codigo = pr.main(["--estado", ruta, "--out-json", salida])
            self.assertEqual(codigo, 0)
            self.assertTrue(os.path.exists(salida))
            with open(salida, encoding="utf-8") as fh:
                dato = json.load(fh)
            self.assertEqual(dato["resumen"]["win_rate"], 60.0)
            self.assertEqual(dato["resumen"]["r_total"], -0.25)
            self.assertEqual(dato["resumen"]["max_dd_banco_pct"], 0.98)
            self.assertEqual(dato["nd"], "n/d")
            self.assertIn("PAPEL XLX", dato["texto"])

    def test_cli_sin_estado_local_intenta_remoto(self):
        # no hay red en el test: solo verifica que no lanza y devuelve informe vacio
        with tempfile.TemporaryDirectory() as td:
            ruta = os.path.join(td, "no-existe.json")
            codigo = pr.main(["--estado", ruta, "--url", "http://127.0.0.1:1/nada.json",
                              "--timeout", "1"])
            self.assertEqual(codigo, 0)


class IntegracionTest(unittest.TestCase):
    def test_workflow_y_dashboard_conocen_el_informe(self):
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        wf = os.path.join(raiz, ".github", "workflows", "oyente.yml")
        with open(wf, encoding="utf-8") as fh:
            texto = fh.read()
        self.assertIn("paper_report.py", texto)
        self.assertIn("paper_summary.json", texto)

        monitor = os.path.join(raiz, "docs", "monitor.html")
        with open(monitor, encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn("paper_summary.json", html)
        # patrón de carga con fallback (varias rutas candidatas)
        self.assertIn("primeroOK", html)
        self.assertIn("cache:\"no-store\"", html)
        # sin botones de orden: el panel es solo lectura
        self.assertNotIn("place order", html.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
