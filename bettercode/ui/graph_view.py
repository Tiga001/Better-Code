from __future__ import annotations

import math
from collections import Counter
from pathlib import PurePosixPath

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsView, QWidget

from bettercode.graph_analysis import GraphInsights
from bettercode.models import GraphEdge, GraphNode, NodeKind, ProjectGraph


GENERIC_FILENAMES = {"__init__.py", "main.py", "app.py"}


def _node_display_text(node: GraphNode, duplicate_labels: dict[str, int]) -> tuple[list[str], str | None]:
    title_lines = _wrap_label_lines(node.label)
    subtitle = None
    if node.kind is not NodeKind.EXTERNAL_PACKAGE and duplicate_labels.get(node.label, 0) > 1:
        subtitle = _path_hint(node.path)
    elif node.kind is not NodeKind.EXTERNAL_PACKAGE and node.label in GENERIC_FILENAMES:
        subtitle = _path_hint(node.path)
    return title_lines, subtitle


def _wrap_label_lines(label: str, *, max_lines: int = 2, max_line_chars: int = 11) -> list[str]:
    if label.startswith("__") and label.endswith(".py"):
        return [label]

    stem, dot, suffix = label.rpartition(".")
    if not dot:
        stem = label
        suffix = ""

    tokens = [token for token in stem.replace("-", "_").split("_") if token]
    if not tokens:
        tokens = [stem or label]

    if suffix:
        tokens[-1] = f"{tokens[-1]}.{suffix}"

    lines: list[str] = []
    current = tokens[0]
    for token in tokens[1:]:
        tentative = f"{current}_{token}"
        if len(tentative) <= max_line_chars or len(lines) + 1 >= max_lines:
            current = tentative
            continue
        lines.append(current)
        current = token

    lines.append(current)
    if len(lines) > max_lines:
        overflow = "_".join(lines[max_lines - 1 :])
        lines = lines[: max_lines - 1] + [_truncate_text(overflow, max_line_chars)]
    else:
        lines[-1] = _truncate_text(lines[-1], max_line_chars)
    return lines


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return f"{text[: max_chars - 1]}…"


def _path_hint(path: str | None) -> str | None:
    if not path:
        return None
    parent = PurePosixPath(path).parent
    if str(parent) in {".", ""}:
        return "project root"
    parts = parent.parts[-2:]
    return "/".join(parts)


class GraphNodeItem(QGraphicsObject):
    clicked = Signal(str)
    double_clicked = Signal(str)

    def __init__(self, node: GraphNode, duplicate_labels: dict[str, int]) -> None:
        super().__init__()
        self.node = node
        self._radius = 58.0
        self._selected = False
        self._dimmed = False
        self._search_match = False
        self._cycle_member = False
        self._isolated = False
        self._title_lines, self._subtitle = _node_display_text(node, duplicate_labels)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(node.path or node.label)

    @property
    def radius(self) -> float:
        return self._radius

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def set_dimmed(self, dimmed: bool) -> None:
        self._dimmed = dimmed
        self.setOpacity(0.18 if dimmed else 1.0)
        self.update()

    def set_search_match(self, search_match: bool) -> None:
        self._search_match = search_match
        self.update()

    def set_cycle_member(self, cycle_member: bool) -> None:
        self._cycle_member = cycle_member
        self.update()

    def set_isolated(self, isolated: bool) -> None:
        self._isolated = isolated
        self.update()

    def boundingRect(self) -> QRectF:
        margin = 10.0
        return QRectF(
            -self._radius - margin,
            -self._radius - margin,
            self._radius * 2 + margin * 2,
            self._radius * 2 + margin * 2,
        )

    def paint(self, painter: QPainter, _option, _widget: QWidget | None = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        if self._cycle_member:
            painter.setPen(QPen(QColor("#ff5d6c"), 5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(-66, -66, 132, 132))
        elif self._isolated:
            dash_pen = QPen(QColor("#a06dff"), 4)
            dash_pen.setStyle(Qt.DashLine)
            painter.setPen(dash_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(-66, -66, 132, 132))

        fill_color = self._fill_color()
        border_color = QColor("#ffffff")
        if not self._selected and self._search_match:
            border_color = QColor("#ffd166")
        elif not self._selected:
            border_color = QColor("#d9e4ff")
        border_width = 4 if self._selected else 2
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(fill_color)

        if self.node.kind is NodeKind.EXTERNAL_PACKAGE:
            painter.drawRoundedRect(QRectF(-54, -54, 108, 108), 14, 14)
        elif self.node.kind is NodeKind.LEAF_FILE:
            polygon = QPolygonF(
                [
                    QPointF(0, -58),
                    QPointF(50, -29),
                    QPointF(50, 29),
                    QPointF(0, 58),
                    QPointF(-50, 29),
                    QPointF(-50, -29),
                ]
            )
            painter.drawPolygon(polygon)
        else:
            painter.drawEllipse(QRectF(-58, -58, 116, 116))

        self._draw_label(painter)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self.node.id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        self.double_clicked.emit(self.node.id)
        event.accept()

    def _draw_label(self, painter: QPainter) -> None:
        title_font = QFont("Helvetica Neue", 10 if self._subtitle else 11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor("#f8fbff")))
        title_metrics = QFontMetrics(title_font)
        line_height = title_metrics.height()
        start_y = -20 if self._subtitle else -((len(self._title_lines) * line_height) / 2) + 4

        for index, line in enumerate(self._title_lines):
            text = title_metrics.elidedText(line, Qt.ElideRight, 92)
            rect = QRectF(-46, start_y + index * line_height, 92, line_height + 2)
            painter.drawText(rect, Qt.AlignCenter, text)

        if not self._subtitle:
            return

        subtitle_font = QFont("Helvetica Neue", 8)
        painter.setFont(subtitle_font)
        painter.setPen(QPen(QColor("#c6d4ef")))
        subtitle_metrics = QFontMetrics(subtitle_font)
        subtitle = subtitle_metrics.elidedText(self._subtitle, Qt.ElideMiddle, 90)
        painter.drawText(QRectF(-45, 18, 90, subtitle_metrics.height() + 2), Qt.AlignCenter, subtitle)

    def _fill_color(self) -> QColor:
        if self.node.kind is NodeKind.EXTERNAL_PACKAGE:
            return QColor("#ff8a3d")
        if self.node.kind is NodeKind.LEAF_FILE:
            return QColor("#118c6a")
        return QColor("#3559d1")


class GraphEdgeItem(QGraphicsItem):
    def __init__(self, source_item: GraphNodeItem, target_item: GraphNodeItem) -> None:
        super().__init__()
        self._source_item = source_item
        self._target_item = target_item
        self._dimmed = False
        self._cycle_member = False
        self.setZValue(-1)

    def set_dimmed(self, dimmed: bool) -> None:
        self._dimmed = dimmed
        self.update()

    def set_cycle_member(self, cycle_member: bool) -> None:
        self._cycle_member = cycle_member
        self.update()

    def boundingRect(self) -> QRectF:
        source = self._source_item.pos()
        target = self._target_item.pos()
        return QRectF(source, target).normalized().adjusted(-24, -24, 24, 24)

    def paint(self, painter: QPainter, _option, _widget: QWidget | None = None) -> None:
        source = self._source_item.pos()
        target = self._target_item.pos()
        line_dx = target.x() - source.x()
        line_dy = target.y() - source.y()
        length = math.hypot(line_dx, line_dy)
        if length == 0:
            return

        ux = line_dx / length
        uy = line_dy / length
        start = QPointF(
            source.x() + ux * self._source_item.radius,
            source.y() + uy * self._source_item.radius,
        )
        end = QPointF(
            target.x() - ux * self._target_item.radius,
            target.y() - uy * self._target_item.radius,
        )

        painter.setRenderHint(QPainter.Antialiasing)
        stroke_color = QColor("#ff6f7d") if self._cycle_member else QColor("#6f8fff")
        if self._dimmed:
            stroke_color.setAlpha(55)
        painter.setPen(QPen(stroke_color, 2.0))
        painter.drawLine(start, end)

        arrow_size = 12.0
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_p1 = QPointF(
            end.x() - math.cos(angle - math.pi / 6) * arrow_size,
            end.y() - math.sin(angle - math.pi / 6) * arrow_size,
        )
        arrow_p2 = QPointF(
            end.x() - math.cos(angle + math.pi / 6) * arrow_size,
            end.y() - math.sin(angle + math.pi / 6) * arrow_size,
        )
        arrow = QPolygonF([end, arrow_p1, arrow_p2])
        painter.setBrush(stroke_color)
        painter.drawPolygon(arrow)


class DependencyGraphView(QGraphicsView):
    node_selected = Signal(str)
    node_double_clicked = Signal(str)

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
        self._node_items: dict[str, GraphNodeItem] = {}
        self._edge_items: dict[str, GraphEdgeItem] = {}
        self._graph: ProjectGraph | None = None
        self._insights: GraphInsights | None = None
        self._has_user_zoomed = False
        self._min_scale = 0.35
        self._max_scale = 3.5
        self._focused_node_ids: set[str] | None = None
        self._search_match_node_ids: set[str] = set()

    def clear_graph(self) -> None:
        self._scene.clear()
        self._node_items.clear()
        self._edge_items.clear()
        self._graph = None
        self._insights = None
        self._has_user_zoomed = False
        self._focused_node_ids = None
        self._search_match_node_ids.clear()

    def set_graph(self, graph: ProjectGraph, insights: GraphInsights) -> None:
        self.clear_graph()
        self._graph = graph
        self._insights = insights
        duplicate_labels = dict(Counter(node.label for node in graph.nodes))

        positions = self._compute_positions(graph)
        for node in graph.nodes:
            item = GraphNodeItem(node, duplicate_labels)
            item.setPos(positions[node.id])
            item.clicked.connect(self.node_selected.emit)
            item.double_clicked.connect(self.node_double_clicked.emit)
            self._scene.addItem(item)
            self._node_items[node.id] = item

        for edge in graph.edges:
            self._add_edge(edge)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-100, -100, 100, 100))
        self._apply_visual_state()
        self.reset_view()

    def select_node(self, node_id: str | None) -> None:
        for current_id, item in self._node_items.items():
            item.set_selected(current_id == node_id)
        if node_id and node_id in self._node_items:
            self.centerOn(self._node_items[node_id])

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
            self.reset_view()

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

    def _add_edge(self, edge: GraphEdge) -> None:
        source_item = self._node_items.get(edge.source)
        target_item = self._node_items.get(edge.target)
        if source_item is None or target_item is None:
            return
        item = GraphEdgeItem(source_item, target_item)
        self._scene.addItem(item)
        self._edge_items[edge.id] = item

    def set_focused_node_ids(self, node_ids: set[str] | None) -> None:
        self._focused_node_ids = node_ids
        self._apply_visual_state()

    def set_search_match_node_ids(self, node_ids: set[str]) -> None:
        self._search_match_node_ids = node_ids
        self._apply_visual_state()

    def _apply_visual_state(self) -> None:
        if self._insights is None:
            return

        active_node_ids = self._focused_node_ids
        for node_id, item in self._node_items.items():
            item.set_dimmed(active_node_ids is not None and node_id not in active_node_ids)
            item.set_search_match(node_id in self._search_match_node_ids)
            item.set_cycle_member(node_id in self._insights.cycle_node_ids)
            item.set_isolated(node_id in self._insights.isolated_node_ids)

        for edge in self._graph.edges if self._graph else []:
            item = self._edge_items.get(edge.id)
            if item is None:
                continue
            item.set_cycle_member(edge.id in self._insights.cycle_edge_ids)
            item.set_dimmed(
                active_node_ids is not None
                and (edge.source not in active_node_ids or edge.target not in active_node_ids)
            )

    def _compute_positions(self, graph: ProjectGraph) -> dict[str, QPointF]:
        external_nodes = [node for node in graph.nodes if node.kind is NodeKind.EXTERNAL_PACKAGE]
        file_nodes = [node for node in graph.nodes if node.kind is not NodeKind.EXTERNAL_PACKAGE]

        positions: dict[str, QPointF] = {}
        for index, node in enumerate(external_nodes):
            positions[node.id] = QPointF(110, 120 + index * 170)

        if not file_nodes:
            return positions

        columns = min(4, max(1, math.ceil(math.sqrt(len(file_nodes)))))
        row_height = 210
        column_width = 240
        start_x = 360 if external_nodes else 140
        start_y = 120

        ordered_files = sorted(
            file_nodes,
            key=lambda node: (0 if node.kind is NodeKind.LEAF_FILE else 1, node.label.lower()),
        )
        for index, node in enumerate(ordered_files):
            row = index // columns
            column = index % columns
            positions[node.id] = QPointF(start_x + column * column_width, start_y + row * row_height)
        return positions

    def reset_view(self) -> None:
        if not self._scene.items():
            return
        self._has_user_zoomed = False
        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
