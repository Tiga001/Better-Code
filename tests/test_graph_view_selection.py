from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bettercode.graph_analysis import analyze_graph_structure
from bettercode.models import GraphEdge, GraphNode, NodeKind, ProjectGraph, ProjectSummary
from bettercode.ui.graph_view import DependencyGraphView, _edge_arrow_size


class GraphViewSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_select_node_highlights_connected_nodes_and_edges(self) -> None:
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
        insights = analyze_graph_structure(graph)
        view = DependencyGraphView()
        view.set_graph(graph, insights)

        view.select_node("file:b.py")

        self.assertTrue(view._node_items["file:b.py"]._selected)
        self.assertEqual(view._node_items["file:a.py"]._neighbor_level, 1)
        self.assertEqual(view._node_items["file:c.py"]._neighbor_level, 1)
        self.assertFalse(view._node_items["file:a.py"]._dimmed)
        self.assertFalse(view._node_items["file:c.py"]._dimmed)
        self.assertEqual(view._edge_items["edge:file:a.py->file:b.py"]._neighbor_level, 1)
        self.assertEqual(view._edge_items["edge:file:c.py->file:b.py"]._neighbor_level, 1)
        self.assertFalse(view._edge_items["edge:file:a.py->file:b.py"]._dimmed)

    def test_two_hop_highlight_follows_same_direction_only(self) -> None:
        graph = ProjectGraph(
            project=ProjectSummary(
                name="demo",
                root_path=Path("."),
                python_files=7,
                external_packages=0,
                parse_duration_ms=0,
                parse_errors=0,
            ),
            nodes=[
                GraphNode(id="file:a.py", kind=NodeKind.PYTHON_FILE, label="a.py", path="a.py", module="a"),
                GraphNode(id="file:b.py", kind=NodeKind.PYTHON_FILE, label="b.py", path="b.py", module="b"),
                GraphNode(id="file:c.py", kind=NodeKind.PYTHON_FILE, label="c.py", path="c.py", module="c"),
                GraphNode(id="file:d.py", kind=NodeKind.PYTHON_FILE, label="d.py", path="d.py", module="d"),
                GraphNode(id="file:e.py", kind=NodeKind.PYTHON_FILE, label="e.py", path="e.py", module="e"),
                GraphNode(id="file:f.py", kind=NodeKind.PYTHON_FILE, label="f.py", path="f.py", module="f"),
                GraphNode(id="file:g.py", kind=NodeKind.PYTHON_FILE, label="g.py", path="g.py", module="g"),
            ],
            edges=[
                GraphEdge(id="edge:file:a.py->file:b.py", source="file:a.py", target="file:b.py"),
                GraphEdge(id="edge:file:b.py->file:c.py", source="file:b.py", target="file:c.py"),
                GraphEdge(id="edge:file:d.py->file:a.py", source="file:d.py", target="file:a.py"),
                GraphEdge(id="edge:file:c.py->file:e.py", source="file:c.py", target="file:e.py"),
                GraphEdge(id="edge:file:a.py->file:f.py", source="file:a.py", target="file:f.py"),
                GraphEdge(id="edge:file:f.py->file:c.py", source="file:f.py", target="file:c.py"),
                GraphEdge(id="edge:file:b.py->file:g.py", source="file:b.py", target="file:g.py"),
                GraphEdge(id="edge:file:g.py->file:c.py", source="file:g.py", target="file:c.py"),
            ],
            file_details={},
        )
        insights = analyze_graph_structure(graph)
        view = DependencyGraphView()
        view.set_graph(graph, insights)
        view.set_neighbor_depth(2)

        view.select_node("file:b.py")

        self.assertEqual(view._node_items["file:a.py"]._neighbor_level, 1)
        self.assertEqual(view._node_items["file:c.py"]._neighbor_level, 1)
        self.assertEqual(view._node_items["file:d.py"]._neighbor_level, 2)
        self.assertEqual(view._node_items["file:e.py"]._neighbor_level, 2)
        self.assertEqual(view._node_items["file:f.py"]._neighbor_level, 0)
        self.assertEqual(view._node_items["file:g.py"]._neighbor_level, 1)
        self.assertEqual(view._edge_items["edge:file:d.py->file:a.py"]._neighbor_level, 2)
        self.assertEqual(view._edge_items["edge:file:c.py->file:e.py"]._neighbor_level, 2)
        self.assertEqual(view._edge_items["edge:file:a.py->file:f.py"]._neighbor_level, 0)
        self.assertEqual(view._edge_items["edge:file:f.py->file:c.py"]._neighbor_level, 0)
        self.assertEqual(view._edge_items["edge:file:b.py->file:g.py"]._neighbor_level, 1)
        self.assertEqual(view._edge_items["edge:file:g.py->file:c.py"]._neighbor_level, 2)

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
        insights = analyze_graph_structure(graph)
        view = DependencyGraphView()
        view.resize(800, 600)
        view.set_graph(graph, insights)
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

    def test_dragging_blank_area_does_not_emit_background_clicked(self) -> None:
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
        insights = analyze_graph_structure(graph)
        view = DependencyGraphView()
        view.resize(800, 600)
        view.set_graph(graph, insights)
        hits: list[str] = []
        view.background_clicked.connect(lambda: hits.append("clicked"))
        start = QPointF(view.viewport().rect().bottomRight() - QPoint(40, 40))
        end = QPointF(view.viewport().rect().bottomRight() - QPoint(4, 4))

        press_event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            start,
            start,
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        release_event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            end,
            end,
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        view.mousePressEvent(press_event)
        view.mouseReleaseEvent(release_event)

        self.assertEqual(hits, [])

    def test_reset_view_uses_fit_scale_as_minimum_when_graph_is_small(self) -> None:
        graph = ProjectGraph(
            project=ProjectSummary(
                name="demo",
                root_path=Path("."),
                python_files=20,
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
                for index in range(20)
            ],
            edges=[],
            file_details={},
        )
        insights = analyze_graph_structure(graph)
        view = DependencyGraphView()
        view.resize(640, 480)
        view.set_graph(graph, insights)

        self.assertLessEqual(view._min_scale, view.transform().m11() + 1e-9)

    def test_highlighted_edges_use_larger_arrow_sizes(self) -> None:
        self.assertEqual(_edge_arrow_size(0), 12.0)
        self.assertEqual(_edge_arrow_size(2), 16.0)
        self.assertEqual(_edge_arrow_size(1), 18.0)

    def test_wide_canvas_prefers_horizontal_layout(self) -> None:
        graph = ProjectGraph(
            project=ProjectSummary(
                name="demo",
                root_path=Path("."),
                python_files=12,
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
                for index in range(12)
            ],
            edges=[],
            file_details={},
        )
        insights = analyze_graph_structure(graph)
        view = DependencyGraphView()
        view.resize(1480, 780)
        view.set_graph(graph, insights)

        xs = [item.pos().x() for item in view._node_items.values()]
        ys = [item.pos().y() for item in view._node_items.values()]

        self.assertGreater(max(xs) - min(xs), max(ys) - min(ys))

    def test_file_layout_orders_leaf_then_internal_then_top_level_script(self) -> None:
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
            edges=[],
            file_details={},
        )
        insights = analyze_graph_structure(graph)
        view = DependencyGraphView()
        view.resize(1480, 780)
        view.set_graph(graph, insights)

        reading_order = [
            node_id
            for node_id, _item in sorted(
                view._node_items.items(),
                key=lambda pair: (round(pair[1].pos().y(), 3), round(pair[1].pos().x(), 3)),
            )
        ]
        self.assertEqual(reading_order, ["file:leaf.py", "file:core.py", "file:entry.py"])

    def test_node_selection_emits_on_release_not_press(self) -> None:
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
        insights = analyze_graph_structure(graph)
        view = DependencyGraphView()
        self.addCleanup(view.close)
        view.resize(900, 640)
        view.show()
        view.set_graph(graph, insights)
        QApplication.processEvents()
        hits: list[str] = []
        view.node_selected.connect(hits.append)
        center = view.mapFromScene(view._node_items["file:a.py"].scenePos())

        QTest.mousePress(view.viewport(), Qt.LeftButton, Qt.NoModifier, center)
        self.assertEqual(hits, [])

        QTest.mouseRelease(view.viewport(), Qt.LeftButton, Qt.NoModifier, center)
        self.assertEqual(hits, ["file:a.py"])


if __name__ == "__main__":
    unittest.main()
