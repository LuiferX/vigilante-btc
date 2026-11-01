"""Tests de configuracion de workflows. No ejecuta Actions.

REARME 2026-11-01: los workflows de operacion (decision, backtest, selfheal,
vigilante/oyente como motor de alertas) se retiraron. Lo que se verifica aqui
es la config del sistema ANALITICO: recolector, archivo de microestructura,
tests y despliegue del informe.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"

RETIRADOS = ("decision.yml", "backtest.yml", "selfheal.yml", "health.yml",
             "pipeline.yml", "vigilante.yml", "validation.yml", "oos-refresh.yml",
             "wf-reentrenar.yml")
VIGENTES = ("collect.yml", "archivo.yml", "test.yml", "analysis-tests.yml",
            "lint.yml", "resumen.yml")


def read(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


class WorkflowTest(unittest.TestCase):
    def test_workflows_de_operacion_retirados(self):
        for name in RETIRADOS:
            with self.subTest(name=name):
                self.assertFalse((WF / name).exists(),
                                 f"{name} no debe existir tras el rearme")

    def test_workflows_vigentes_existen(self):
        for name in VIGENTES:
            with self.subTest(name=name):
                self.assertTrue((WF / name).exists(), f"{name} debe existir")

    def test_archivo_tiene_cron_diario(self):
        text = read("archivo.yml")
        self.assertIn("cron:", text)
        self.assertIn("workflow_dispatch", text)
        self.assertIn("--diario", text)

    def test_archivo_no_escribe_datos_de_operacion(self):
        text = read("archivo.yml")
        self.assertIn("analysis/archivo_micro.py", text)
        self.assertNotIn("run_decision.py", text)
        self.assertNotIn("paper", text)

    def test_colector_sigue_manual(self):
        text = read("collect.yml")
        self.assertIn("workflow_dispatch", text)
        self.assertIn("collector/collector.py", text)
        self.assertNotIn("schedule:", text)

    def test_ningun_workflow_usa_pull_request_target(self):
        for path in WF.glob("*.yml"):
            with self.subTest(path=path.name):
                self.assertNotIn("pull_request_target", path.read_text(encoding="utf-8"))

    def test_ningun_workflow_tiene_mas_de_un_cron_si_no_es_periodico(self):
        for path in WF.glob("*.yml"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                crons = re.findall(r'cron:\s*["\']([^"\']+)["\']', text)
                self.assertLessEqual(len(crons), 2, "mas de 2 cron es sospechoso")

    def test_tests_y_lint_corren_en_ci(self):
        self.assertIn("test_vigilante.py", read("test.yml"))
        self.assertIn("analysis/test_*.py", read("test.yml"))
        self.assertIn("ruff", read("lint.yml"))
        self.assertIn("test_vigilante", read("analysis-tests.yml") + read("test.yml"))
        # nadie debe ejecutar lo archivado (la capa de operar).
        # Se comprueba sobre las lineas de `run:`, no sobre comentarios.
        for path in WF.glob("*.yml"):
            with self.subTest(path=path.name):
                for linea in path.read_text(encoding="utf-8").split("\n"):
                    limpia = linea.split("#", 1)[0]
                    self.assertNotIn("paper_report.py", limpia)
                    self.assertNotIn("run_decision.py", limpia)
                    self.assertNotIn("run_loop.py", limpia)


if __name__ == "__main__":
    unittest.main(verbosity=2)
