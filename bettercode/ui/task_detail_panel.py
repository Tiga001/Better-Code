from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from bettercode.i18n import LanguageCode, tr
from bettercode.models import AgentTaskSuitability, TaskExecutionPlan, TaskGraph, TaskGraphUnit, TaskMode, TaskUnitKind


class TaskDetailPanel(QWidget):
    export_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None, *, language: LanguageCode = "en") -> None:
        super().__init__(parent)
        self._language = language
        self._task_graph: TaskGraph | None = None
        self._optimize_plan: TaskExecutionPlan | None = None
        self._translate_plan: TaskExecutionPlan | None = None
        self._current_unit: TaskGraphUnit | None = None

        self._title = QLabel()
        self._subtitle = QLabel()
        self._kind_chip = QLabel()
        self._ready_chip = QLabel()
        self._summary = QLabel()
        self._queue_summary = QLabel()
        self._depends_on = self._create_list_widget(max_height=120)
        self._depended_on_by = self._create_list_widget(max_height=120)
        self._blocks = self._create_list_widget(max_height=180)
        self._reasons = self._create_list_widget(max_height=180)
        self._dependency_surface_title = self._section_label("")
        self._depends_on_title = self._subsection_label("")
        self._depended_on_by_title = self._subsection_label("")
        self._blocks_title = self._section_label("")
        self._reasons_title = self._section_label("")
        self._export_optimize_button = QPushButton()
        self._export_translate_button = QPushButton()
        self._export_optimize_button.clicked.connect(lambda: self._emit_export(TaskMode.OPTIMIZE))
        self._export_translate_button.clicked.connect(lambda: self._emit_export(TaskMode.TRANSLATE))

        self._title.setObjectName("detailTitle")
        self._subtitle.setObjectName("detailHelper")
        self._summary.setObjectName("detailMeta")
        self._queue_summary.setObjectName("detailMeta")
        for chip in [self._kind_chip, self._ready_chip]:
            chip.setObjectName("detailChip")
            chip.setAlignment(Qt.AlignCenter)

        content = QWidget()
        content.setObjectName("detailContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)
        content_layout.addWidget(self._build_header_card())
        content_layout.addWidget(
            self._build_two_section_card(
                self._dependency_surface_title,
                (self._depends_on_title, self._depends_on),
                (self._depended_on_by_title, self._depended_on_by),
            )
        )
        content_layout.addWidget(self._build_section_card(self._blocks_title, self._blocks))
        content_layout.addWidget(self._build_section_card(self._reasons_title, self._reasons))
        content_layout.addStretch(1)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("detailScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)

        self._subtitle.setWordWrap(True)
        self._summary.setWordWrap(True)
        self._queue_summary.setWordWrap(True)
        self._apply_static_text()
        self.clear_panel()

    def set_language(self, language: LanguageCode) -> None:
        self._language = language
        self._apply_static_text()
        if self._task_graph is None or self._current_unit is None:
            self.clear_panel()
            return
        self.set_selection(
            task_graph=self._task_graph,
            optimize_plan=self._optimize_plan,
            translate_plan=self._translate_plan,
            unit=self._current_unit,
        )

    def clear_panel(self) -> None:
        self._task_graph = None
        self._optimize_plan = None
        self._translate_plan = None
        self._current_unit = None
        self._title.setText(tr(self._language, "task_detail.title.default"))
        self._subtitle.setText(tr(self._language, "task_detail.subtitle.default"))
        self._kind_chip.setText(tr(self._language, "task_detail.kind.empty"))
        self._ready_chip.setText(tr(self._language, "task_detail.ready.empty"))
        self._apply_chip_style(self._kind_chip, "neutral")
        self._apply_chip_style(self._ready_chip, "neutral")
        self._summary.setText(tr(self._language, "task_detail.summary.empty"))
        self._queue_summary.setText(tr(self._language, "task_detail.queue.empty"))
        self._set_placeholder(self._depends_on, tr(self._language, "task_detail.placeholder.no_dependencies"))
        self._set_placeholder(self._depended_on_by, tr(self._language, "task_detail.placeholder.no_dependents"))
        self._set_placeholder(self._blocks, tr(self._language, "task_detail.placeholder.no_blocks"))
        self._set_placeholder(self._reasons, tr(self._language, "task_detail.placeholder.no_reasons"))
        self._export_optimize_button.setEnabled(False)
        self._export_translate_button.setEnabled(False)

    def set_selection(
        self,
        *,
        task_graph: TaskGraph | None,
        optimize_plan: TaskExecutionPlan | None,
        translate_plan: TaskExecutionPlan | None,
        unit: TaskGraphUnit | None,
    ) -> None:
        if task_graph is None or unit is None:
            self.clear_panel()
            return

        self._task_graph = task_graph
        self._optimize_plan = optimize_plan
        self._translate_plan = translate_plan
        self._current_unit = unit

        self._title.setText(unit.label)
        self._subtitle.setText(tr(self._language, "task_detail.subtitle.selected"))
        self._kind_chip.setText(self._kind_label(unit.kind))
        self._apply_chip_style(self._kind_chip, self._kind_tone(unit.kind))
        self._ready_chip.setText(self._ready_label(unit.ready_to_run))
        self._apply_chip_style(self._ready_chip, "ok" if unit.ready_to_run else "caution")
        self._summary.setText(
            tr(
                self._language,
                "task_detail.summary.value",
                depth=unit.depth,
                blocks=len(unit.block_ids),
                files=len(unit.node_ids),
            )
        )
        self._queue_summary.setText(
            tr(
                self._language,
                "task_detail.queue.value",
                optimize=self._plan_summary(optimize_plan, unit.id),
                translate=self._plan_summary(translate_plan, unit.id),
            )
        )
        self._populate_strings(
            self._depends_on,
            unit.depends_on,
            empty_message=tr(self._language, "task_detail.placeholder.no_dependencies"),
        )
        self._populate_strings(
            self._depended_on_by,
            unit.depended_on_by,
            empty_message=tr(self._language, "task_detail.placeholder.no_dependents"),
        )
        self._populate_strings(
            self._blocks,
            unit.block_ids,
            empty_message=tr(self._language, "task_detail.placeholder.no_blocks"),
        )
        self._populate_strings(
            self._reasons,
            unit.reasons,
            empty_message=tr(self._language, "task_detail.placeholder.no_reasons"),
        )
        self._export_optimize_button.setEnabled(optimize_plan is not None)
        self._export_translate_button.setEnabled(translate_plan is not None)

    def _emit_export(self, mode: TaskMode) -> None:
        if self._current_unit is None:
            return
        self.export_requested.emit(self._current_unit.id, mode.value)

    def _apply_static_text(self) -> None:
        self._dependency_surface_title.setText(tr(self._language, "task_detail.section.dependencies"))
        self._depends_on_title.setText(tr(self._language, "task_detail.section.depends_on"))
        self._depended_on_by_title.setText(tr(self._language, "task_detail.section.depended_on_by"))
        self._blocks_title.setText(tr(self._language, "task_detail.section.blocks"))
        self._reasons_title.setText(tr(self._language, "task_detail.section.reasons"))
        self._export_optimize_button.setText(tr(self._language, "task_detail.button.export_optimize"))
        self._export_translate_button.setText(tr(self._language, "task_detail.button.export_translate"))

    def _plan_summary(self, plan: TaskExecutionPlan | None, unit_id: str) -> str:
        if plan is None:
            return "-"
        item = next((candidate for candidate in plan.items if candidate.unit_id == unit_id), None)
        if item is None:
            return "-"
        return tr(
            self._language,
            "task_detail.queue.item",
            index=item.order_index,
            risk=self._risk_label(item.risk),
        )

    def _risk_label(self, risk: AgentTaskSuitability) -> str:
        return tr(self._language, f"task.suitability.{risk.value}")

    def _kind_label(self, kind: TaskUnitKind) -> str:
        return tr(self._language, f"task_detail.kind.{kind.value}")

    def _kind_tone(self, kind: TaskUnitKind) -> str:
        if kind is TaskUnitKind.CLASS_GROUP:
            return "leaf"
        if kind is TaskUnitKind.CYCLE_GROUP:
            return "script"
        return "file"

    def _ready_label(self, ready: bool) -> str:
        return tr(self._language, "task_detail.ready.true" if ready else "task_detail.ready.false")

    def _create_list_widget(self, *, max_height: int) -> QListWidget:
        widget = QListWidget()
        widget.setObjectName("detailList")
        widget.setMaximumHeight(max_height)
        return widget

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("detailSectionTitle")
        return label

    def _subsection_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("detailSubsectionTitle")
        return label

    def _build_header_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailHeaderCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self._title)
        status_row = QWidget()
        status_row_layout = QHBoxLayout(status_row)
        status_row_layout.setContentsMargins(0, 0, 0, 0)
        status_row_layout.setSpacing(8)
        status_row_layout.addWidget(self._kind_chip)
        status_row_layout.addWidget(self._ready_chip)
        status_row_layout.addStretch(1)
        layout.addWidget(status_row)
        layout.addWidget(self._subtitle)
        layout.addWidget(self._summary)
        layout.addWidget(self._queue_summary)
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        button_layout.addWidget(self._export_optimize_button)
        button_layout.addWidget(self._export_translate_button)
        layout.addWidget(button_row)
        return frame

    def _build_section_card(self, title_label: QLabel, widget: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(title_label)
        layout.addWidget(widget)
        return frame

    def _build_two_section_card(
        self,
        title_label: QLabel,
        first: tuple[QLabel, QWidget],
        second: tuple[QLabel, QWidget],
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(title_label)
        layout.addWidget(first[0])
        layout.addWidget(first[1])
        layout.addWidget(second[0])
        layout.addWidget(second[1])
        return frame

    def _populate_strings(self, widget: QListWidget, items: list[str], *, empty_message: str) -> None:
        if not items:
            self._set_placeholder(widget, empty_message)
            return
        widget.clear()
        for item in items:
            widget.addItem(QListWidgetItem(item))

    def _set_placeholder(self, widget: QListWidget, message: str) -> None:
        widget.clear()
        widget.addItem(QListWidgetItem(message))

    def _apply_chip_style(self, label: QLabel, tone: str) -> None:
        styles = {
            "neutral": "background:#243344;color:#d6e0ef;border:1px solid #415468;",
            "file": "background:#213a67;color:#d4e1ff;border:1px solid #517ae8;",
            "leaf": "background:#18473f;color:#b9f4dd;border:1px solid #34c38f;",
            "script": "background:#4f234e;color:#f4ccff;border:1px solid #c86dff;",
            "ok": "background:#103629;color:#9ef0c8;border:1px solid #34c38f;",
            "caution": "background:#4b3512;color:#ffdca8;border:1px solid #f2a93b;",
        }
        label.setStyleSheet(styles[tone])
