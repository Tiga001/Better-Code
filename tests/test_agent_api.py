from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from bettercode.agent_api import analyze_project_for_agent


class AgentApiTests(unittest.TestCase):
    def test_analyze_project_for_agent_returns_four_structures_and_issues(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "pkg").mkdir()
            (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (root / "pkg" / "helper.py").write_text(
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
                    from pkg.helper import normalize
                    from MissingModule import MissingThing

                    def main(raw: str) -> str:
                        return normalize(raw)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

            result = analyze_project_for_agent(root)

        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["analysis_mode"], "static")
        self.assertEqual(result["project_root"], str(root.resolve()))
        self.assertIn("dependency_graph", result)
        self.assertIn("subsystem_graph", result)
        self.assertIn("task_graph", result)
        self.assertIn("batch_view", result)
        self.assertIn("issues", result)

        dependency_graph = result["dependency_graph"]
        self.assertIn("file_details", dependency_graph)
        self.assertIn("app.py", dependency_graph["file_details"])
        self.assertEqual(
            dependency_graph["file_details"]["pkg/helper.py"]["node_kind"],
            "leaf_file",
        )
        self.assertTrue(
            any(issue["path"] == "broken.py" for issue in result["issues"]["syntax_errors"])
        )
        self.assertTrue(
            any(issue["module"] == "MissingModule.MissingThing" for issue in result["issues"]["unresolved_imports"])
        )
        self.assertIn("optimize", result["batch_view"])
        self.assertIn("translate", result["batch_view"])
        self.assertIn("plans", result["task_graph"])
        json.dumps(result, ensure_ascii=False)

    def test_subsystem_and_task_outputs_are_agent_oriented(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "base.py").write_text(
                "class Base:\n    pass\n",
                encoding="utf-8",
            )
            (root / "worker.py").write_text(
                textwrap.dedent(
                    """
                    from base import Base

                    class Worker(Base):
                        def run(self, value: str) -> str:
                            return value.strip()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "entry.py").write_text(
                textwrap.dedent(
                    """
                    from worker import Worker

                    worker = Worker()
                    print(worker.run(" ok "))
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = analyze_project_for_agent(root)

        subsystem = result["subsystem_graph"]["subsystems"][0]
        self.assertIn("member_nodes", subsystem)
        self.assertIn("member_edges", subsystem)
        self.assertIn("entry_node_ids", subsystem)
        self.assertIn("leaf_node_ids", subsystem)

        task_edges = result["task_graph"]["graph"]["edges"]
        self.assertTrue(any("inheritance" in edge["dependency_kinds"] for edge in task_edges))
        optimize_batch = result["batch_view"]["optimize"]
        self.assertIn("phases", optimize_batch)
        self.assertTrue(optimize_batch["phases"])
