from __future__ import annotations

import unittest

from bettercode.models import GraphNode, NodeKind
from bettercode.ui.graph_view import _node_display_text, _path_hint, _wrap_label_lines


class GraphViewLabelTests(unittest.TestCase):
    def test_duplicate_generic_filename_gets_parent_hint(self) -> None:
        node = GraphNode(
            id="file:bettercode/ui/__init__.py",
            kind=NodeKind.PYTHON_FILE,
            label="__init__.py",
            path="bettercode/ui/__init__.py",
            module="bettercode.ui",
        )

        title_lines, subtitle = _node_display_text(node, {"__init__.py": 2})

        self.assertEqual(title_lines, ["__init__.py"])
        self.assertEqual(subtitle, "bettercode/ui")

    def test_long_snake_case_filename_wraps_into_two_lines(self) -> None:
        self.assertEqual(
            _wrap_label_lines("test_graph_analysis.py"),
            ["test_graph", "analysis.py"],
        )

    def test_path_hint_uses_project_root_for_top_level_file(self) -> None:
        self.assertEqual(_path_hint("app.py"), "project root")


if __name__ == "__main__":
    unittest.main()
