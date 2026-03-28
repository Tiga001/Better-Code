from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from bettercode.agent_api import analyze_project_for_agent as wrapped_analyze
from bettercode_agent_api import analyze_project_for_agent


class StandaloneAgentApiTests(unittest.TestCase):
    def test_standalone_package_matches_bettercode_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                "def normalize(value: str) -> str:\n    return value.strip()\n",
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

            direct = analyze_project_for_agent(root)
            wrapped = wrapped_analyze(root)

        self.assertEqual(direct["project_root"], wrapped["project_root"])
        self.assertEqual(direct["dependency_graph"]["nodes"], wrapped["dependency_graph"]["nodes"])
        self.assertEqual(direct["task_graph"]["graph"]["units"], wrapped["task_graph"]["graph"]["units"])

    def test_python_m_bettercode_agent_api_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "main.py").write_text("VALUE = 1\n", encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, "-m", "bettercode_agent_api", str(root), "--compact"],
                check=True,
                capture_output=True,
                text=True,
            )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["project_root"], str(root.resolve()))
