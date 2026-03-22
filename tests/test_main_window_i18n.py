from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch
import json

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from bettercode.model_config_store import load_model_config
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
            self.assertEqual(window._export_image_button.text(), "导出图片")
            self.assertEqual(window._graph_mode_buttons["dependency"].text(), "依赖图")
            self.assertEqual(window._graph_mode_buttons["subsystems"].text(), "子系统")
            self.assertEqual(window._graph_mode_buttons["batches"].text(), "批次视图")
            self.assertEqual(window._search_input.placeholderText(), "搜索文件、路径或模块...")
            self.assertEqual(window._detail_panel._syntax.text(), "语法：正常")
            self.assertEqual(window._detail_panel._dependency_surface_title.text(), "依赖关系")

    def test_can_export_all_four_canvas_modes_as_images(self) -> None:
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
            window.resize(1480, 920)
            window._load_project(root)

            export_targets = {
                "dependency": root / "dependency.png",
                "subsystems": root / "subsystems.png",
                "tasks": root / "tasks.png",
                "batches": root / "batches.png",
            }

            for mode, export_path in export_targets.items():
                window._set_graph_mode(mode)
                with (
                    patch(
                        "bettercode.ui.main_window.QFileDialog.getSaveFileName",
                        return_value=(str(export_path), "Image Files (*.png)"),
                    ),
                    patch("bettercode.ui.main_window.QMessageBox.information") as information_mock,
                ):
                    window._export_current_canvas_image()

                self.assertTrue(export_path.is_file(), mode)
                self.assertGreater(export_path.stat().st_size, 0, mode)
                information_mock.assert_called_once()

    def test_export_canvas_image_can_save_svg(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            export_path = root / "dependency.svg"
            (root / "helper.py").write_text(
                "def normalize(value: str) -> str:\n    return value.strip()\n",
                encoding="utf-8",
            )
            (root / "main.py").write_text(
                "from helper import normalize\n\n"
                "def run() -> str:\n"
                "    return normalize(' ok ')\n",
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window.resize(1480, 920)
            window._load_project(root)

            with (
                patch(
                    "bettercode.ui.main_window.QFileDialog.getSaveFileName",
                    return_value=(str(export_path), "SVG Files (*.svg)"),
                ),
                patch("bettercode.ui.main_window.QMessageBox.information") as information_mock,
            ):
                window._export_current_canvas_image()

            self.assertTrue(export_path.is_file())
            exported = export_path.read_text(encoding="utf-8")
            self.assertIn("<svg", exported)
            information_mock.assert_called_once()

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
            self.assertTrue(window._search_input.isEnabled())
            self.assertTrue(window._focus_filter.isEnabled())
            self.assertTrue(window._neighbor_filter.isEnabled())
            self.assertTrue(window._next_match_button.isEnabled() is False)
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
            self.assertTrue(window._search_input.isEnabled())
            self.assertTrue(window._focus_filter.isEnabled())
            self.assertTrue(window._neighbor_filter.isEnabled())
            self.assertFalse(window._legend_items["legend.task_function"].isHidden())
            self.assertFalse(window._legend_items["legend.task_class_group"].isHidden())
            self.assertFalse(window._legend_items["legend.task_edge_strong"].isHidden())
            self.assertFalse(window._legend_items["legend.task_edge_inheritance"].isHidden())
            self.assertFalse(window._legend_items["legend.task_edge_context"].isHidden())
            self.assertTrue(window._legend_items["legend.python_file"].isHidden())
            self.assertTrue(window._legend_items["legend.leaf_file"].isHidden())
            self.assertIn("优化阶段：", window._task_detail_panel._phase_summary.text())
            self.assertFalse(window._task_detail_panel._assignment_card.isHidden())

    def test_switching_to_batch_mode_shows_phase_view_and_batch_monitor(self) -> None:
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
            window._set_graph_mode("batches")
            window._handle_task_unit_selected(first_task_unit.id)

            self.assertEqual(window._canvas_stack.currentWidget(), window._task_batch_view)
            self.assertEqual(window._detail_stack.currentWidget(), window._batch_monitor_panel)
            self.assertEqual(window._batch_monitor_panel._title.text(), "批次监控")
            self.assertTrue(window._search_input.isEnabled())
            self.assertTrue(window._focus_filter.isEnabled())
            self.assertFalse(window._neighbor_filter.isEnabled())
            self.assertFalse(window._next_match_button.isEnabled())
            self.assertTrue(window._reset_view_button.isEnabled())
            self.assertFalse(window._legend_items["legend.task_function"].isHidden())
            self.assertTrue(window._legend_items["legend.python_file"].isHidden())
            self.assertIn("任务数：", window._batch_monitor_panel._summary.text())

    def test_task_modes_support_search_and_filter_by_underlying_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                "def normalize(value: str) -> str:\n    return value.strip()\n",
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

            window._set_graph_mode("tasks")
            window._search_input.setText("helper.py")
            self.assertTrue(any(match.startswith("task_unit:") for match in window._search_matches))
            self.assertIsNotNone(window._selected_task_unit_id)

            function_filter_index = window._focus_filter.findData("task_function")
            window._focus_filter.setCurrentIndex(function_filter_index)
            self.assertEqual(window._focus_filter.currentData(), "task_function")

            window._set_graph_mode("batches")
            window._search_input.setText("main.py")
            self.assertTrue(any(match.startswith("task_unit:") for match in window._search_matches))

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

    def test_task_mode_can_export_task_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            export_path = root / "optimize.task_batch.json"
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

            with (
                patch(
                    "bettercode.ui.main_window.QFileDialog.getSaveFileName",
                    return_value=(str(export_path), "JSON Files (*.json)"),
                ),
                patch("bettercode.ui.main_window.QMessageBox.information") as information_mock,
            ):
                window._export_task_batch("optimize")

            exported = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(exported["mode"], "optimize")
            self.assertIn("phases", exported)
            self.assertIn("items", exported)
            information_mock.assert_called_once()

    def test_task_graph_optimize_action_opens_review_dialog(self) -> None:
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
            window._set_graph_mode("tasks")
            unit = window._task_graph.units[0]
            window._handle_task_unit_selected(unit.id)

            fake_result = type(
                "FakeOptimizationResult",
                (),
                {
                    "status": type("Status", (), {"value": "optimized"})(),
                    "summary": "ok",
                    "validation_notes": [],
                    "suggested_tests": [],
                    "changed_files": [],
                    "original_files": [],
                    "output_dir": str(root / "generated" / "optimizations" / "unit"),
                    "diff_path": str(root / "generated" / "optimizations" / "unit" / "optimization.patch"),
                    "validation_report": type("Validation", (), {"status": type("Status", (), {"value": "passed"})()})(),
                },
            )()
            diff_path = Path(fake_result.diff_path)
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff_path.write_text("--- a.py\n+++ a.py\n", encoding="utf-8")

            with (
                patch.object(window, "_resolve_model_config", return_value=load_model_config()),
                patch("bettercode.ui.main_window.execute_optimization", return_value=fake_result) as execute_mock,
                patch("bettercode.ui.main_window.OptimizationReviewDialog") as dialog_mock,
            ):
                window._task_detail_panel._assign_optimize_button.click()

            execute_mock.assert_called_once()
            dialog_mock.assert_called_once()

    def test_batch_view_actions_export_only_current_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            export_path = root / "phase_batch.json"
            (root / "leaf.py").write_text(
                "def normalize(value: str) -> str:\n    return value.strip()\n",
                encoding="utf-8",
            )
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    from leaf import normalize

                    def format_value(value: str) -> str:
                        return normalize(value).upper()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "main.py").write_text(
                textwrap.dedent(
                    """
                    from helper import format_value

                    def run() -> str:
                        return format_value(" ok ")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window._load_project(root)
            window._set_graph_mode("batches")
            target_unit = next(unit for unit in window._task_graph.units if unit.depth == 1)
            window._handle_task_unit_selected(target_unit.id)

            with (
                patch(
                    "bettercode.ui.main_window.QFileDialog.getSaveFileName",
                    return_value=(str(export_path), "JSON Files (*.json)"),
                ),
                patch("bettercode.ui.main_window.QMessageBox.information") as information_mock,
            ):
                window._handle_task_phase_assignment(target_unit.id, "optimize")

            exported = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(exported["mode"], "optimize")
            self.assertEqual(len(exported["phases"]), 1)
            self.assertEqual(exported["phases"][0]["index"], 1)
            self.assertTrue(all(item["phase_index"] == 1 for item in exported["items"]))
            information_mock.assert_called_once()

    def test_task_graph_translate_action_still_exports_task_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            export_path = root / "translate_task.json"
            (root / "service.py").write_text(
                "def run(value: str) -> str:\n    return value.strip()\n",
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window._load_project(root)
            window._set_graph_mode("tasks")
            unit = window._task_graph.units[0]
            window._handle_task_unit_selected(unit.id)

            with (
                patch(
                    "bettercode.ui.main_window.QFileDialog.getSaveFileName",
                    return_value=(str(export_path), "JSON Files (*.json)"),
                ),
                patch("bettercode.ui.main_window.QMessageBox.information") as information_mock,
            ):
                window._task_detail_panel._assign_translate_button.click()

            exported = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(exported["item"]["mode"], "translate")
            self.assertEqual(exported["item"]["unit_id"], unit.id)
            information_mock.assert_called_once()

    def test_batch_view_run_batch_executes_items_and_updates_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "leaf.py").write_text(
                "def normalize(value: str) -> str:\n    return value.strip()\n",
                encoding="utf-8",
            )
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    from leaf import normalize

                    def format_value(value: str) -> str:
                        return normalize(value).upper()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            fake_result = type(
                "FakeOptimizationResult",
                (),
                {
                    "status": type("Status", (), {"value": "optimized"})(),
                    "summary": "ok",
                    "validation_notes": [],
                    "suggested_tests": [],
                    "changed_files": [],
                    "original_files": [],
                    "output_dir": str(root / "generated" / "optimizations" / "unit"),
                    "diff_path": str(root / "generated" / "optimizations" / "unit" / "optimization.patch"),
                    "validation_report": type("Validation", (), {"status": type("Status", (), {"value": "passed"})()})(),
                    "failure_category": None,
                },
            )()

            window = MainWindow()
            self.addCleanup(window.close)
            window._load_project(root)
            window._set_graph_mode("batches")
            first_unit = next(unit for unit in window._task_graph.units if unit.depth == 0)
            window._handle_task_unit_selected(first_unit.id)

            with (
                patch.object(window, "_resolve_model_config", return_value=load_model_config()),
                patch("bettercode.ui.main_window.execute_optimization", return_value=fake_result) as execute_mock,
                patch("bettercode.ui.main_window.BatchRunReportDialog.exec", return_value=0) as report_exec_mock,
            ):
                window._task_batch_view._run_batch_button.click()
                for _ in range(40):
                    QTest.qWait(50)
                    if window._batch_run_thread is None and window._batch_run_report is None:
                        break

            self.assertEqual(execute_mock.call_count, len(window._optimize_batch.items))
            self.assertTrue(report_exec_mock.called)
            self.assertTrue(all(status.value == "passed" for status in window._batch_run_status_by_unit.values()))
            batch_run_root = root / "generated" / "batch_runs"
            report_files = list(batch_run_root.glob("*/batch_run_report.json"))
            self.assertTrue(report_files)


if __name__ == "__main__":
    unittest.main()
