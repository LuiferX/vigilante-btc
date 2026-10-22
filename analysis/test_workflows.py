"""Tests de configuracion de workflows. No ejecuta Actions."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"


def read(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


class WorkflowTest(unittest.TestCase):
    def test_pipeline_has_the_15m_schedule(self):
        text = read("pipeline.yml")
        self.assertIn('cron: "*/15 * * * *"', text)
        self.assertIn("workflow_dispatch", text)
        self.assertIn("concurrency:", text)
        self.assertIn("group: data-write", text)

    def test_manual_workflows_do_not_duplicate_schedule(self):
        for name in (
            "collect.yml",
            "decision.yml",
            "health.yml",
            "backtest.yml",
            "validation.yml",
        ):
            with self.subTest(name=name):
                self.assertNotIn("schedule:", read(name))
                self.assertIn("workflow_dispatch", read(name))

    def test_writers_share_concurrency(self):
        for name in ("pipeline.yml", "collect.yml", "decision.yml", "validation.yml"):
            with self.subTest(name=name):
                text = read(name)
                self.assertIn("group: data-write", text)
                self.assertIn("contents: write", text)

    def test_no_pull_request_target(self):
        for path in WF.glob("*.yml"):
            with self.subTest(path=path.name):
                self.assertNotIn("pull_request_target", path.read_text(encoding="utf-8"))

    def test_pipeline_has_one_cron(self):
        text = read("pipeline.yml")
        crons = re.findall(r'cron:\s*["\']([^"\']+)["\']', text)
        self.assertEqual(crons, ["*/15 * * * *"])

    def test_dashboard_publishers_include_the_motor_page(self):
        for name in ("oyente.yml", "vigilante.yml"):
            with self.subTest(name=name):
                text = read(name)
                self.assertIn("dash_motor", text)
                self.assertIn("motor.html", text)

    def test_selfheal_runs_after_vigilante_and_shares_the_write_lock(self):
        text = read("selfheal.yml")
        self.assertIn("workflow_run:", text)
        self.assertIn("Vigilante BTC Cloud", text)
        self.assertIn("group: data-write", text)
        self.assertIn("collector/collector.py", text)
        self.assertIn("run_decision.py", text)

    def test_pipeline_and_selfheal_run_validation(self):
        for name in ("pipeline.yml", "decision.yml", "selfheal.yml", "backtest.yml"):
            with self.subTest(name=name):
                self.assertIn("analysis/validation.py", read(name))
        self.assertIn("validation.json", read("pipeline.yml"))
        self.assertIn("validation_history.jsonl", read("pipeline.yml"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
