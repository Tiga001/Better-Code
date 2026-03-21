from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from bettercode.parser import ProjectAnalyzer
from bettercode.ui.code_block_dialog import CodeBlockDialog


class CodeBlockDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_builds_block_tree_and_source_excerpt(self) -> None:
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
            node = next(candidate for candidate in graph.nodes if candidate.id == "file:service.py")
            detail = graph.file_details["file:service.py"]
            dialog = CodeBlockDialog(project_root=root, graph=graph, node=node, detail=detail)

            self.assertEqual(dialog._tree.topLevelItemCount(), 2)
            self.assertEqual(dialog._tree.topLevelItem(0).text(0), "class Greeter")
            self.assertIn("class Greeter:", dialog._preview.toPlainText())
            dialog._tree.setCurrentItem(dialog._tree.topLevelItem(1))

            self.assertEqual(dialog._fit_chip.text(), "Agent fit: good")
            self.assertEqual(dialog._parameters.item(0).text(), "value: str")
            self.assertEqual(dialog._returns.text(), "Returns: str")
            outgoing_items = [
                dialog._outgoing_calls.item(index).text()
                for index in range(dialog._outgoing_calls.count())
            ]
            self.assertTrue(any("Greeter().greet" in item for item in outgoing_items))

    def test_renders_cross_file_call_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    def format_value(value: str) -> str:
                        return value.strip()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    from helper import format_value

                    def run(raw: str) -> str:
                        return format_value(raw)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            graph = ProjectAnalyzer().analyze(root)
            node = next(candidate for candidate in graph.nodes if candidate.id == "file:service.py")
            detail = graph.file_details["file:service.py"]
            dialog = CodeBlockDialog(project_root=root, graph=graph, node=node, detail=detail)
            dialog._tree.setCurrentItem(dialog._tree.topLevelItem(0))

            outgoing_items = [
                dialog._outgoing_calls.item(index).text()
                for index in range(dialog._outgoing_calls.count())
            ]
            self.assertTrue(any("[helper.py]" in item and "cross-file" in item for item in outgoing_items))

    def test_renders_symbol_usages_for_selected_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    class Formatter:
                        def normalize(self, value: str) -> str:
                            return value.strip()

                    def decorate(fn):
                        return fn
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    from helper import Formatter, decorate

                    class Derived(Formatter):
                        pass

                    @decorate
                    def run(value: Formatter) -> Formatter:
                        formatter = Formatter()
                        return formatter
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            graph = ProjectAnalyzer().analyze(root)
            node = next(candidate for candidate in graph.nodes if candidate.id == "file:helper.py")
            detail = graph.file_details["file:helper.py"]
            dialog = CodeBlockDialog(project_root=root, graph=graph, node=node, detail=detail)
            dialog._tree.setCurrentItem(dialog._tree.topLevelItem(0))

            usage_items = [
                dialog._usages.item(index).text()
                for index in range(dialog._usages.count())
            ]

            self.assertTrue(any("import" in item and "[service.py]" in item for item in usage_items))
            self.assertTrue(any("inheritance" in item and "[service.py]" in item for item in usage_items))
            self.assertTrue(any("type annotation" in item and "[service.py]" in item for item in usage_items))
            self.assertTrue(any("instantiation" in item and "[service.py]" in item for item in usage_items))
            self.assertIn("Usages: 4", dialog._stats.text())

    def test_switches_between_dialog_context_panels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    def run(value: str) -> str:
                        return value.strip()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            graph = ProjectAnalyzer().analyze(root)
            node = next(candidate for candidate in graph.nodes if candidate.id == "file:service.py")
            detail = graph.file_details["file:service.py"]
            dialog = CodeBlockDialog(project_root=root, graph=graph, node=node, detail=detail)

            self.assertEqual(dialog._inspector_stack.currentIndex(), 0)
            self.assertTrue(dialog._call_links_button.isChecked())
            dialog._usages_button.click()
            self.assertEqual(dialog._inspector_stack.currentIndex(), 1)
            self.assertTrue(dialog._usages_button.isChecked())
            dialog._agent_notes_button.click()
            self.assertEqual(dialog._inspector_stack.currentIndex(), 2)
            self.assertTrue(dialog._agent_notes_button.isChecked())


if __name__ == "__main__":
    unittest.main()
