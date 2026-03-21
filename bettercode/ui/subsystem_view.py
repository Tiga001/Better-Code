from __future__ import annotations

import math
from collections import Counter

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QWidget,
)

from bettercode.graph_analysis import SubsystemSummary, decompose_subsystems
from bettercode.i18n import LanguageCode, tr
from bettercode.models import GraphEdge, GraphNode, NodeKind, ProjectGraph
from bettercode.ui.graph_view import GraphEdgeItem, GraphNodeItem, _preferred_grid_columns


class SubsystemCanvasView(QGraphicsView):
    node_selected = Signal(object)
    node_double_clicked = Signal(str)
    background_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QColor("#0e1422"))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._graph: ProjectGraph | None = None
        self._language: LanguageCode = "en"
        self._has_user_zoomed = False
        self._min_scale = 0.35
        self._max_scale = 3.5
        self._node_items: dict[str, GraphNodeItem] = {}
        self._edge_items: dict[str, GraphEdgeItem] = {}
        self._selected_node_id: str | None = None
        self._selected_related_node_levels: dict[str, int] = {}
        self._selected_related_edge_levels: dict[str, int] = {}
        self._neighbor_depth = 1
        self._background_press_pos: QPointF | None = None
        self._background_press_started = False

    def clear_view(self) -> None:
        self._scene.clear()
        self._graph = None
        self._has_user_zoomed = False
        self._node_items.clear()
        self._edge_items.clear()
        self._selected_node_id = None
        self._selected_related_node_levels.clear()
        self._selected_related_edge_levels.clear()
        self._background_press_pos = None
        self._background_press_started = False

    def set_graph(self, graph: ProjectGraph | None) -> None:
        selected_node_id = self._selected_node_id
        self.clear_view()
        self._graph = graph
        if graph is None:
            return

        subsystems = decompose_subsystems(graph)
        if not subsystems:
            self._render_empty_state()
            return

        self._render_subsystems(graph, subsystems)
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-100, -100, 100, 100))
        self.reset_view()
        self.select_node(selected_node_id)

    def set_language(self, language: LanguageCode) -> None:
        self._language = language
        if self._graph is not None:
            self.set_graph(self._graph)

    def set_neighbor_depth(self, neighbor_depth: int) -> None:
        self._neighbor_depth = 2 if neighbor_depth == 2 else 1
        if self._selected_node_id is not None:
            self.select_node(self._selected_node_id)
        else:
            self._apply_visual_state()

    def select_node(self, node_id: str | None) -> None:
        if node_id is not None and node_id not in self._node_items:
            node_id = None
        self._selected_node_id = node_id
        self._selected_related_node_levels = {}
        self._selected_related_edge_levels = {}
        if self._graph is not None and node_id is not None:
            (
                self._selected_related_node_levels,
                self._selected_related_edge_levels,
            ) = self._neighbor_context_levels(node_id)
        self._apply_visual_state()
        if node_id and node_id in self._node_items:
            self.centerOn(self._node_items[node_id])

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.itemAt(event.position().toPoint()) is None:
            self._background_press_started = True
            self._background_press_pos = event.position()
        else:
            self._background_press_started = False
            self._background_press_pos = None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if (
            event.button() == Qt.LeftButton
            and self._background_press_started
            and self._background_press_pos is not None
            and self.itemAt(event.position().toPoint()) is None
        ):
            drag_distance = (event.position() - self._background_press_pos).manhattanLength()
            if drag_distance < QApplication.startDragDistance():
                self.background_clicked.emit()
        self._background_press_started = False
        self._background_press_pos = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if not self._scene.items():
            return

        zoom_factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        current_scale = self.transform().m11()
        next_scale = current_scale * zoom_factor
        bounded_scale = max(self._min_scale, min(self._max_scale, next_scale))
        if math.isclose(bounded_scale, current_scale, rel_tol=1e-6, abs_tol=1e-6):
            event.accept()
            return

        self.scale(bounded_scale / current_scale, bounded_scale / current_scale)
        self._has_user_zoomed = True
        event.accept()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._graph and self._scene.items() and not self._has_user_zoomed:
            self.set_graph(self._graph)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        painter.save()
        painter.setPen(QPen(QColor("#172033"), 1))
        grid = 36
        left = int(rect.left()) - (int(rect.left()) % grid)
        top = int(rect.top()) - (int(rect.top()) % grid)
        path = QPainterPath()
        x = left
        while x < rect.right():
            path.moveTo(x, rect.top())
            path.lineTo(x, rect.bottom())
            x += grid
        y = top
        while y < rect.bottom():
            path.moveTo(rect.left(), y)
            path.lineTo(rect.right(), y)
            y += grid
        painter.drawPath(path)
        painter.restore()

    def reset_view(self) -> None:
        if not self._scene.items():
            return
        self._has_user_zoomed = False
        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._min_scale = min(0.35, self.transform().m11())

    def _render_empty_state(self) -> None:
        text_item = self._scene.addText(tr(self._language, "subsystem.empty"))
        text_item.setDefaultTextColor(QColor("#d8e3f5"))
        text_item.setPos(120, 120)

    def _render_subsystems(self, graph: ProjectGraph, subsystems: list[SubsystemSummary]) -> None:
        internal_nodes = {
            node.id: node
            for node in graph.nodes
            if node.kind is not NodeKind.EXTERNAL_PACKAGE
        }
        internal_edges = [
            edge
            for edge in graph.edges
            if edge.source in internal_nodes and edge.target in internal_nodes
        ]
        duplicate_labels = dict(Counter(node.label for node in internal_nodes.values()))

        layouts: list[_SubsystemLayout] = []
        for subsystem in subsystems:
            member_node_ids = set(subsystem.node_ids)
            member_nodes = [internal_nodes[node_id] for node_id in subsystem.node_ids if node_id in internal_nodes]
            member_edges = [
                edge
                for edge in internal_edges
                if edge.source in member_node_ids and edge.target in member_node_ids
            ]
            layouts.append(
                self._build_subsystem_layout(
                    subsystem=subsystem,
                    nodes=member_nodes,
                    edges=member_edges,
                    duplicate_labels=duplicate_labels,
                )
            )

        columns = 1 if len(layouts) == 1 else 2
        row_gap = 40
        column_gap = 36
        start_x = 72
        start_y = 72

        row_heights: dict[int, float] = {}
        boxes: list[tuple[int, int, _SubsystemLayout]] = []
        for index, layout in enumerate(layouts):
            row = index // columns
            column = index % columns
            row_heights[row] = max(row_heights.get(row, 0.0), layout.height)
            boxes.append((row, column, layout))

        row_offsets: dict[int, float] = {}
        current_y = start_y
        for row in range(max(row_heights.keys(), default=-1) + 1):
            row_offsets[row] = current_y
            current_y += row_heights.get(row, 0.0) + row_gap

        column_widths: dict[int, float] = {}
        for _, column, layout in boxes:
            column_widths[column] = max(column_widths.get(column, 0.0), layout.width)

        column_offsets: dict[int, float] = {}
        current_x = start_x
        for column in range(columns):
            column_offsets[column] = current_x
            current_x += column_widths.get(column, 0.0) + column_gap

        for row, column, layout in boxes:
            self._add_subsystem_group(column_offsets[column], row_offsets[row], layout)

    def _build_subsystem_layout(
        self,
        *,
        subsystem: SubsystemSummary,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
        duplicate_labels: dict[str, int],
    ) -> "_SubsystemLayout":
        header_height = 86.0
        horizontal_padding = 74.0
        vertical_padding = 60.0
        row_spacing = 190.0
        column_spacing = 220.0
        columns = _preferred_grid_columns(
            len(nodes),
            target_aspect=1.9,
            column_spacing=column_spacing,
            row_spacing=row_spacing,
            max_columns=min(len(nodes), 6) if nodes else 1,
        )
        ordered_nodes = sorted(
            nodes,
            key=lambda node: (
                0
                if node.kind is NodeKind.LEAF_FILE
                else 1
                if node.kind is NodeKind.PYTHON_FILE
                else 2,
                (node.path or node.label).lower(),
            ),
        )

        positions: dict[str, QPointF] = {}
        for index, node in enumerate(ordered_nodes):
            row = index // columns
            column = index % columns
            row_count = min(columns, len(ordered_nodes) - row * columns)
            row_width = max(0.0, (row_count - 1) * column_spacing)
            row_start_x = horizontal_padding + max(0.0, ((columns - 1) * column_spacing - row_width) / 2)
            positions[node.id] = QPointF(
                row_start_x + column * column_spacing,
                header_height + vertical_padding + row * row_spacing,
            )

        row_count = max(1, math.ceil(len(ordered_nodes) / columns))
        width = max(
            420.0,
            horizontal_padding * 2 + (max(0, columns - 1) * column_spacing) + 120.0,
        )
        height = max(
            280.0,
            header_height + vertical_padding + (max(0, row_count - 1) * row_spacing) + 118.0,
        )

        return _SubsystemLayout(
            summary=subsystem,
            width=width,
            height=height,
            positions=positions,
            nodes=ordered_nodes,
            edges=edges,
            duplicate_labels=duplicate_labels,
        )

    def _add_subsystem_group(self, offset_x: float, offset_y: float, layout: "_SubsystemLayout") -> None:
        rect_item = QGraphicsRectItem(QRectF(offset_x, offset_y, layout.width, layout.height))
        border_pen = QPen(QColor("#5b81aa"), 2)
        border_pen.setStyle(Qt.DashLine)
        rect_item.setPen(border_pen)
        rect_item.setBrush(QColor("#101a2a"))
        rect_item.setZValue(-5)
        self._scene.addItem(rect_item)

        title_item = QGraphicsTextItem(tr(self._language, "subsystem.title", index=layout.summary.index))
        title_item.setDefaultTextColor(QColor("#f7fbff"))
        title_item.setPos(offset_x + 16, offset_y + 12)
        self._scene.addItem(title_item)

        count_item = QGraphicsTextItem(tr(self._language, "subsystem.files", count=len(layout.nodes)))
        count_item.setDefaultTextColor(QColor("#8fb4d9"))
        count_item.setPos(offset_x + 16, offset_y + 40)
        self._scene.addItem(count_item)

        node_items: dict[str, GraphNodeItem] = {}
        for node in layout.nodes:
            item = GraphNodeItem(node, layout.duplicate_labels, self._language)
            position = layout.positions[node.id]
            item.setPos(offset_x + position.x(), offset_y + position.y())
            item.clicked.connect(self.node_selected.emit)
            item.double_clicked.connect(self.node_double_clicked.emit)
            self._scene.addItem(item)
            node_items[node.id] = item
            self._node_items[node.id] = item

        for edge in layout.edges:
            source_item = node_items.get(edge.source)
            target_item = node_items.get(edge.target)
            if source_item is None or target_item is None:
                continue
            edge_item = GraphEdgeItem(source_item, target_item)
            self._scene.addItem(edge_item)
            self._edge_items[edge.id] = edge_item

        self._apply_visual_state()

    def _apply_visual_state(self) -> None:
        for node_id, item in self._node_items.items():
            in_selected_context = (
                self._selected_node_id is None
                or node_id == self._selected_node_id
                or node_id in self._selected_related_node_levels
            )
            item.set_dimmed(not in_selected_context)
            item.set_selected(node_id == self._selected_node_id)
            item.set_neighbor_level(self._selected_related_node_levels.get(node_id, 0))
            item.set_search_match(False)
            item.set_cycle_member(False)
            item.set_isolated(False)

        for edge in self._graph.edges if self._graph else []:
            item = self._edge_items.get(edge.id)
            if item is None:
                continue
            in_selected_context = (
                self._selected_node_id is None or edge.id in self._selected_related_edge_levels
            )
            item.set_dimmed(not in_selected_context)
            item.set_neighbor_level(self._selected_related_edge_levels.get(edge.id, 0))
            item.set_cycle_member(False)

    def _neighbor_context_levels(self, node_id: str) -> tuple[dict[str, int], dict[str, int]]:
        if self._graph is None:
            return {}, {}

        available_node_ids = set(self._node_items)
        node_levels: dict[str, int] = {}
        edge_levels: dict[str, int] = {}
        incoming_first: set[str] = set()
        outgoing_first: set[str] = set()

        for edge in self._graph.edges:
            if edge.source not in available_node_ids or edge.target not in available_node_ids:
                continue
            if edge.source == node_id:
                outgoing_first.add(edge.target)
                self._set_min_level(edge_levels, edge.id, 1)
                if edge.target != node_id:
                    self._set_min_level(node_levels, edge.target, 1)
            elif edge.target == node_id:
                incoming_first.add(edge.source)
                self._set_min_level(edge_levels, edge.id, 1)
                if edge.source != node_id:
                    self._set_min_level(node_levels, edge.source, 1)

        if self._neighbor_depth >= 2:
            for edge in self._graph.edges:
                if edge.source not in available_node_ids or edge.target not in available_node_ids:
                    continue
                if edge.source in outgoing_first:
                    self._set_min_level(edge_levels, edge.id, 2)
                    if edge.target != node_id and edge.target not in outgoing_first:
                        self._set_min_level(node_levels, edge.target, 2)
                if edge.target in incoming_first:
                    self._set_min_level(edge_levels, edge.id, 2)
                    if edge.source != node_id and edge.source not in incoming_first:
                        self._set_min_level(node_levels, edge.source, 2)

        node_levels.pop(node_id, None)
        return node_levels, edge_levels

    def _set_min_level(self, levels: dict[str, int], key: str, level: int) -> None:
        current_level = levels.get(key)
        if current_level is None or level < current_level:
            levels[key] = level


class _SubsystemLayout:
    def __init__(
        self,
        *,
        summary: SubsystemSummary,
        width: float,
        height: float,
        positions: dict[str, QPointF],
        nodes: list[GraphNode],
        edges: list[GraphEdge],
        duplicate_labels: dict[str, int],
    ) -> None:
        self.summary = summary
        self.width = width
        self.height = height
        self.positions = positions
        self.nodes = nodes
        self.edges = edges
        self.duplicate_labels = duplicate_labels
