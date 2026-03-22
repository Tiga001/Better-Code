from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from bettercode.batch_optimize_executor import BatchRunItemStatus, BatchRunReport, BatchRunStatus
from bettercode.optimize_executor import OptimizationStatus, ValidationStatus
from bettercode.parser import ProjectAnalyzer
from bettercode.task_graph import build_task_batch, build_task_execution_plan, build_task_graph
from bettercode.models import TaskMode
from bettercode.optimization_history import OptimizationHistoryEntry
from bettercode.ui.task_detail_panel import TaskDetailPanel


class TaskDetailPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_task_detail_panel_shows_localized_reasons_and_source_preview(self) -> None:
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
            graph = ProjectAnalyzer().analyze(root)
            task_graph = build_task_graph(graph)
            optimize_plan = build_task_execution_plan(graph, mode=TaskMode.OPTIMIZE)
            translate_plan = build_task_execution_plan(graph, mode=TaskMode.TRANSLATE)
            optimize_batch = build_task_batch(graph, mode=TaskMode.OPTIMIZE)
            translate_batch = build_task_batch(graph, mode=TaskMode.TRANSLATE)
            unit = next(candidate for candidate in task_graph.units if candidate.label.startswith("normalize("))

            panel = TaskDetailPanel(language="en")
            self.addCleanup(panel.close)
            panel.set_selection(
                project_graph=graph,
                task_graph=task_graph,
                optimize_plan=optimize_plan,
                translate_plan=translate_plan,
                optimize_batch=optimize_batch,
                translate_batch=translate_batch,
                optimization_history_by_unit={},
                batch_run_report=None,
                batch_run_status_by_unit={},
                batch_run_current_unit_id=None,
                unit=unit,
            )

            self.assertIn("top-level function is a standalone task unit", panel._reasons.item(0).text().lower())
            preview = panel._source_preview.toPlainText()
            self.assertIn("helper.py:1-2", preview)
            self.assertIn("def normalize(value: str) -> str:", preview)

            panel.set_language("zh")

            self.assertIn("顶层函数是一个独立任务单元", panel._reasons.item(0).text())
            self.assertEqual(panel._source_preview_title.text(), "代码预览")

    def test_task_detail_panel_switches_assignment_controls_by_view_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                "def normalize(value: str) -> str:\n    return value.strip()\n",
                encoding="utf-8",
            )
            graph = ProjectAnalyzer().analyze(root)
            task_graph = build_task_graph(graph)
            optimize_plan = build_task_execution_plan(graph, mode=TaskMode.OPTIMIZE)
            translate_plan = build_task_execution_plan(graph, mode=TaskMode.TRANSLATE)
            optimize_batch = build_task_batch(graph, mode=TaskMode.OPTIMIZE)
            translate_batch = build_task_batch(graph, mode=TaskMode.TRANSLATE)
            unit = task_graph.units[0]

            panel = TaskDetailPanel(language="zh")
            self.addCleanup(panel.close)
            panel.set_selection(
                project_graph=graph,
                task_graph=task_graph,
                optimize_plan=optimize_plan,
                translate_plan=translate_plan,
                optimize_batch=optimize_batch,
                translate_batch=translate_batch,
                optimization_history_by_unit={},
                batch_run_report=None,
                batch_run_status_by_unit={},
                batch_run_current_unit_id=None,
                unit=unit,
            )

            panel.set_view_mode("tasks")
            self.assertTrue(panel._execution_card.isHidden())
            self.assertFalse(panel._assignment_card.isHidden())
            self.assertFalse(panel._unit_assignment_row.isHidden())
            self.assertTrue(panel._phase_assignment_row.isHidden())
            self.assertEqual(panel._assign_optimize_button.text(), "指派优化任务")

            panel.set_view_mode("batches")
            self.assertFalse(panel._execution_card.isHidden())
            self.assertTrue(panel._assignment_card.isHidden())
            self.assertTrue(panel._unit_assignment_row.isHidden())
            self.assertFalse(panel._phase_assignment_row.isHidden())

    def test_task_detail_panel_shows_optimization_history_and_localizes_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                "def normalize(value: str) -> str:\n    return value.strip()\n",
                encoding="utf-8",
            )
            graph = ProjectAnalyzer().analyze(root)
            task_graph = build_task_graph(graph)
            optimize_plan = build_task_execution_plan(graph, mode=TaskMode.OPTIMIZE)
            translate_plan = build_task_execution_plan(graph, mode=TaskMode.TRANSLATE)
            optimize_batch = build_task_batch(graph, mode=TaskMode.OPTIMIZE)
            translate_batch = build_task_batch(graph, mode=TaskMode.TRANSLATE)
            unit = task_graph.units[0]
            history = {
                unit.id: [
                    OptimizationHistoryEntry(
                        task_id=f"{unit.id}:optimize",
                        unit_id=unit.id,
                        output_dir=str(root / "generated" / "optimizations" / "run_1"),
                        summary="Trimmed repeated logic.",
                        status=OptimizationStatus.OPTIMIZED,
                        failure_category=None,
                        validation_status=ValidationStatus.PASSED,
                        created_at_ms=1_711_111_111_000,
                        changed_files=1,
                        has_apply_result=True,
                        has_rollback_result=False,
                    )
                ]
            }

            panel = TaskDetailPanel(language="en")
            self.addCleanup(panel.close)
            panel.set_selection(
                project_graph=graph,
                task_graph=task_graph,
                optimize_plan=optimize_plan,
                translate_plan=translate_plan,
                optimize_batch=optimize_batch,
                translate_batch=translate_batch,
                optimization_history_by_unit=history,
                batch_run_report=None,
                batch_run_status_by_unit={},
                batch_run_current_unit_id=None,
                unit=unit,
            )

            self.assertIn("Latest optimization: optimized", panel._optimization_status.text())
            self.assertIn("applied", panel._optimization_history.item(0).text())
            self.assertTrue(panel._open_history_button.isEnabled())

            panel.set_language("zh")

            self.assertEqual(panel._optimization_history_title.text(), "优化历史")
            self.assertIn("最近一次优化：optimized", panel._optimization_status.text())
            self.assertIn("已应用", panel._optimization_history.item(0).text())

    def test_task_detail_panel_shows_batch_execution_monitor_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                "def normalize(value: str) -> str:\n    return value.strip()\n",
                encoding="utf-8",
            )
            graph = ProjectAnalyzer().analyze(root)
            task_graph = build_task_graph(graph)
            optimize_plan = build_task_execution_plan(graph, mode=TaskMode.OPTIMIZE)
            translate_plan = build_task_execution_plan(graph, mode=TaskMode.TRANSLATE)
            optimize_batch = build_task_batch(graph, mode=TaskMode.OPTIMIZE)
            translate_batch = build_task_batch(graph, mode=TaskMode.TRANSLATE)
            unit = task_graph.units[0]
            report = BatchRunReport(
                id="run_1",
                mode=TaskMode.OPTIMIZE,
                project_root=str(root),
                scope="phase",
                selected_phase=0,
                status=BatchRunStatus.RUNNING,
                started_at_ms=1,
                finished_at_ms=None,
                output_dir=str(root / "generated" / "batch_runs" / "run_1"),
                items=[],
            )

            panel = TaskDetailPanel(language="zh")
            self.addCleanup(panel.close)
            panel.set_view_mode("batches")
            panel.set_selection(
                project_graph=graph,
                task_graph=task_graph,
                optimize_plan=optimize_plan,
                translate_plan=translate_plan,
                optimize_batch=optimize_batch,
                translate_batch=translate_batch,
                optimization_history_by_unit={},
                batch_run_report=report,
                batch_run_status_by_unit={unit.id: BatchRunItemStatus.RUNNING},
                batch_run_current_unit_id=unit.id,
                unit=unit,
            )

            self.assertEqual(panel._subtitle.text(), "批次执行监控")
            self.assertEqual(panel._execution_title.text(), "执行监控")
            self.assertIn("批次执行：运行中", panel._execution_batch_status.text())
            self.assertIn("当前任务状态：运行中", panel._execution_unit_status.text())
            self.assertIn(unit.label, panel._execution_current_task.text())


if __name__ == "__main__":
    unittest.main()
