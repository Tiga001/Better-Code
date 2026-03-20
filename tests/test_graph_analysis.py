from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from bettercode.graph_analysis import analyze_graph_structure
from bettercode.parser import ProjectAnalyzer


class GraphAnalysisTests(unittest.TestCase):
    def test_detects_cycles_and_isolated_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "a.py").write_text("import b\n", encoding="utf-8")
            (root / "b.py").write_text("import c\n", encoding="utf-8")
            (root / "c.py").write_text("import a\n", encoding="utf-8")
            (root / "user.py").write_text(
                textwrap.dedent(
                    """
                    import requests
                    import leaf
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "leaf.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "lonely.py").write_text("VALUE = 0\n", encoding="utf-8")

            graph = ProjectAnalyzer().analyze(root)
            insights = analyze_graph_structure(graph)

        self.assertEqual(
            insights.cycle_node_ids,
            {"file:a.py", "file:b.py", "file:c.py"},
        )
        self.assertEqual(
            insights.isolated_node_ids,
            {"file:lonely.py"},
        )
        self.assertEqual(insights.outgoing_node_ids["file:user.py"], ["external:requests", "file:leaf.py"])
        self.assertEqual(insights.incoming_node_ids["file:leaf.py"], ["file:user.py"])
        self.assertEqual(insights.incoming_node_ids["external:requests"], ["file:user.py"])
        self.assertEqual(insights.incoming_internal_counts["file:leaf.py"], 1)
        self.assertEqual(insights.outgoing_internal_counts["file:leaf.py"], 0)
        self.assertEqual(len(insights.cycle_edge_ids), 3)


if __name__ == "__main__":
    unittest.main()
