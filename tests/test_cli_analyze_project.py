from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from typer.testing import CliRunner

from bettercode.cli.main import app


class AnalyzeProjectCliTests(unittest.TestCase):
    def test_analyze_project_cli_prints_json(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    def normalize(value: str) -> str:
                        return value.strip()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "app.py").write_text(
                textwrap.dedent(
                    """
                    from helper import normalize

                    def main(raw: str) -> str:
                        return normalize(raw)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(app, ["analyze-project", str(root), "--compact"])

        self.assertEqual(result.exit_code, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertIn("dependency_graph", payload)
        self.assertIn("task_graph", payload)
