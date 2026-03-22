from __future__ import annotations

import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bettercode.models import (
    AgentTaskSuitability,
    TaskBatch,
    TaskBatchItem,
    TaskBatchPhase,
    TaskGraph,
    TaskGraphUnit,
    TaskMode,
    TaskUnitKind,
)
from bettercode.batch_optimize_executor import BatchRunItemStatus
from bettercode.ui.task_batch_view import TaskBatchView


class TaskBatchViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_batch_view_renders_phase_bands_and_wraps_after_twelve_items(self) -> None:
        units = [
            TaskGraphUnit(
                id=f"task:{index}",
                kind=TaskUnitKind.FUNCTION,
                label=f"task_{index}() [file_{index}.py]",
                block_ids=[f"block:{index}"],
                root_block_ids=[f"block:{index}"],
                node_ids=[f"file:file_{index}.py"],
                depends_on=[],
                depended_on_by=[],
                depth=0 if index < 13 else 1,
                reasons=[],
                ready_to_run=index < 13,
            )
            for index in range(14)
        ]
        optimize_items = [
            TaskBatchItem(
                id=f"task:{index}:optimize",
                unit_id=f"task:{index}",
                mode=TaskMode.OPTIMIZE,
                label=units[index].label,
                phase_index=0 if index < 13 else 1,
                order_index=index + 1,
                target_block_ids=[f"block:{index}"],
                target_node_ids=[f"file:file_{index}.py"],
                blocking_dependencies=[],
                context_dependencies=[],
                suitability=AgentTaskSuitability.GOOD,
                risk=AgentTaskSuitability.GOOD,
                ready_to_run=index < 13,
            )
            for index in range(14)
        ]
        optimize_batch = TaskBatch(
            mode=TaskMode.OPTIMIZE,
            items=optimize_items,
            phases=[
                TaskBatchPhase(index=0, item_ids=[f"task:{index}:optimize" for index in range(13)]),
                TaskBatchPhase(index=1, item_ids=["task:13:optimize"]),
            ],
        )
        translate_batch = TaskBatch(
            mode=TaskMode.TRANSLATE,
            items=[],
            phases=[],
        )
        view = TaskBatchView(language="zh")
        self.addCleanup(view.close)
        view.resize(1480, 780)
        view.set_batches(
            task_graph=TaskGraph(units=units, edges=[]),
            optimize_batch=optimize_batch,
            translate_batch=translate_batch,
        )

        row_y_values = sorted({round(item.pos().y(), 2) for unit_id, item in view._canvas._cards.items() if unit_id != "task:13"})
        self.assertGreater(len(row_y_values), 1)
        self.assertEqual(len(view._canvas._phase_bands), 2)
        self.assertLess(view._canvas._cards["task:0"].pos().y(), view._canvas._cards["task:13"].pos().y())

    def test_batch_view_switches_between_optimize_and_translate_batches(self) -> None:
        task_graph = TaskGraph(
            units=[
                TaskGraphUnit(
                    id="task:opt",
                    kind=TaskUnitKind.FUNCTION,
                    label="opt() [helper.py]",
                    block_ids=["block:opt"],
                    root_block_ids=["block:opt"],
                    node_ids=["file:helper.py"],
                    depends_on=[],
                    depended_on_by=[],
                    depth=0,
                    reasons=[],
                    ready_to_run=True,
                ),
                TaskGraphUnit(
                    id="task:tr",
                    kind=TaskUnitKind.CLASS_GROUP,
                    label="translate() [helper.py]",
                    block_ids=["block:tr"],
                    root_block_ids=["block:tr"],
                    node_ids=["file:helper.py"],
                    depends_on=[],
                    depended_on_by=[],
                    depth=0,
                    reasons=[],
                    ready_to_run=True,
                ),
            ],
            edges=[],
        )
        optimize_batch = TaskBatch(
            mode=TaskMode.OPTIMIZE,
            items=[
                TaskBatchItem(
                    id="task:opt:optimize",
                    unit_id="task:opt",
                    mode=TaskMode.OPTIMIZE,
                    label="opt() [helper.py]",
                    phase_index=0,
                    order_index=1,
                    target_block_ids=["block:opt"],
                    target_node_ids=["file:helper.py"],
                    blocking_dependencies=[],
                    context_dependencies=[],
                    suitability=AgentTaskSuitability.GOOD,
                    risk=AgentTaskSuitability.GOOD,
                    ready_to_run=True,
                )
            ],
            phases=[TaskBatchPhase(index=0, item_ids=["task:opt:optimize"])],
        )
        translate_batch = TaskBatch(
            mode=TaskMode.TRANSLATE,
            items=[
                TaskBatchItem(
                    id="task:tr:translate",
                    unit_id="task:tr",
                    mode=TaskMode.TRANSLATE,
                    label="translate() [helper.py]",
                    phase_index=0,
                    order_index=1,
                    target_block_ids=["block:tr"],
                    target_node_ids=["file:helper.py"],
                    blocking_dependencies=[],
                    context_dependencies=[],
                    suitability=AgentTaskSuitability.CAUTION,
                    risk=AgentTaskSuitability.CAUTION,
                    ready_to_run=True,
                )
            ],
            phases=[TaskBatchPhase(index=0, item_ids=["task:tr:translate"])],
        )
        view = TaskBatchView(language="zh")
        self.addCleanup(view.close)
        view.set_batches(task_graph=task_graph, optimize_batch=optimize_batch, translate_batch=translate_batch)

        self.assertIn("task:opt", view._canvas._cards)
        self.assertNotIn("task:tr", view._canvas._cards)

        view._set_mode(TaskMode.TRANSLATE)

        self.assertIn("task:tr", view._canvas._cards)
        self.assertNotIn("task:opt", view._canvas._cards)

    def test_batch_selection_emits_on_release_not_press(self) -> None:
        task_graph = TaskGraph(
            units=[
                TaskGraphUnit(
                    id="task:opt",
                    kind=TaskUnitKind.FUNCTION,
                    label="opt() [helper.py]",
                    block_ids=["block:opt"],
                    root_block_ids=["block:opt"],
                    node_ids=["file:helper.py"],
                    depends_on=[],
                    depended_on_by=[],
                    depth=0,
                    reasons=[],
                    ready_to_run=True,
                )
            ],
            edges=[],
        )
        optimize_batch = TaskBatch(
            mode=TaskMode.OPTIMIZE,
            items=[
                TaskBatchItem(
                    id="task:opt:optimize",
                    unit_id="task:opt",
                    mode=TaskMode.OPTIMIZE,
                    label="opt() [helper.py]",
                    phase_index=0,
                    order_index=1,
                    target_block_ids=["block:opt"],
                    target_node_ids=["file:helper.py"],
                    blocking_dependencies=[],
                    context_dependencies=[],
                    suitability=AgentTaskSuitability.GOOD,
                    risk=AgentTaskSuitability.GOOD,
                    ready_to_run=True,
                )
            ],
            phases=[TaskBatchPhase(index=0, item_ids=["task:opt:optimize"])],
        )
        view = TaskBatchView(language="zh")
        self.addCleanup(view.close)
        view.resize(1280, 760)
        view.show()
        view.set_batches(task_graph=task_graph, optimize_batch=optimize_batch, translate_batch=None)
        QApplication.processEvents()
        hits: list[str] = []
        view.unit_selected.connect(hits.append)
        center = view._canvas.mapFromScene(view._canvas._cards["task:opt"].scenePos())

        QTest.mousePress(view._canvas.viewport(), Qt.LeftButton, Qt.NoModifier, center)
        self.assertEqual(hits, [])

        QTest.mouseRelease(view._canvas.viewport(), Qt.LeftButton, Qt.NoModifier, center)
        self.assertEqual(hits, ["task:opt"])

    def test_batch_view_updates_execution_state_and_enables_controls(self) -> None:
        task_graph = TaskGraph(
            units=[
                TaskGraphUnit(
                    id="task:opt",
                    kind=TaskUnitKind.FUNCTION,
                    label="opt() [helper.py]",
                    block_ids=["block:opt"],
                    root_block_ids=["block:opt"],
                    node_ids=["file:helper.py"],
                    depends_on=[],
                    depended_on_by=[],
                    depth=0,
                    reasons=[],
                    ready_to_run=True,
                )
            ],
            edges=[],
        )
        optimize_batch = TaskBatch(
            mode=TaskMode.OPTIMIZE,
            items=[
                TaskBatchItem(
                    id="task:opt:optimize",
                    unit_id="task:opt",
                    mode=TaskMode.OPTIMIZE,
                    label="opt() [helper.py]",
                    phase_index=0,
                    order_index=1,
                    target_block_ids=["block:opt"],
                    target_node_ids=["file:helper.py"],
                    blocking_dependencies=[],
                    context_dependencies=[],
                    suitability=AgentTaskSuitability.GOOD,
                    risk=AgentTaskSuitability.GOOD,
                    ready_to_run=True,
                )
            ],
            phases=[TaskBatchPhase(index=0, item_ids=["task:opt:optimize"])],
        )
        view = TaskBatchView(language="zh")
        self.addCleanup(view.close)
        view.set_batches(task_graph=task_graph, optimize_batch=optimize_batch, translate_batch=None)
        view.select_unit("task:opt")

        self.assertTrue(view._run_phase_button.isEnabled())
        self.assertTrue(view._run_batch_button.isEnabled())

        view.set_execution_state(
            status_by_unit={"task:opt": BatchRunItemStatus.RUNNING},
            status_text="running",
            is_running=True,
        )

        self.assertEqual(view._canvas._cards["task:opt"]._execution_status, BatchRunItemStatus.RUNNING)
        self.assertFalse(view._run_phase_button.isEnabled())
        self.assertTrue(view._stop_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
