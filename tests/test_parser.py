from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from bettercode.models import AgentTaskSuitability, CodeBlockKind, ImportKind, NodeKind
from bettercode.parser import ProjectAnalyzer


class ProjectAnalyzerTests(unittest.TestCase):
    def test_builds_file_level_dependency_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "pkg").mkdir()
            (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (root / "pkg" / "helpers.py").write_text(
                "import os\n\n\ndef normalize(value: str) -> str:\n    return value.strip() + os.sep\n",
                encoding="utf-8",
            )
            (root / "lonely.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "main.py").write_text(
                textwrap.dedent(
                    """
                    import pkg
                    import requests
                    import os
                    from pkg.helpers import normalize

                    def run() -> str:
                        return normalize(" ok ")

                    if __name__ == "__main__":
                        print(run())
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        node_kinds = {node.id: node.kind for node in graph.nodes}
        self.assertEqual(node_kinds["file:main.py"], NodeKind.PYTHON_FILE)
        self.assertEqual(node_kinds["file:pkg/__init__.py"], NodeKind.PYTHON_FILE)
        self.assertEqual(node_kinds["file:pkg/helpers.py"], NodeKind.LEAF_FILE)
        self.assertEqual(node_kinds["file:lonely.py"], NodeKind.PYTHON_FILE)
        self.assertEqual(node_kinds["external:requests"], NodeKind.EXTERNAL_PACKAGE)

        edges = {(edge.source, edge.target) for edge in graph.edges}
        self.assertIn(("file:main.py", "file:pkg/__init__.py"), edges)
        self.assertIn(("file:main.py", "file:pkg/helpers.py"), edges)
        self.assertIn(("file:main.py", "external:requests"), edges)

        detail = graph.file_details["file:main.py"]
        import_kinds = {record.module: record.kind for record in detail.imports}
        self.assertEqual(import_kinds["pkg"], ImportKind.INTERNAL)
        self.assertEqual(import_kinds["requests"], ImportKind.EXTERNAL)
        self.assertEqual(import_kinds["os"], ImportKind.STANDARD_LIBRARY)
        self.assertEqual(import_kinds["pkg.helpers.normalize"], ImportKind.INTERNAL)
        self.assertEqual(graph.project.python_files, 4)

    def test_absolute_from_imports_stay_absolute_inside_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_sample.py").write_text(
                textwrap.dedent(
                    """
                    from pathlib import Path
                    from core import VALUE
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:tests/test_sample.py"]
        import_kinds = {record.module: record.kind for record in detail.imports}
        self.assertEqual(import_kinds["pathlib.Path"], ImportKind.STANDARD_LIBRARY)
        self.assertEqual(import_kinds["core.VALUE"], ImportKind.INTERNAL)
        self.assertNotIn("external:tests", {node.id for node in graph.nodes})

    def test_extracts_file_internal_code_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    class Greeter:
                        def greet(self, name: str) -> str:
                            return self._normalize(name)

                        def _normalize(self, name: str) -> str:
                            return name.strip()

                    def run(value: str) -> str:
                        return Greeter().greet(value)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:service.py"]
        blocks = detail.code_blocks
        self.assertEqual(
            [(block.kind, block.name) for block in blocks],
            [
                (CodeBlockKind.CLASS, "Greeter"),
                (CodeBlockKind.METHOD, "greet"),
                (CodeBlockKind.METHOD, "_normalize"),
                (CodeBlockKind.FUNCTION, "run"),
            ],
        )
        self.assertIsNone(blocks[0].parent_id)
        self.assertEqual(blocks[1].parent_id, blocks[0].id)
        self.assertEqual(blocks[2].parent_id, blocks[0].id)
        self.assertIsNone(blocks[3].parent_id)
        self.assertEqual(blocks[0].line, 1)
        self.assertGreaterEqual(blocks[0].end_line, blocks[2].end_line)
        self.assertEqual(blocks[1].parameters, ["name: str"])
        self.assertEqual(blocks[1].return_summary, "str")
        self.assertEqual(blocks[3].agent_task_fit, AgentTaskSuitability.GOOD)
        self.assertEqual(blocks[2].agent_task_fit, AgentTaskSuitability.CAUTION)

        call_edges = {
            (
                next(block.name for block in blocks if block.id == call.source_id),
                next(block.name for block in blocks if block.id == call.target_id),
                call.expression,
            )
            for call in detail.code_block_calls
        }
        self.assertIn(("greet", "_normalize", "self._normalize"), call_edges)
        self.assertIn(("run", "Greeter", "Greeter"), call_edges)
        self.assertIn(("run", "greet", "Greeter().greet"), call_edges)

    def test_resolves_cross_file_code_block_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    class Formatter:
                        def normalize(self, value: str) -> str:
                            return value.strip()

                    def format_value(value: str) -> str:
                        return Formatter().normalize(value)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    from helper import Formatter, format_value

                    def run(raw: str) -> str:
                        return format_value(raw)

                    def run_method(raw: str) -> str:
                        formatter = Formatter()
                        return formatter.normalize(raw)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:service.py"]
        blocks_by_id = {block.id: block for block in detail.code_blocks}
        call_edges = {
            (
                blocks_by_id[call.source_id].name,
                call.target_node_id,
                call.target_id,
                call.expression,
                call.is_cross_file,
            )
            for call in detail.code_block_calls
        }
        helper_blocks = {block.name: block.id for block in graph.file_details["file:helper.py"].code_blocks}
        self.assertIn(
            ("run", "file:helper.py", helper_blocks["format_value"], "format_value", True),
            call_edges,
        )
        self.assertIn(
            ("run_method", "file:helper.py", helper_blocks["Formatter"], "Formatter", True),
            call_edges,
        )
        self.assertIn(
            ("run_method", "file:helper.py", helper_blocks["normalize"], "formatter.normalize", True),
            call_edges,
        )


if __name__ == "__main__":
    unittest.main()
