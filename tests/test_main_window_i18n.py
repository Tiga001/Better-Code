from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch
import json

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
            self.assertEqual(window._model_config_button.text(), "API 配置")
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

    def test_main_window_can_open_and_save_model_config(self) -> None:
        window = MainWindow()
        self.addCleanup(window.close)

        with (
            patch("bettercode.ui.main_window.load_model_config") as load_mock,
            patch("bettercode.ui.main_window.save_model_config") as save_mock,
            patch("bettercode.ui.main_window.ModelConfigDialog") as dialog_class,
        ):
            dialog_instance = dialog_class.return_value
            dialog_instance.exec.return_value = 1
            load_mock.return_value = object()
            saved_config = object()
            dialog_instance.model_config.return_value = saved_config

            window._open_model_config_dialog()

        load_mock.assert_called_once()
        dialog_class.assert_called_once()
        save_mock.assert_called_once_with(saved_config)

    def test_switching_to_task_mode_shows_task_panel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text("def normalize(value: str) -> str:\n    return value.strip()\n", encoding="utf-8")
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
            first_task_unit = window._task_graph.units[0]
            window._set_graph_mode("tasks")
            window._handle_task_unit_selected(first_task_unit.id)

            self.assertEqual(window._canvas_stack.currentWidget(), window._task_graph_view)
            self.assertEqual(window._detail_stack.currentWidget(), window._task_detail_panel)
            self.assertEqual(window._task_detail_panel._title.text(), first_task_unit.label)
            self.assertFalse(window._search_input.isEnabled())
            self.assertTrue(window._neighbor_filter.isEnabled())

    def test_task_mode_can_export_task_unit_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            export_path = root / "task_package.json"
            (root / "helper.py").write_text("def normalize(value: str) -> str:\n    return value.strip()\n", encoding="utf-8")
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
            unit_id = window._task_graph.units[0].id

            with (
                patch(
                    "bettercode.ui.main_window.QFileDialog.getSaveFileName",
                    return_value=(str(export_path), "JSON Files (*.json)"),
                ),
                patch("bettercode.ui.main_window.QMessageBox.information") as information_mock,
            ):
                window._export_task_unit_package(unit_id, "optimize")

            exported = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(exported["item"]["mode"], "optimize")
            self.assertEqual(exported["item"]["unit_id"], unit_id)
            self.assertIn("source_snippets", exported)
            information_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
