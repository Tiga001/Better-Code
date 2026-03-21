from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from bettercode.ui.main_window import MainWindow


class MainWindowI18nTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_switching_language_updates_main_window_and_detail_panel(self) -> None:
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
            (root / "main.py").write_text(
                textwrap.dedent(
                    """
                    from helper import normalize

                    def run() -> str:
                        return normalize(" ok ")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window._load_project(root)
            window._handle_node_selected("file:main.py")

            zh_index = window._language_selector.findData("zh")
            window._language_selector.setCurrentIndex(zh_index)

            self.assertEqual(window._language_label.text(), "语言")
            self.assertEqual(window._import_button.text(), "导入项目")
            self.assertEqual(window._graph_mode_buttons["dependency"].text(), "依赖图")
            self.assertEqual(window._graph_mode_buttons["subsystems"].text(), "子系统")
            self.assertEqual(window._search_input.placeholderText(), "搜索文件、路径或模块...")
            self.assertEqual(window._detail_panel._syntax.text(), "语法：正常")
            self.assertEqual(window._detail_panel._dependency_surface_title.text(), "依赖关系")

    def test_loading_project_does_not_auto_select_any_node(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "main.py").write_text(
                textwrap.dedent(
                    """
                    from helper import VALUE
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window._load_project(root)

            self.assertIsNone(window._selected_node_id)
            self.assertIsNone(window._graph_view._selected_node_id)
            self.assertEqual(window._detail_panel._title.text(), "节点详情")

    def test_focus_filter_does_not_replace_selected_center_node(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "main.py").write_text(
                textwrap.dedent(
                    """
                    import requests
                    from helper import VALUE
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window._load_project(root)
            window._handle_node_selected("file:main.py")

            external_index = window._focus_filter.findData("external")
            window._focus_filter.setCurrentIndex(external_index)

            self.assertEqual(window._selected_node_id, "file:main.py")
            self.assertEqual(window._graph_view._selected_node_id, "file:main.py")
            self.assertEqual(window._detail_panel._title.text(), "main.py")

    def test_switching_to_subsystem_mode_keeps_selection_and_disables_search_focus_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "main.py").write_text(
                textwrap.dedent(
                    """
                    from helper import VALUE
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window._load_project(root)
            window._handle_node_selected("file:main.py")
            window._set_graph_mode("subsystems")

            self.assertEqual(window._canvas_stack.currentWidget(), window._subsystem_view)
            self.assertEqual(window._detail_panel._title.text(), "main.py")
            self.assertFalse(window._search_input.isEnabled())
            self.assertFalse(window._focus_filter.isEnabled())
            self.assertTrue(window._neighbor_filter.isEnabled())
            self.assertFalse(window._next_match_button.isEnabled())
            self.assertTrue(window._reset_view_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
