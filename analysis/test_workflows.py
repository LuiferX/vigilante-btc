"""Tests de configuracion de workflows. No ejecuta Actions."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"


def read(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


class WorkflowTest(unittest.TestCase):
    def test_pipeline_has_the_hourly_schedule(self):
        text = read("pipeline.yml")
        self.assertIn('cron: "17 * * * *"', text)
        self.assertIn("workflow_dispatch", text)
        self.assertIn("concurrency:", text)
        self.assertIn("group: data-write", text)

    def test_manual_workflows_do_not_duplicate_schedule(self):
        for name in ("collect.yml", "decision.yml", "health.yml", "backtest.yml"):
            with self.subTest(name=name):
                self.assertNotIn("schedule:", read(name))
                self.assertIn("workflow_dispatch", read(name))

    def test_writers_share_concurrency(self):
        for name in ("pipeline.yml", "collect.yml", "decision.yml"):
            with self.subTest(name=name):
                text = read(name)
                self.assertIn("group: data-write", text)
                self.assertIn("contents: write", text)

    def test_no_pull_request_target(self):
        for path in WF.glob("*.yml"):
            with self.subTest(path=path.name):
                self.assertNotIn("pull_request_target", path.read_text(encoding="utf-8"))

    def test_only_one_hourly_pipeline_cron(self):
        crons = []
        for path in WF.glob("*.yml"):
            crons.extend(re.findall(r'cron:\s*["\']([^"\']+)["\']', path.read_text(encoding="utf-8")))
        self.assertEqual(crons.count("17 * * * *"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
