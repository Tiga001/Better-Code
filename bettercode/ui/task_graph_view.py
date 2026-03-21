from __future__ import annotations

import math
from collections import defaultdict

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsView, QWidget

from bettercode.i18n import LanguageCode, tr
from bettercode.models import TaskGraph, TaskGraphUnit, TaskUnitKind
from bettercode.ui.graph_view import _edge_arrow_size


class TaskNodeItem(QGraphicsObject):
    clicked = Signal(str)
    double_clicked = Signal(str)

    def __init__(self, unit: TaskGraphUnit, language: LanguageCode) -> None:
        super().__init__()
        self.unit = unit
        self._language = language
        self._width = 190.0
        self._height = 92.0
        self._selected = False
        self._dimmed = False
        self._neighbor_level = 0
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(unit.label)

    @property
    def radius(self) -> float:
        return 60.0

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def set_dimmed(self, dimmed: bool) -> None:
        self._dimmed = dimmed
        self.setOpacity(0.18 if dimmed else 1.0)
        self.update()

    def set_neighbor_level(self, level: int) -> None:
        self._neighbor_level = level
        self.update()

    def set_language(self, language: LanguageCode) -> None:
        self._language = language
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-self._width / 2 - 8, -self._height / 2 - 8, self._width + 16, self._height + 16)

    def paint(self, painter: QPainter, _option, _widget: QWidget | None = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._selected and self._neighbor_level == 1:
            painter.setPen(QPen(QColor("#4fc3ff"), 5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(-101, -51, 202, 102), 18, 18)
        elif not self._selected and self._neighbor_level == 2:
            painter.setPen(QPen(QColor("#c79bff"), 4))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(-101, -51, 202, 102), 18, 18)
        if self._selected:
            painter.setPen(QPen(QColor("#ffd166"), 6))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(-104, -54, 208, 108), 20, 20)

        fill = self._fill_color()
        border = QColor("#ffe7a3") if self._selected else QColor("#d9e4ff")
        if not self._selected and self._neighbor_level == 1:
            border = QColor("#7dc6ff")
        elif not self._selected and self._neighbor_level == 2:
            border = QColor("#c79bff")
        painter.setPen(QPen(border, 4 if self._selected else (3 if self._neighbor_level else 2)))
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(-95, -45, 190, 90), 16, 16)

        self._draw_label(painter)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self.unit.id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        self.double_clicked.emit(self.unit.id)
        event.accept()

    def _draw_label(self, painter: QPainter) -> None:
        title_font = QFont("Helvetica Neue", 10)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor("#f8fbff")))
        metrics = QFontMetrics(title_font)
        title = metrics.elidedText(self.unit.label, Qt.ElideRight, 164)
        painter.drawText(QRectF(-82, -30, 164, 24), Qt.AlignCenter, title)

        meta_font = QFont("Helvetica Neue", 8)
        painter.setFont(meta_font)
        painter.setPen(QPen(QColor("#c6d4ef")))
        meta_metrics = QFontMetrics(meta_font)
        kind = tr(self._language, f"task_graph.kind.{self.unit.kind.value}")
        depth = tr(self._language, "task_graph.meta.depth", depth=self.unit.depth)
        blocks = tr(self._language, "task_graph.meta.blocks", count=len(self.unit.block_ids))
        painter.drawText(QRectF(-82, -2, 164, meta_metrics.height() + 2), Qt.AlignCenter, meta_metrics.elidedText(kind, Qt.ElideRight, 160))
        painter.drawText(QRectF(-82, 16, 164, meta_metrics.height() + 2), Qt.AlignCenter, f"{depth} · {blocks}")

    def _fill_color(self) -> QColor:
        if self.unit.kind is TaskUnitKind.CLASS_GROUP:
            base = QColor("#118c6a")
        elif self.unit.kind is TaskUnitKind.CYCLE_GROUP:
            base = QColor("#9b4fd8")
        else:
            base = QColor("#3559d1")
        if self._selected:
            return base.lighter(125)
        if self._neighbor_level == 1:
            return base.lighter(118)
        if self._neighbor_level == 2:
            return base.lighter(110)
        return base


class TaskEdgeItem(QGraphicsItem):
    def __init__(self, source_item: TaskNodeItem, target_item: TaskNodeItem) -> None:
        super().__init__()
        self._source_item = source_item
        self._target_item = target_item
        self._dimmed = False
        self._neighbor_level = 0
        self.setZValue(-1)

    def set_dimmed(self, dimmed: bool) -> None:
        self._dimmed = dimmed
        self.update()

    def set_neighbor_level(self, level: int) -> None:
        self._neighbor_level = level
        self.update()

    def boundingRect(self) -> QRectF:
        source = self._source_item.pos()
        target = self._target_item.pos()
        return QRectF(source, target).normalized().adjusted(-24, -24, 24, 24)

    def paint(self, painter: QPainter, _option, _widget: QWidget | None = None) -> None:
        source = self._source_item.pos()
        target = self._target_item.pos()
        dx = target.x() - source.x()
        dy = target.y() - source.y()
        length = math.hypot(dx, dy)
        if length == 0:
            return

        ux = dx / length
        uy = dy / length
        start = QPointF(source.x() + ux * self._source_item.radius, source.y() + uy * 22.0)
        end = QPointF(target.x() - ux * self._target_item.radius, target.y() - uy * 22.0)

        painter.setRenderHint(QPainter.Antialiasing)
        if self._neighbor_level == 1:
            stroke = QColor("#7dc6ff")
        elif self._neighbor_level == 2:
            stroke = QColor("#c79bff")
        else:
            stroke = QColor("#6f8fff")
        if self._dimmed:
            stroke.setAlpha(55)
        painter.setPen(QPen(stroke, 3.0 if self._neighbor_level else 2.0))
        painter.drawLine(start, end)

        arrow_size = _edge_arrow_size(self._neighbor_level)
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_p1 = QPointF(
            end.x() - math.cos(angle - math.pi / 6) * arrow_size,
            end.y() - math.sin(angle - math.pi / 6) * arrow_size,
        )
        arrow_p2 = QPointF(
            end.x() - math.cos(angle + math.pi / 6) * arrow_size,
            end.y() - math.sin(angle + math.pi / 6) * arrow_size,
        )
        painter.setBrush(stroke)
        painter.drawPolygon(QPolygonF([end, arrow_p1, arrow_p2]))


class TaskGraphView(QGraphicsView):
    unit_selected = Signal(object)
    unit_double_clicked = Signal(str)
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
        self._task_graph: TaskGraph | None = None
        self._language: LanguageCode = "en"
        self._has_user_zoomed = False
        self._min_scale = 0.35
        self._max_scale = 3.5
        self._node_items: dict[str, TaskNodeItem] = {}
        self._edge_items: dict[str, TaskEdgeItem] = {}
        self._display_edges: list[tuple[str, str]] = []
        self._selected_unit_id: str | None = None
        self._selected_related_node_levels: dict[str, int] = {}
        self._selected_related_edge_levels: dict[str, int] = {}
        self._neighbor_depth = 1
        self._background_press_pos: QPointF | None = None
        self._background_press_started = False

    def clear_graph(self) -> None:
        self._scene.clear()
        self._task_graph = None
        self._has_user_zoomed = False
        self._node_items.clear()
        self._edge_items.clear()
        self._display_edges.clear()
        self._selected_unit_id = None
        self._selected_related_node_levels.clear()
        self._selected_related_edge_levels.clear()
        self._background_press_pos = None
        self._background_press_started = False

    def set_task_graph(self, task_graph: TaskGraph | None) -> None:
        selected_unit_id = self._selected_unit_id
        self.clear_graph()
        self._task_graph = task_graph
        if task_graph is None or not task_graph.units:
            self._render_empty_state()
            return

        positions = self._compute_positions(task_graph)
        units_by_id = {unit.id: unit for unit in task_graph.units}
        for unit in task_graph.units:
            item = TaskNodeItem(unit, self._language)
            item.setPos(positions[unit.id])
            item.clicked.connect(self.unit_selected.emit)
            item.double_clicked.connect(self.unit_double_clicked.emit)
            self._scene.addItem(item)
            self._node_items[unit.id] = item

        for edge in task_graph.edges:
            # The stored edge is "dependent -> dependency". The UI renders
            # "prerequisite -> later task" so execution order reads left-to-right.
            display_source = edge.target
            display_target = edge.source
            source_unit = units_by_id.get(display_source)
            target_unit = units_by_id.get(display_target)
            if source_unit is None or target_unit is None:
                continue
            source_item = self._node_items.get(display_source)
            target_item = self._node_items.get(display_target)
            if source_item is None or target_item is None:
                continue
            edge_item = TaskEdgeItem(source_item, target_item)
            self._scene.addItem(edge_item)
            edge_id = self._edge_id(display_source, display_target)
            self._edge_items[edge_id] = edge_item
            self._display_edges.append((display_source, display_target))

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-100, -100, 100, 100))
        self._apply_visual_state()
        self.reset_view()
        self.select_unit(selected_unit_id)

    def set_language(self, language: LanguageCode) -> None:
        self._language = language
        if self._task_graph is not None:
            self.set_task_graph(self._task_graph)

    def set_neighbor_depth(self, neighbor_depth: int) -> None:
        self._neighbor_depth = 2 if neighbor_depth == 2 else 1
        if self._selected_unit_id is not None:
            self.select_unit(self._selected_unit_id)
        else:
            self._apply_visual_state()

    def select_unit(self, unit_id: str | None) -> None:
        if unit_id is not None and unit_id not in self._node_items:
            unit_id = None
        self._selected_unit_id = unit_id
        self._selected_related_node_levels = {}
        self._selected_related_edge_levels = {}
        if self._task_graph is not None and unit_id is not None:
            self._selected_related_node_levels, self._selected_related_edge_levels = self._neighbor_context_levels(unit_id)
        self._apply_visual_state()
        if unit_id and unit_id in self._node_items:
            self.centerOn(self._node_items[unit_id])

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
        if self._task_graph and self._scene.items() and not self._has_user_zoomed:
            self.set_task_graph(self._task_graph)

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
        text_item = self._scene.addText(tr(self._language, "task_graph.placeholder.empty"))
        text_item.setDefaultTextColor(QColor("#d8e3f5"))
        text_item.setPos(120, 120)

    def _apply_visual_state(self) -> None:
        for unit_id, item in self._node_items.items():
            in_selected_context = (
                self._selected_unit_id is None
                or unit_id == self._selected_unit_id
                or unit_id in self._selected_related_node_levels
            )
            item.set_dimmed(not in_selected_context)
            item.set_selected(unit_id == self._selected_unit_id)
            item.set_neighbor_level(self._selected_related_node_levels.get(unit_id, 0))

        for edge_id, item in self._edge_items.items():
            in_selected_context = self._selected_unit_id is None or edge_id in self._selected_related_edge_levels
            item.set_dimmed(not in_selected_context)
            item.set_neighbor_level(self._selected_related_edge_levels.get(edge_id, 0))

    def _neighbor_context_levels(self, unit_id: str) -> tuple[dict[str, int], dict[str, int]]:
        if self._task_graph is None:
            return {}, {}
        node_levels: dict[str, int] = {}
        edge_levels: dict[str, int] = {}
        incoming_first: set[str] = set()
        outgoing_first: set[str] = set()

        for source, target in self._display_edges:
            edge_id = self._edge_id(source, target)
            if source == unit_id:
                outgoing_first.add(target)
                self._set_min_level(edge_levels, edge_id, 1)
                if target != unit_id:
                    self._set_min_level(node_levels, target, 1)
            elif target == unit_id:
                incoming_first.add(source)
                self._set_min_level(edge_levels, edge_id, 1)
                if source != unit_id:
                    self._set_min_level(node_levels, source, 1)

        if self._neighbor_depth >= 2:
            for source, target in self._display_edges:
                edge_id = self._edge_id(source, target)
                if source in outgoing_first:
                    self._set_min_level(edge_levels, edge_id, 2)
                    if target != unit_id and target not in outgoing_first:
                        self._set_min_level(node_levels, target, 2)
                if target in incoming_first:
                    self._set_min_level(edge_levels, edge_id, 2)
                    if source != unit_id and source not in incoming_first:
                        self._set_min_level(node_levels, source, 2)

        node_levels.pop(unit_id, None)
        return node_levels, edge_levels

    def _set_min_level(self, levels: dict[str, int], key: str, level: int) -> None:
        current = levels.get(key)
        if current is None or level < current:
            levels[key] = level

    def _compute_positions(self, task_graph: TaskGraph) -> dict[str, QPointF]:
        units_by_depth: dict[int, list[TaskGraphUnit]] = defaultdict(list)
        for unit in task_graph.units:
            units_by_depth[unit.depth].append(unit)

        max_depth = max(units_by_depth.keys(), default=0)
        viewport_width = max(float(self.viewport().width()), 1120.0)
        viewport_height = max(float(self.viewport().height()), 720.0)
        horizontal_origin = 140.0
        vertical_origin = 130.0
        usable_width = max(860.0, viewport_width - horizontal_origin * 2)
        column_spacing = usable_width / max(max_depth, 1) if max_depth > 0 else usable_width
        column_spacing = max(220.0, min(340.0, column_spacing))
        row_spacing = 160.0
        positions: dict[str, QPointF] = {}

        for depth in sorted(units_by_depth):
            column_units = sorted(
                units_by_depth[depth],
                key=lambda unit: (-len(unit.depended_on_by), unit.label.lower(), unit.id),
            )
            total_height = max(0.0, (len(column_units) - 1) * row_spacing)
            start_y = vertical_origin + max(0.0, (viewport_height - 220.0 - total_height) / 2)
            x = horizontal_origin + depth * column_spacing
            for index, unit in enumerate(column_units):
                positions[unit.id] = QPointF(x, start_y + index * row_spacing)
        return positions

    def _edge_id(self, source: str, target: str) -> str:
        return f"taskedge:{source}->{target}"
