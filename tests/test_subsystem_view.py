from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsTextItem

from bettercode.models import GraphEdge, GraphNode, NodeKind, ProjectGraph, ProjectSummary
from bettercode.parser import ProjectAnalyzer
from bettercode.ui.graph_view import GraphNodeItem
from bettercode.ui.subsystem_view import SubsystemCanvasView


class SubsystemViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_renders_subsystem_boxes_with_internal_node_graphs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "alpha.py").write_text("import beta\n", encoding="utf-8")
            (root / "beta.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "gamma.py").write_text("VALUE = 2\n", encoding="utf-8")

            graph = ProjectAnalyzer().analyze(root)
            view = SubsystemCanvasView()
            self.addCleanup(view.close)
            view.set_graph(graph)

            rect_items = [
                item
                for item in view.scene().items()
                if isinstance(item, QGraphicsRectItem) and item.pen().style() == Qt.DashLine
            ]
            title_items = [
                item.toPlainText()
                for item in view.scene().items()
                if isinstance(item, QGraphicsTextItem)
            ]
            node_items = [
                item
                for item in view.scene().items()
                if isinstance(item, GraphNodeItem)
            ]

        self.assertEqual(len(rect_items), 2)
        self.assertIn("Subsystem 1", title_items)
        self.assertIn("Subsystem 2", title_items)
        self.assertEqual(len(node_items), 3)

    def test_select_node_highlights_neighbors_inside_subsystem_graph(self) -> None:
        graph = ProjectGraph(
            project=ProjectSummary(
                name="demo",
                root_path=Path("."),
                python_files=3,
                external_packages=0,
                parse_duration_ms=0,
                parse_errors=0,
            ),
            nodes=[
                GraphNode(id="file:a.py", kind=NodeKind.PYTHON_FILE, label="a.py", path="a.py", module="a"),
                GraphNode(id="file:b.py", kind=NodeKind.PYTHON_FILE, label="b.py", path="b.py", module="b"),
                GraphNode(id="file:c.py", kind=NodeKind.PYTHON_FILE, label="c.py", path="c.py", module="c"),
            ],
            edges=[
                GraphEdge(id="edge:file:a.py->file:b.py", source="file:a.py", target="file:b.py"),
                GraphEdge(id="edge:file:c.py->file:b.py", source="file:c.py", target="file:b.py"),
            ],
            file_details={},
        )
        view = SubsystemCanvasView()
        self.addCleanup(view.close)
        view.set_graph(graph)

        view.select_node("file:b.py")

        self.assertTrue(view._node_items["file:b.py"]._selected)
        self.assertEqual(view._node_items["file:a.py"]._neighbor_level, 1)
        self.assertEqual(view._node_items["file:c.py"]._neighbor_level, 1)
        self.assertFalse(view._node_items["file:a.py"]._dimmed)
        self.assertEqual(view._edge_items["edge:file:a.py->file:b.py"]._neighbor_level, 1)
        self.assertEqual(view._edge_items["edge:file:c.py->file:b.py"]._neighbor_level, 1)

    def test_clicking_blank_area_emits_background_clicked(self) -> None:
        graph = ProjectGraph(
            project=ProjectSummary(
                name="demo",
                root_path=Path("."),
                python_files=1,
                external_packages=0,
                parse_duration_ms=0,
                parse_errors=0,
            ),
            nodes=[
                GraphNode(id="file:a.py", kind=NodeKind.PYTHON_FILE, label="a.py", path="a.py", module="a"),
            ],
            edges=[],
            file_details={},
        )
        view = SubsystemCanvasView()
        self.addCleanup(view.close)
        view.resize(800, 600)
        view.set_graph(graph)
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

    def test_wide_canvas_prefers_horizontal_subsystem_layout(self) -> None:
        graph = ProjectGraph(
            project=ProjectSummary(
                name="demo",
                root_path=Path("."),
                python_files=8,
                external_packages=0,
                parse_duration_ms=0,
                parse_errors=0,
            ),
            nodes=[
                GraphNode(
                    id=f"file:{index}.py",
                    kind=NodeKind.PYTHON_FILE,
                    label=f"{index}.py",
                    path=f"{index}.py",
                    module=f"m{index}",
                )
                for index in range(8)
            ],
            edges=[
                GraphEdge(
                    id=f"edge:file:{index}.py->file:{index + 1}.py",
                    source=f"file:{index}.py",
                    target=f"file:{index + 1}.py",
                )
                for index in range(7)
            ],
            file_details={},
        )
        view = SubsystemCanvasView()
        self.addCleanup(view.close)
        view.resize(1480, 780)
        view.set_graph(graph)

        xs = [item.pos().x() for item in view._node_items.values()]
        ys = [item.pos().y() for item in view._node_items.values()]

        self.assertGreater(max(xs) - min(xs), max(ys) - min(ys))

    def test_subsystem_layout_orders_leaf_then_internal_then_top_level_script(self) -> None:
        graph = ProjectGraph(
            project=ProjectSummary(
                name="demo",
                root_path=Path("."),
                python_files=3,
                external_packages=0,
                parse_duration_ms=0,
                parse_errors=0,
            ),
            nodes=[
                GraphNode(
                    id="file:leaf.py",
                    kind=NodeKind.LEAF_FILE,
                    label="leaf.py",
                    path="leaf.py",
                    module="leaf",
                ),
                GraphNode(
                    id="file:core.py",
                    kind=NodeKind.PYTHON_FILE,
                    label="core.py",
                    path="core.py",
                    module="core",
                ),
                GraphNode(
                    id="file:entry.py",
                    kind=NodeKind.TOP_LEVEL_SCRIPT,
                    label="entry.py",
                    path="entry.py",
                    module="entry",
                ),
            ],
            edges=[
                GraphEdge(id="edge:leaf->core", source="file:leaf.py", target="file:core.py"),
                GraphEdge(id="edge:core->entry", source="file:core.py", target="file:entry.py"),
            ],
            file_details={},
        )
        view = SubsystemCanvasView()
        self.addCleanup(view.close)
        view.resize(1480, 780)
        view.set_graph(graph)

        reading_order = [
            node_id
            for node_id, _item in sorted(
                view._node_items.items(),
                key=lambda pair: (round(pair[1].pos().y(), 3), round(pair[1].pos().x(), 3)),
            )
        ]
        self.assertEqual(reading_order, ["file:leaf.py", "file:core.py", "file:entry.py"])


if __name__ == "__main__":
    unittest.main()
