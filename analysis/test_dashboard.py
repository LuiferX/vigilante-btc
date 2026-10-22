"""Smoke test del dashboard: no ejecuta navegador ni red."""

import re
import unittest
from pathlib import Path


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.html = Path(__file__).resolve().parents[1].joinpath(
            "dashboard", "index.html"
        ).read_text(encoding="utf-8")

    def test_reads_decision_and_eval(self):
        self.assertIn("latest_decision.json", self.html)
        self.assertIn("eval.json", self.html)
        self.assertIn("validation.json", self.html)
        self.assertIn("DECISION_BASE", self.html)

    def test_has_no_order_buttons(self):
        text = self.html.lower()
        self.assertIn("sin ejecución", text)
        self.assertNotIn("place order", text)
        self.assertNotIn("ejecutar orden", text)

    def test_ids_are_unique(self):
        ids = re.findall(r'\bid="([^"]+)"', self.html)
        self.assertEqual(len(ids), len(set(ids)), "IDs duplicados en el dashboard")

    def test_motor_page_exists_for_pages(self):
        motor = Path(__file__).resolve().parents[1] / "docs" / "motor.html"
        self.assertTrue(motor.exists(), "falta docs/motor.html para GitHub Pages")
        self.assertIn("latest_decision.json", motor.read_text(encoding="utf-8"))

    def test_chart_is_height_constrained(self):
        self.assertIn("chart-wrap", self.html)
        self.assertIn("maintainAspectRatio: false", self.html)
        self.assertIn("animation: false", self.html)
        self.assertNotIn('height="220"', self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
