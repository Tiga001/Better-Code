from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bettercode.batch_optimize_executor import BatchRunItemStatus
from bettercode.i18n import LanguageCode, tr
from bettercode.models import AgentTaskSuitability, TaskBatch, TaskBatchItem, TaskGraph, TaskGraphUnit, TaskMode, TaskUnitKind
from bettercode.ui.scene_export import export_scene_image


class _TaskBatchCardItem(QGraphicsObject):
    clicked = Signal(str)

    def __init__(self, item: TaskBatchItem, unit: TaskGraphUnit, language: LanguageCode) -> None:
        super().__init__()
        self.item = item
        self.unit = unit
        self._language = language
        self._selected = False
        self._dimmed = False
        self._search_match = False
        self._execution_status: BatchRunItemStatus | None = None
        self._press_pos: QPointF | None = None
        self._width = 188.0
        self._height = 84.0
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(item.label)

    def boundingRect(self) -> QRectF:
        return QRectF(-self._width / 2 - 6, -self._height / 2 - 6, self._width + 12, self._height + 12)

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

    def set_execution_status(self, status: BatchRunItemStatus | None) -> None:
        self._execution_status = status
        self.update()

    def set_language(self, language: LanguageCode) -> None:
        self._language = language
        self.update()

    def paint(self, painter: QPainter, _option, _widget: QWidget | None = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        if self._selected:
            painter.setPen(QPen(QColor("#ffd166"), 6))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(-103, -49, 206, 98), 20, 20)

        fill = self._fill_color()
        border = QColor("#ffe7a3") if self._selected else QColor("#d9e4ff")
        if not self._selected and self._search_match:
            border = QColor("#ffd166")
        painter.setPen(QPen(border, 4 if self._selected else 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(-94, -42, 188, 84), 15, 15)

        title_font = QFont("Helvetica Neue", 10)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor("#f8fbff")))
        title_metrics = QFontMetrics(title_font)
        title = title_metrics.elidedText(self.item.label, Qt.ElideRight, 160)
        painter.drawText(QRectF(-80, -26, 160, 22), Qt.AlignCenter, title)

        meta_font = QFont("Helvetica Neue", 8)
        painter.setFont(meta_font)
        painter.setPen(QPen(QColor("#c6d4ef")))
        meta_metrics = QFontMetrics(meta_font)
        kind = tr(self._language, f"task_graph.kind.{self.unit.kind.value}")
        risk = tr(self._language, f"task.suitability.{self.item.risk.value}")
        painter.drawText(
            QRectF(-80, 0, 160, meta_metrics.height() + 2),
            Qt.AlignCenter,
            meta_metrics.elidedText(kind, Qt.ElideRight, 156),
        )
        painter.drawText(QRectF(-80, 18, 160, meta_metrics.height() + 2), Qt.AlignCenter, f"#{self.item.order_index} · {risk}")
        self._draw_status_badge(painter)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._press_pos is not None:
            drag_distance = (event.pos() - self._press_pos).manhattanLength()
            if drag_distance < QApplication.startDragDistance() and self.boundingRect().contains(event.pos()):
                self.clicked.emit(self.item.unit_id)
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def _fill_color(self) -> QColor:
        if self.unit.kind is TaskUnitKind.CLASS_GROUP:
            return QColor("#118c6a").lighter(120 if self._selected else 100)
        if self.unit.kind is TaskUnitKind.SCRIPT_BLOCK:
            return QColor("#d07a1f").lighter(120 if self._selected else 100)
        if self.unit.kind is TaskUnitKind.CYCLE_GROUP:
            return QColor("#9b4fd8").lighter(120 if self._selected else 100)
        return QColor("#3559d1").lighter(120 if self._selected else 100)

    def _draw_status_badge(self, painter: QPainter) -> None:
        if self._execution_status is None:
            return
        badge_rect = QRectF(-66, 24, 132, 16)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._status_fill_color())
        painter.drawRoundedRect(badge_rect, 8, 8)
        font = QFont("Helvetica Neue", 7)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#f8fbff")))
        metrics = QFontMetrics(font)
        text = tr(self._language, f"batch_run.status.{self._execution_status.value}")
        painter.drawText(badge_rect, Qt.AlignCenter, metrics.elidedText(text, Qt.ElideRight, 122))

    def _status_fill_color(self) -> QColor:
        palette = {
            BatchRunItemStatus.PENDING: QColor("#415468"),
            BatchRunItemStatus.RUNNING: QColor("#ff9640"),
            BatchRunItemStatus.PASSED: QColor("#1d8f63"),
            BatchRunItemStatus.FAILED: QColor("#c45252"),
            BatchRunItemStatus.BLOCKED: QColor("#6b5b3f"),
        }
        return palette[self._execution_status]


class _TaskBatchCanvas(QGraphicsView):
    unit_selected = Signal(str)
    background_clicked = Signal()

    def __init__(self, parent: QWidget | None = None, *, language: LanguageCode = "en") -> None:
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
        self._language = language
        self._batch: TaskBatch | None = None
        self._task_graph: TaskGraph | None = None
        self._cards: dict[str, _TaskBatchCardItem] = {}
        self._phase_bands: list[tuple[int, QRectF, int]] = []
        self._focused_unit_ids: set[str] | None = None
        self._search_match_unit_ids: set[str] = set()
        self._selected_unit_id: str | None = None
        self._execution_status_by_unit: dict[str, BatchRunItemStatus] = {}
        self._has_user_zoomed = False
        self._min_scale = 0.35
        self._max_scale = 3.5
        self._background_press_pos: QPointF | None = None
        self._background_press_started = False

    def set_language(self, language: LanguageCode) -> None:
        self._language = language
        if self._batch is not None:
            self.set_batch(task_graph=self._task_graph, batch=self._batch)

    def set_batch(self, *, task_graph: TaskGraph | None, batch: TaskBatch | None) -> None:
        selected_unit_id = self._selected_unit_id
        self._scene.clear()
        self._cards.clear()
        self._phase_bands.clear()
        self._focused_unit_ids = None
        self._search_match_unit_ids.clear()
        self._task_graph = task_graph
        self._batch = batch
        self._has_user_zoomed = False
        if task_graph is None or batch is None or not batch.items:
            self._render_empty_state()
            return

        units_by_id = {unit.id: unit for unit in task_graph.units}
        positions, phase_bands = self._compute_positions(batch)
        self._phase_bands = phase_bands
        for item in batch.items:
            unit = units_by_id.get(item.unit_id)
            position = positions.get(item.unit_id)
            if unit is None or position is None:
                continue
            card = _TaskBatchCardItem(item, unit, self._language)
            card.setPos(position)
            card.clicked.connect(self.unit_selected.emit)
            self._scene.addItem(card)
            self._cards[item.unit_id] = card

        scene_rect = self._scene.itemsBoundingRect()
        for _phase, band_rect, _count in self._phase_bands:
            scene_rect = scene_rect.united(band_rect)
        self._scene.setSceneRect(scene_rect.adjusted(-100, -100, 100, 100))
        self.select_unit(selected_unit_id)
        self.reset_view()

    def clear_batch(self) -> None:
        self._scene.clear()
        self._batch = None
        self._task_graph = None
        self._cards.clear()
        self._phase_bands.clear()
        self._focused_unit_ids = None
        self._search_match_unit_ids.clear()
        self._selected_unit_id = None
        self._execution_status_by_unit.clear()

    def select_unit(self, unit_id: str | None) -> None:
        if unit_id is not None and unit_id not in self._cards:
            unit_id = None
        self._selected_unit_id = unit_id
        self._apply_visual_state()
        if unit_id and unit_id in self._cards:
            self.centerOn(self._cards[unit_id])

    def reset_view(self) -> None:
        if not self._scene.items():
            return
        self._has_user_zoomed = False
        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._min_scale = min(0.35, self.transform().m11())

    def set_neighbor_depth(self, _neighbor_depth: int) -> None:
        return

    def set_focused_unit_ids(self, unit_ids: set[str] | None) -> None:
        self._focused_unit_ids = unit_ids
        self._apply_visual_state()

    def set_search_match_unit_ids(self, unit_ids: set[str]) -> None:
        self._search_match_unit_ids = unit_ids
        self._apply_visual_state()

    def set_execution_state(self, status_by_unit: dict[str, BatchRunItemStatus]) -> None:
        self._execution_status_by_unit = dict(status_by_unit)
        self._apply_visual_state()

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
        if self._batch is not None and self._scene.items() and not self._has_user_zoomed:
            self.set_batch(task_graph=self._task_graph, batch=self._batch)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        painter.save()
        for phase_index, band_rect, item_count in self._phase_bands:
            if not band_rect.intersects(rect):
                continue
            fill = QColor("#102033" if phase_index % 2 == 0 else "#13263c")
            fill.setAlpha(220)
            painter.setPen(QPen(QColor("#25425f"), 1.5))
            painter.setBrush(fill)
            painter.drawRoundedRect(band_rect, 22, 22)

            title_rect = QRectF(band_rect.left() + 18, band_rect.top() + 12, 220, 30)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#1f3955"))
            painter.drawRoundedRect(title_rect, 12, 12)

            title_font = QFont("Helvetica Neue", 10)
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.setPen(QPen(QColor("#f3f8ff")))
            title = tr(self._language, "task_batch_view.phase.title", index=phase_index)
            painter.drawText(title_rect.adjusted(12, 0, -12, 0), Qt.AlignVCenter | Qt.AlignLeft, title)

            meta_font = QFont("Helvetica Neue", 8)
            painter.setFont(meta_font)
            painter.setPen(QPen(QColor("#9eb5d4")))
            painter.drawText(
                QRectF(title_rect.right() + 12, band_rect.top() + 14, 120, 24),
                Qt.AlignVCenter | Qt.AlignLeft,
                tr(self._language, "task_batch_view.phase.tasks", count=item_count),
            )

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

    def _render_empty_state(self) -> None:
        text_item = self._scene.addText(tr(self._language, "task_batch_view.placeholder.empty"))
        text_item.setDefaultTextColor(QColor("#d8e3f5"))
        text_item.setPos(120, 120)

    def export_image(self, output_path: str) -> None:
        export_scene_image(view=self, scene=self._scene, output_path=output_path)

    def _apply_visual_state(self) -> None:
        active_unit_ids = self._focused_unit_ids
        for unit_id, card in self._cards.items():
            in_selected_context = self._selected_unit_id is None or unit_id == self._selected_unit_id
            in_focus = active_unit_ids is None or unit_id in active_unit_ids or (self._selected_unit_id is not None and in_selected_context)
            card.set_dimmed(not in_focus or not in_selected_context)
            card.set_selected(unit_id == self._selected_unit_id)
            card.set_search_match(unit_id in self._search_match_unit_ids)
            card.set_execution_status(self._execution_status_by_unit.get(unit_id))

    def _compute_positions(self, batch: TaskBatch) -> tuple[dict[str, QPointF], list[tuple[int, QRectF, int]]]:
        items_by_id = {item.id: item for item in batch.items}
        positions: dict[str, QPointF] = {}
        phase_bands: list[tuple[int, QRectF, int]] = []
        viewport_width = max(float(self.viewport().width()), 1120.0)
        horizontal_origin = 130.0
        vertical_origin = 120.0
        usable_width = max(860.0, viewport_width - horizontal_origin * 2)
        column_spacing = 236.0
        wrap_row_spacing = 120.0
        phase_band_spacing = 182.0
        current_y = vertical_origin
        columns_per_row = 12
        band_left = 44.0
        band_width = max(usable_width + 180.0, columns_per_row * column_spacing + 120.0)

        for phase in batch.phases:
            row_items = [
                items_by_id[item_id]
                for item_id in phase.item_ids
                if item_id in items_by_id
            ]
            wrapped_rows = [
                row_items[index : index + columns_per_row]
                for index in range(0, len(row_items), columns_per_row)
            ]
            for row_index, wrapped_items in enumerate(wrapped_rows):
                total_width = max(0.0, (len(wrapped_items) - 1) * column_spacing)
                start_x = horizontal_origin + max(0.0, (usable_width - total_width) / 2)
                y = current_y + row_index * wrap_row_spacing
                for column_index, item in enumerate(wrapped_items):
                    positions[item.unit_id] = QPointF(start_x + column_index * column_spacing, y)
            band_height = 122.0 + max(0, len(wrapped_rows) - 1) * wrap_row_spacing
            phase_bands.append(
                (
                    phase.index,
                    QRectF(band_left, current_y - 72.0, band_width, band_height),
                    len(row_items),
                )
            )
            current_y += phase_band_spacing + max(0, len(wrapped_rows) - 1) * wrap_row_spacing
        return positions, phase_bands


class TaskBatchView(QWidget):
    unit_selected = Signal(str)
    background_clicked = Signal()
    run_phase_requested = Signal(str)
    run_batch_requested = Signal(str)
    stop_requested = Signal()
    mode_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, language: LanguageCode = "en") -> None:
        super().__init__(parent)
        self._language = language
        self._task_graph: TaskGraph | None = None
        self._optimize_batch: TaskBatch | None = None
        self._translate_batch: TaskBatch | None = None
        self._current_mode = TaskMode.OPTIMIZE
        self._is_running = False

        self._optimize_button = QPushButton()
        self._translate_button = QPushButton()
        self._run_phase_button = QPushButton()
        self._run_batch_button = QPushButton()
        self._stop_button = QPushButton()
        self._execution_label = QLabel()
        self._execution_label.setObjectName("detailMeta")
        for button in (self._optimize_button, self._translate_button):
            button.setCheckable(True)
            button.setProperty("modeButton", True)

        self._canvas = _TaskBatchCanvas(language=language)
        self._canvas.unit_selected.connect(self.unit_selected.emit)
        self._canvas.background_clicked.connect(self.background_clicked.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        toggle_bar = QWidget()
        toggle_layout = QHBoxLayout(toggle_bar)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setSpacing(10)
        toggle_layout.addWidget(self._optimize_button)
        toggle_layout.addWidget(self._translate_button)
        toggle_layout.addSpacing(12)
        toggle_layout.addWidget(self._run_phase_button)
        toggle_layout.addWidget(self._run_batch_button)
        toggle_layout.addWidget(self._stop_button)
        toggle_layout.addStretch(1)
        toggle_layout.addWidget(self._execution_label)
        layout.addWidget(toggle_bar)
        layout.addWidget(self._canvas, stretch=1)

        self._optimize_button.clicked.connect(lambda: self._set_mode(TaskMode.OPTIMIZE))
        self._translate_button.clicked.connect(lambda: self._set_mode(TaskMode.TRANSLATE))
        self._run_phase_button.clicked.connect(lambda: self.run_phase_requested.emit(self._current_mode.value))
        self._run_batch_button.clicked.connect(lambda: self.run_batch_requested.emit(self._current_mode.value))
        self._stop_button.clicked.connect(self.stop_requested.emit)
        self._apply_language()
        self._set_execution_state(status_by_unit={}, status_text="", is_running=False)
        self._sync_mode_buttons()

    def set_language(self, language: LanguageCode) -> None:
        self._language = language
        self._canvas.set_language(language)
        self._apply_language()
        self._refresh_canvas()

    def set_batches(
        self,
        *,
        task_graph: TaskGraph | None,
        optimize_batch: TaskBatch | None,
        translate_batch: TaskBatch | None,
    ) -> None:
        self._task_graph = task_graph
        self._optimize_batch = optimize_batch
        self._translate_batch = translate_batch
        self._refresh_canvas()

    def select_unit(self, unit_id: str | None) -> None:
        self._canvas.select_unit(unit_id)
        self._sync_mode_buttons()

    def reset_view(self) -> None:
        self._canvas.reset_view()

    def export_image(self, output_path: str) -> None:
        self._canvas.export_image(output_path)

    def set_neighbor_depth(self, neighbor_depth: int) -> None:
        self._canvas.set_neighbor_depth(neighbor_depth)

    def set_focused_unit_ids(self, unit_ids: set[str] | None) -> None:
        self._canvas.set_focused_unit_ids(unit_ids)

    def set_search_match_unit_ids(self, unit_ids: set[str]) -> None:
        self._canvas.set_search_match_unit_ids(unit_ids)

    def set_execution_state(
        self,
        *,
        status_by_unit: dict[str, BatchRunItemStatus],
        status_text: str,
        is_running: bool,
    ) -> None:
        self._set_execution_state(status_by_unit=status_by_unit, status_text=status_text, is_running=is_running)

    def current_mode(self) -> TaskMode:
        return self._current_mode

    def _set_mode(self, mode: TaskMode) -> None:
        if self._current_mode is mode:
            self._sync_mode_buttons()
            return
        self._current_mode = mode
        self._sync_mode_buttons()
        self._refresh_canvas()
        self.mode_changed.emit(self._current_mode.value)

    def _sync_mode_buttons(self) -> None:
        self._optimize_button.setChecked(self._current_mode is TaskMode.OPTIMIZE)
        self._translate_button.setChecked(self._current_mode is TaskMode.TRANSLATE)
        selected_phase = self._selected_phase_index()
        can_run_optimize = self._current_mode is TaskMode.OPTIMIZE and self._optimize_batch is not None
        self._run_phase_button.setEnabled(can_run_optimize and selected_phase is not None and not self._is_running)
        self._run_batch_button.setEnabled(can_run_optimize and not self._is_running)

    def _refresh_canvas(self) -> None:
        current_batch = self._optimize_batch if self._current_mode is TaskMode.OPTIMIZE else self._translate_batch
        self._canvas.set_batch(task_graph=self._task_graph, batch=current_batch)
        self._optimize_button.setEnabled(self._optimize_batch is not None)
        self._translate_button.setEnabled(self._translate_batch is not None)
        self._sync_mode_buttons()

    def _apply_language(self) -> None:
        self._optimize_button.setText(tr(self._language, "task.mode.optimize"))
        self._translate_button.setText(tr(self._language, "task.mode.translate"))
        self._run_phase_button.setText(tr(self._language, "task_batch_view.button.run_phase"))
        self._run_batch_button.setText(tr(self._language, "task_batch_view.button.run_batch"))
        self._stop_button.setText(tr(self._language, "task_batch_view.button.stop"))

    def _set_execution_state(
        self,
        *,
        status_by_unit: dict[str, BatchRunItemStatus],
        status_text: str,
        is_running: bool,
    ) -> None:
        self._is_running = is_running
        self._canvas.set_execution_state(status_by_unit)
        self._execution_label.setText(status_text or tr(self._language, "task_batch_view.execution.idle"))
        self._stop_button.setEnabled(is_running)
        self._sync_mode_buttons()

    def _selected_phase_index(self) -> int | None:
        batch = self._optimize_batch if self._current_mode is TaskMode.OPTIMIZE else self._translate_batch
        selected_unit_id = self._canvas._selected_unit_id
        if batch is None or selected_unit_id is None:
            return None
        item = next((candidate for candidate in batch.items if candidate.unit_id == selected_unit_id), None)
        return item.phase_index if item is not None else None
