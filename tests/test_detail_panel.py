from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from bettercode.graph_analysis import analyze_graph_structure
from bettercode.parser import ProjectAnalyzer
from bettercode.ui.detail_panel import DetailPanel


class DetailPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_renders_relationships_structure_and_syntax_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    class Helper:
                        pass

                    def normalize(value: str) -> str:
                        return value.strip()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "main.py").write_text(
                textwrap.dedent(
                    """
                    import requests
                    from helper import normalize

                    def run() -> str:
                        return normalize(" ok ")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

            graph = ProjectAnalyzer().analyze(root)
            insights = analyze_graph_structure(graph)

        panel = DetailPanel()

        panel.set_selection(graph, insights, next(node for node in graph.nodes if node.id == "file:main.py"))
        self.assertEqual(panel._syntax.text(), "Syntax: OK")
        self.assertEqual(
            [panel._dependencies.item(index).text() for index in range(panel._dependencies.count())],
            ["requests [External package]", "helper.py [Dependency leaf]"],
        )
        self.assertEqual(
            [panel._functions.item(index).text() for index in range(panel._functions.count())],
            ["run (L4)"],
        )

        panel.set_selection(graph, insights, next(node for node in graph.nodes if node.id == "file:helper.py"))
        self.assertEqual(
            [panel._dependents.item(index).text() for index in range(panel._dependents.count())],
            ["main.py [Top-level script]"],
        )
        self.assertEqual(
            [panel._classes.item(index).text() for index in range(panel._classes.count())],
            ["Helper (L1)"],
        )
        self.assertEqual(
            [panel._functions.item(index).text() for index in range(panel._functions.count())],
            ["normalize (L4)"],
        )

        panel.set_selection(graph, insights, next(node for node in graph.nodes if node.id == "file:broken.py"))
        self.assertIn("Syntax Error:", panel._syntax.text())


if __name__ == "__main__":
    unittest.main()
