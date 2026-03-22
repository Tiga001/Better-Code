from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bettercode.models import (
    TaskGraph,
    TaskGraphEdge,
    TaskGraphUnit,
    TaskUnitKind,
)
from bettercode.batch_optimize_executor import BatchRunItemStatus
from bettercode.ui.task_graph_view import TaskGraphView, TaskNodeItem


class TaskGraphViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_task_graph_view_renders_depths_top_to_bottom_with_rows_by_depth(self) -> None:
        task_graph = TaskGraph(
            units=[
                TaskGraphUnit(
                    id="task:normalize",
                    kind=TaskUnitKind.FUNCTION,
                    label="normalize(value) [helper.py]",
                    block_ids=["block:normalize"],
                    root_block_ids=["block:normalize"],
                    node_ids=["file:helper.py"],
                    depends_on=[],
                    depended_on_by=["task:run"],
                    depth=0,
                    reasons=[],
                    ready_to_run=True,
                ),
                TaskGraphUnit(
                    id="task:run",
                    kind=TaskUnitKind.FUNCTION,
                    label="run(value) [service.py]",
                    block_ids=["block:run"],
                    root_block_ids=["block:run"],
                    node_ids=["file:service.py"],
                    depends_on=["task:normalize"],
                    depended_on_by=["task:main"],
                    depth=1,
                    reasons=[],
                    ready_to_run=False,
                ),
                TaskGraphUnit(
                    id="task:run_alt",
                    kind=TaskUnitKind.FUNCTION,
                    label="run_alt(value) [service.py]",
                    block_ids=["block:run_alt"],
                    root_block_ids=["block:run_alt"],
                    node_ids=["file:service.py"],
                    depends_on=["task:normalize"],
                    depended_on_by=[],
                    depth=1,
                    reasons=[],
                    ready_to_run=False,
                ),
                TaskGraphUnit(
                    id="task:main",
                    kind=TaskUnitKind.FUNCTION,
                    label="main(raw) [app.py]",
                    block_ids=["block:main"],
                    root_block_ids=["block:main"],
                    node_ids=["file:app.py"],
                    depends_on=["task:run"],
                    depended_on_by=[],
                    depth=2,
                    reasons=[],
                    ready_to_run=False,
                ),
            ],
            edges=[
                TaskGraphEdge(source="task:run", target="task:normalize", reasons=["call"]),
                TaskGraphEdge(source="task:run_alt", target="task:normalize", reasons=["call"]),
                TaskGraphEdge(source="task:main", target="task:run", reasons=["call"]),
            ],
        )
        view = TaskGraphView()
        self.addCleanup(view.close)
        view.resize(1480, 780)
        view.set_task_graph(task_graph)

        self.assertLess(view._node_items["task:normalize"].pos().y(), view._node_items["task:run"].pos().y())
        self.assertLess(view._node_items["task:run"].pos().y(), view._node_items["task:main"].pos().y())
        self.assertEqual(view._node_items["task:run"].pos().y(), view._node_items["task:run_alt"].pos().y())
        self.assertNotEqual(view._node_items["task:run"].pos().x(), view._node_items["task:run_alt"].pos().x())

    def test_select_unit_highlights_neighbors(self) -> None:
        task_graph = TaskGraph(
            units=[
                TaskGraphUnit(
                    id="task:a",
                    kind=TaskUnitKind.FUNCTION,
                    label="a() [a.py]",
                    block_ids=["a"],
                    root_block_ids=["a"],
                    node_ids=["file:a.py"],
                    depends_on=[],
                    depended_on_by=["task:b"],
                    depth=0,
                    reasons=[],
                    ready_to_run=True,
                ),
                TaskGraphUnit(
                    id="task:b",
                    kind=TaskUnitKind.FUNCTION,
                    label="b() [b.py]",
                    block_ids=["b"],
                    root_block_ids=["b"],
                    node_ids=["file:b.py"],
                    depends_on=["task:a"],
                    depended_on_by=["task:c"],
                    depth=1,
                    reasons=[],
                    ready_to_run=False,
                ),
                TaskGraphUnit(
                    id="task:c",
                    kind=TaskUnitKind.FUNCTION,
                    label="c() [c.py]",
                    block_ids=["c"],
                    root_block_ids=["c"],
                    node_ids=["file:c.py"],
                    depends_on=["task:b"],
                    depended_on_by=[],
                    depth=2,
                    reasons=[],
                    ready_to_run=False,
                ),
            ],
            edges=[
                TaskGraphEdge(source="task:b", target="task:a", reasons=["call"]),
                TaskGraphEdge(source="task:c", target="task:b", reasons=["call"]),
            ],
        )
        view = TaskGraphView()
        self.addCleanup(view.close)
        view.set_task_graph(task_graph)

        view.select_unit("task:b")

        self.assertTrue(view._node_items["task:b"]._selected)
        self.assertEqual(view._node_items["task:a"]._neighbor_level, 1)
        self.assertEqual(view._node_items["task:c"]._neighbor_level, 1)

    def test_clicking_blank_area_emits_background_clicked(self) -> None:
        task_graph = TaskGraph(
            units=[
                TaskGraphUnit(
                    id="task:a",
                    kind=TaskUnitKind.FUNCTION,
                    label="a() [a.py]",
                    block_ids=["a"],
                    root_block_ids=["a"],
                    node_ids=["file:a.py"],
                    depends_on=[],
                    depended_on_by=[],
                    depth=0,
                    reasons=[],
                    ready_to_run=True,
                )
            ],
            edges=[],
        )
        view = TaskGraphView()
        self.addCleanup(view.close)
        view.resize(800, 600)
        view.set_task_graph(task_graph)
        hits: list[str] = []
        view.background_clicked.connect(lambda: hits.append("clicked"))
        position = QPointF(view.viewport().rect().bottomRight() - QPoint(4, 4))

        press_event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            position,
            position,
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        release_event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            position,
            position,
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        view.mousePressEvent(press_event)
        view.mouseReleaseEvent(release_event)

        self.assertEqual(hits, ["clicked"])

    def test_same_depth_units_wrap_to_multiple_rows_after_twelve_items(self) -> None:
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
                depth=0,
                reasons=[],
                ready_to_run=True,
            )
            for index in range(13)
        ]
        view = TaskGraphView()
        self.addCleanup(view.close)
        view.resize(980, 720)
        view.set_task_graph(TaskGraph(units=units, edges=[]))

        row_y_values = sorted({round(item.pos().y(), 2) for item in view._node_items.values()})
        self.assertGreater(len(row_y_values), 1)
        self.assertEqual(min(row_y_values), round(view._node_items["task:0"].pos().y(), 2))
        self.assertEqual(len(view._depth_bands), 1)

    def test_node_selection_emits_on_release_not_press(self) -> None:
        task_graph = TaskGraph(
            units=[
                TaskGraphUnit(
                    id="task:a",
                    kind=TaskUnitKind.FUNCTION,
                    label="a() [a.py]",
                    block_ids=["a"],
                    root_block_ids=["a"],
                    node_ids=["file:a.py"],
                    depends_on=[],
                    depended_on_by=[],
                    depth=0,
                    reasons=[],
                    ready_to_run=True,
                )
            ],
            edges=[],
        )
        view = TaskGraphView()
        self.addCleanup(view.close)
        view.resize(900, 640)
        view.show()
        view.set_task_graph(task_graph)
        QApplication.processEvents()
        hits: list[str] = []
        view.unit_selected.connect(hits.append)
        center = view.mapFromScene(view._node_items["task:a"].scenePos())

        QTest.mousePress(view.viewport(), Qt.LeftButton, Qt.NoModifier, center)
        self.assertEqual(hits, [])

        QTest.mouseRelease(view.viewport(), Qt.LeftButton, Qt.NoModifier, center)
        self.assertEqual(hits, ["task:a"])

    def test_execution_state_updates_node_badges(self) -> None:
        task_graph = TaskGraph(
            units=[
                TaskGraphUnit(
                    id="task:a",
                    kind=TaskUnitKind.FUNCTION,
                    label="a() [a.py]",
                    block_ids=["a"],
                    root_block_ids=["a"],
                    node_ids=["file:a.py"],
                    depends_on=[],
                    depended_on_by=[],
                    depth=0,
                    reasons=[],
                    ready_to_run=True,
                )
            ],
            edges=[],
        )
        view = TaskGraphView()
        self.addCleanup(view.close)
        view.set_task_graph(task_graph)

        view.set_execution_state({"task:a": BatchRunItemStatus.RUNNING})

        self.assertEqual(view._node_items["task:a"]._execution_status, BatchRunItemStatus.RUNNING)

    def test_task_node_anchor_points_land_on_rectangle_edge(self) -> None:
        unit = TaskGraphUnit(
            id="task:a",
            kind=TaskUnitKind.FUNCTION,
            label="a() [a.py]",
            block_ids=["a"],
            root_block_ids=["a"],
            node_ids=["file:a.py"],
            depends_on=[],
            depended_on_by=[],
            depth=0,
            reasons=[],
            ready_to_run=True,
        )
        node = TaskNodeItem(unit, "en")
        node.setPos(QPointF(100.0, 200.0))

        right_anchor = node.anchor_point_towards(QPointF(400.0, 200.0))
        down_anchor = node.anchor_point_towards(QPointF(100.0, 500.0))

        self.assertAlmostEqual(right_anchor.x(), 193.5, places=1)
        self.assertAlmostEqual(right_anchor.y(), 200.0, places=1)
        self.assertAlmostEqual(down_anchor.x(), 100.0, places=1)
        self.assertAlmostEqual(down_anchor.y(), 243.5, places=1)


if __name__ == "__main__":
    unittest.main()
