from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bettercode.batch_optimize_executor import BatchRunItemStatus, BatchRunReport
from bettercode.i18n import LanguageCode, tr
from bettercode.optimization_history import OptimizationHistoryEntry
from bettercode.models import ProjectGraph, TaskBatch, TaskExecutionPlan, TaskGraph, TaskGraphUnit, TaskUnitKind
from bettercode.task_graph import build_task_unit_source_snippets


class TaskDetailPanel(QWidget):
    assign_unit_requested = Signal(str, str)
    assign_phase_requested = Signal(str, str)
    optimization_history_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None, *, language: LanguageCode = "en") -> None:
        super().__init__(parent)
        self._language = language
        self._view_mode = "tasks"
        self._project_graph: ProjectGraph | None = None
        self._task_graph: TaskGraph | None = None
        self._optimize_plan: TaskExecutionPlan | None = None
        self._translate_plan: TaskExecutionPlan | None = None
        self._optimize_batch: TaskBatch | None = None
        self._translate_batch: TaskBatch | None = None
        self._current_unit: TaskGraphUnit | None = None
        self._optimization_history_by_unit: dict[str, list[OptimizationHistoryEntry]] = {}
        self._batch_run_report: BatchRunReport | None = None
        self._batch_run_status_by_unit: dict[str, BatchRunItemStatus] = {}
        self._batch_run_current_unit_id: str | None = None

        self._title = QLabel()
        self._subtitle = QLabel()
        self._kind_chip = QLabel()
        self._ready_chip = QLabel()
        self._summary = QLabel()
        self._phase_summary = QLabel()
        self._optimization_status = QLabel()
        self._depends_on = self._create_list_widget(max_height=120)
        self._depended_on_by = self._create_list_widget(max_height=120)
        self._context_depends_on = self._create_list_widget(max_height=120)
        self._context_depended_on_by = self._create_list_widget(max_height=120)
        self._blocks = self._create_list_widget(max_height=180)
        self._reasons = self._create_list_widget(max_height=180)
        self._optimization_history = self._create_list_widget(max_height=180)
        self._source_preview = QTextEdit()
        self._execution_title = self._section_label("")
        self._execution_batch_status = QLabel()
        self._execution_unit_status = QLabel()
        self._execution_current_task = QLabel()
        self._assignment_title = self._section_label("")
        self._assign_optimize_button = QPushButton()
        self._assign_translate_button = QPushButton()
        self._assign_optimize_phase_button = QPushButton()
        self._assign_translate_phase_button = QPushButton()
        self._open_history_button = QPushButton()
        self._blocking_surface_title = self._section_label("")
        self._context_surface_title = self._section_label("")
        self._depends_on_title = self._subsection_label("")
        self._depended_on_by_title = self._subsection_label("")
        self._context_depends_on_title = self._subsection_label("")
        self._context_depended_on_by_title = self._subsection_label("")
        self._blocks_title = self._section_label("")
        self._reasons_title = self._section_label("")
        self._optimization_history_title = self._section_label("")
        self._source_preview_title = self._section_label("")

        self._title.setObjectName("detailTitle")
        self._subtitle.setObjectName("detailHelper")
        self._summary.setObjectName("detailMeta")
        self._phase_summary.setObjectName("detailMeta")
        self._optimization_status.setObjectName("detailMeta")
        self._source_preview.setObjectName("detailPreview")
        self._source_preview.setReadOnly(True)
        self._source_preview.setMinimumHeight(260)
        for label in (self._execution_batch_status, self._execution_unit_status, self._execution_current_task):
            label.setObjectName("detailMeta")
            label.setWordWrap(True)
        for button in (
            self._assign_optimize_button,
            self._assign_translate_button,
            self._assign_optimize_phase_button,
            self._assign_translate_phase_button,
            self._open_history_button,
        ):
            button.setCursor(Qt.PointingHandCursor)
        for chip in [self._kind_chip, self._ready_chip]:
            chip.setObjectName("detailChip")
            chip.setAlignment(Qt.AlignCenter)

        content = QWidget()
        content.setObjectName("detailContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)
        content_layout.addWidget(self._build_header_card())
        content_layout.addWidget(self._build_execution_card())
        content_layout.addWidget(self._build_assignment_card())
        content_layout.addWidget(
            self._build_two_section_card(
                self._blocking_surface_title,
                (self._depends_on_title, self._depends_on),
                (self._depended_on_by_title, self._depended_on_by),
            )
        )
        content_layout.addWidget(
            self._build_two_section_card(
                self._context_surface_title,
                (self._context_depends_on_title, self._context_depends_on),
                (self._context_depended_on_by_title, self._context_depended_on_by),
            )
        )
        content_layout.addWidget(self._build_section_card(self._blocks_title, self._blocks))
        content_layout.addWidget(self._build_section_card(self._reasons_title, self._reasons))
        content_layout.addWidget(self._build_optimization_history_card())
        content_layout.addWidget(self._build_section_card(self._source_preview_title, self._source_preview))
        content_layout.addStretch(1)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("detailScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)

        self._assign_optimize_button.clicked.connect(lambda: self._emit_assign_unit("optimize"))
        self._assign_translate_button.clicked.connect(lambda: self._emit_assign_unit("translate"))
        self._assign_optimize_phase_button.clicked.connect(lambda: self._emit_assign_phase("optimize"))
        self._assign_translate_phase_button.clicked.connect(lambda: self._emit_assign_phase("translate"))
        self._open_history_button.clicked.connect(self._emit_open_history)
        self._optimization_history.itemDoubleClicked.connect(lambda _item: self._emit_open_history())
        self._subtitle.setWordWrap(True)
        self._summary.setWordWrap(True)
        self._phase_summary.setWordWrap(True)
        self._optimization_status.setWordWrap(True)
        self._apply_static_text()
        self.clear_panel()

    def set_language(self, language: LanguageCode) -> None:
        self._language = language
        self._apply_static_text()
        if self._task_graph is None or self._current_unit is None:
            self.clear_panel()
            return
        self.set_selection(
            project_graph=self._project_graph,
            task_graph=self._task_graph,
            optimize_plan=self._optimize_plan,
            translate_plan=self._translate_plan,
            optimize_batch=self._optimize_batch,
            translate_batch=self._translate_batch,
            optimization_history_by_unit=self._optimization_history_by_unit,
            batch_run_report=self._batch_run_report,
            batch_run_status_by_unit=self._batch_run_status_by_unit,
            batch_run_current_unit_id=self._batch_run_current_unit_id,
            unit=self._current_unit,
        )

    def clear_panel(self) -> None:
        self._project_graph = None
        self._task_graph = None
        self._optimize_plan = None
        self._translate_plan = None
        self._optimize_batch = None
        self._translate_batch = None
        self._current_unit = None
        self._optimization_history_by_unit = {}
        self._batch_run_report = None
        self._batch_run_status_by_unit = {}
        self._batch_run_current_unit_id = None
        self._title.setText(tr(self._language, "task_detail.title.default"))
        self._subtitle.setText(
            tr(self._language, "task_detail.subtitle.batch_default")
            if self._view_mode == "batches"
            else tr(self._language, "task_detail.subtitle.default")
        )
        self._kind_chip.setText(tr(self._language, "task_detail.kind.empty"))
        self._ready_chip.setText(tr(self._language, "task_detail.ready.empty"))
        self._apply_chip_style(self._kind_chip, "neutral")
        self._apply_chip_style(self._ready_chip, "neutral")
        self._summary.setText(tr(self._language, "task_detail.summary.empty"))
        self._phase_summary.setText(tr(self._language, "task_detail.phase.empty"))
        self._execution_batch_status.setText(tr(self._language, "task_detail.execution.batch_idle"))
        self._execution_unit_status.setText(tr(self._language, "task_detail.execution.unit_idle"))
        self._execution_current_task.setText(tr(self._language, "task_detail.execution.current_task.empty"))
        self._optimization_status.setText(tr(self._language, "task_detail.optimization.empty"))
        self._set_placeholder(self._depends_on, tr(self._language, "task_detail.placeholder.no_dependencies"))
        self._set_placeholder(self._depended_on_by, tr(self._language, "task_detail.placeholder.no_dependents"))
        self._set_placeholder(self._context_depends_on, tr(self._language, "task_detail.placeholder.no_context_dependencies"))
        self._set_placeholder(self._context_depended_on_by, tr(self._language, "task_detail.placeholder.no_context_dependents"))
        self._set_placeholder(self._blocks, tr(self._language, "task_detail.placeholder.no_blocks"))
        self._set_placeholder(self._reasons, tr(self._language, "task_detail.placeholder.no_reasons"))
        self._set_placeholder(self._optimization_history, tr(self._language, "task_detail.placeholder.no_optimization_history"))
        self._source_preview.setPlainText(tr(self._language, "task_detail.placeholder.no_source_preview"))
        self._open_history_button.setEnabled(False)
        self._sync_assignment_controls()

    def set_view_mode(self, view_mode: str) -> None:
        self._view_mode = view_mode
        self._sync_assignment_controls()

    def set_selection(
        self,
        *,
        project_graph: ProjectGraph | None,
        task_graph: TaskGraph | None,
        optimize_plan: TaskExecutionPlan | None,
        translate_plan: TaskExecutionPlan | None,
        optimize_batch: TaskBatch | None,
        translate_batch: TaskBatch | None,
        optimization_history_by_unit: dict[str, list[OptimizationHistoryEntry]] | None,
        batch_run_report: BatchRunReport | None,
        batch_run_status_by_unit: dict[str, BatchRunItemStatus] | None,
        batch_run_current_unit_id: str | None,
        unit: TaskGraphUnit | None,
    ) -> None:
        if project_graph is None or task_graph is None or unit is None:
            self.clear_panel()
            return

        self._project_graph = project_graph
        self._task_graph = task_graph
        self._optimize_plan = optimize_plan
        self._translate_plan = translate_plan
        self._optimize_batch = optimize_batch
        self._translate_batch = translate_batch
        self._optimization_history_by_unit = dict(optimization_history_by_unit or {})
        self._batch_run_report = batch_run_report
        self._batch_run_status_by_unit = dict(batch_run_status_by_unit or {})
        self._batch_run_current_unit_id = batch_run_current_unit_id
        self._current_unit = unit

        self._title.setText(unit.label)
        self._subtitle.setText(
            tr(self._language, "task_detail.subtitle.batch_selected")
            if self._view_mode == "batches"
            else tr(self._language, "task_detail.subtitle.selected")
        )
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
        self._phase_summary.setText(
            tr(
                self._language,
                "task_detail.phase.value",
                optimize=self._batch_summary(optimize_batch, unit.id),
                translate=self._batch_summary(translate_batch, unit.id),
            )
        )
        self._populate_execution_state(unit.id)
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
            self._context_depends_on,
            unit.context_depends_on,
            empty_message=tr(self._language, "task_detail.placeholder.no_context_dependencies"),
        )
        self._populate_strings(
            self._context_depended_on_by,
            unit.context_depended_on_by,
            empty_message=tr(self._language, "task_detail.placeholder.no_context_dependents"),
        )
        self._populate_strings(
            self._blocks,
            unit.block_ids,
            empty_message=tr(self._language, "task_detail.placeholder.no_blocks"),
        )
        self._populate_strings(
            self._reasons,
            [self._localize_reason(reason) for reason in unit.reasons],
            empty_message=tr(self._language, "task_detail.placeholder.no_reasons"),
        )
        self._populate_optimization_history(unit.id)
        self._source_preview.setPlainText(self._build_source_preview(project_graph, unit.id))
        self._sync_assignment_controls()

    def _apply_static_text(self) -> None:
        self._assignment_title.setText(tr(self._language, "task_detail.section.assignment"))
        self._execution_title.setText(tr(self._language, "task_detail.section.execution"))
        self._blocking_surface_title.setText(tr(self._language, "task_detail.section.dependencies"))
        self._depends_on_title.setText(tr(self._language, "task_detail.section.depends_on"))
        self._depended_on_by_title.setText(tr(self._language, "task_detail.section.depended_on_by"))
        self._context_surface_title.setText(tr(self._language, "task_detail.section.context_dependencies"))
        self._context_depends_on_title.setText(tr(self._language, "task_detail.section.context_depends_on"))
        self._context_depended_on_by_title.setText(tr(self._language, "task_detail.section.context_depended_on_by"))
        self._blocks_title.setText(tr(self._language, "task_detail.section.blocks"))
        self._reasons_title.setText(tr(self._language, "task_detail.section.reasons"))
        self._optimization_history_title.setText(tr(self._language, "task_detail.section.optimization_history"))
        self._source_preview_title.setText(tr(self._language, "task_detail.section.source_preview"))
        self._assign_optimize_button.setText(tr(self._language, "task_detail.button.assign_optimize"))
        self._assign_translate_button.setText(tr(self._language, "task_detail.button.assign_translate"))
        self._assign_optimize_phase_button.setText(tr(self._language, "task_detail.button.assign_optimize_phase"))
        self._assign_translate_phase_button.setText(tr(self._language, "task_detail.button.assign_translate_phase"))
        self._open_history_button.setText(tr(self._language, "task_detail.button.open_optimization_history"))
        if self._current_unit is None:
            self._optimization_status.setText(tr(self._language, "task_detail.optimization.empty"))
            self._set_placeholder(
                self._optimization_history,
                tr(self._language, "task_detail.placeholder.no_optimization_history"),
            )
        else:
            self._populate_optimization_history(self._current_unit.id)
        self._sync_assignment_controls()

    def _batch_summary(self, batch: TaskBatch | None, unit_id: str) -> str:
        if batch is None:
            return "-"
        item = next((candidate for candidate in batch.items if candidate.unit_id == unit_id), None)
        if item is None:
            return "-"
        return tr(
            self._language,
            "task_detail.phase.item",
            phase=item.phase_index,
            index=item.order_index,
        )

    def _risk_label(self, risk: AgentTaskSuitability) -> str:
        return tr(self._language, f"task.suitability.{risk.value}")

    def _kind_label(self, kind: TaskUnitKind) -> str:
        return tr(self._language, f"task_detail.kind.{kind.value}")

    def _kind_tone(self, kind: TaskUnitKind) -> str:
        if kind is TaskUnitKind.CLASS_GROUP:
            return "leaf"
        if kind is TaskUnitKind.SCRIPT_BLOCK:
            return "script"
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
        layout.addWidget(self._phase_summary)
        layout.addWidget(self._optimization_status)
        return frame

    def _build_assignment_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self._assignment_title)

        unit_row = QWidget()
        unit_row_layout = QHBoxLayout(unit_row)
        unit_row_layout.setContentsMargins(0, 0, 0, 0)
        unit_row_layout.setSpacing(8)
        unit_row_layout.addWidget(self._assign_optimize_button)
        unit_row_layout.addWidget(self._assign_translate_button)

        phase_row = QWidget()
        phase_row_layout = QHBoxLayout(phase_row)
        phase_row_layout.setContentsMargins(0, 0, 0, 0)
        phase_row_layout.setSpacing(8)
        phase_row_layout.addWidget(self._assign_optimize_phase_button)
        phase_row_layout.addWidget(self._assign_translate_phase_button)

        self._unit_assignment_row = unit_row
        self._phase_assignment_row = phase_row
        self._assignment_card = frame
        layout.addWidget(unit_row)
        layout.addWidget(phase_row)
        return frame

    def _build_execution_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self._execution_title)
        layout.addWidget(self._execution_batch_status)
        layout.addWidget(self._execution_unit_status)
        layout.addWidget(self._execution_current_task)
        self._execution_card = frame
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

    def _build_optimization_history_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self._optimization_history_title)
        layout.addWidget(self._optimization_history)
        layout.addWidget(self._open_history_button, alignment=Qt.AlignRight)
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

    def _build_source_preview(self, project_graph: ProjectGraph, unit_id: str) -> str:
        snippets = build_task_unit_source_snippets(project_graph, unit_id=unit_id)
        if not snippets:
            return tr(self._language, "task_detail.placeholder.no_source_preview")
        divider = "\n\n" + ("-" * 48) + "\n\n"
        return divider.join(snippets)

    def _populate_optimization_history(self, unit_id: str) -> None:
        entries = self._optimization_history_by_unit.get(unit_id, [])
        if not entries:
            self._optimization_status.setText(tr(self._language, "task_detail.optimization.empty"))
            self._set_placeholder(
                self._optimization_history,
                tr(self._language, "task_detail.placeholder.no_optimization_history"),
            )
            self._open_history_button.setEnabled(False)
            return

        latest = entries[0]
        latest_summary = tr(
            self._language,
            "task_detail.optimization.latest",
            status=self._optimization_status_label(latest),
            count=len(entries),
            timestamp=self._format_timestamp(latest.created_at_ms),
        )
        if latest.failure_category is not None:
            latest_summary += "\n" + tr(
                self._language,
                "task_detail.optimization.failure",
                category=tr(self._language, f"optimize_failure.{latest.failure_category.value}"),
            )
        self._optimization_status.setText(latest_summary)
        self._optimization_history.clear()
        for entry in entries:
            item = QListWidgetItem(
                tr(
                    self._language,
                    "task_detail.optimization.history_item",
                    timestamp=self._format_timestamp(entry.created_at_ms),
                    status=self._optimization_status_label(entry),
                    validation=entry.validation_status.value,
                    changed_files=entry.changed_files,
                )
            )
            item.setData(Qt.UserRole, entry.output_dir)
            self._optimization_history.addItem(item)
        self._optimization_history.setCurrentRow(0)
        self._open_history_button.setEnabled(True)

    def _populate_execution_state(self, unit_id: str) -> None:
        if self._batch_run_report is None:
            self._execution_batch_status.setText(tr(self._language, "task_detail.execution.batch_idle"))
        else:
            scope_label = (
                tr(self._language, "task_detail.execution.scope.phase", phase=self._batch_run_report.selected_phase)
                if self._batch_run_report.selected_phase is not None
                else tr(self._language, "task_detail.execution.scope.all")
            )
            self._execution_batch_status.setText(
                tr(
                    self._language,
                    "task_detail.execution.batch_value",
                    status=tr(self._language, f"batch_run.status.{self._batch_run_report.status.value}"),
                    scope=scope_label,
                )
            )

        unit_status = self._batch_run_status_by_unit.get(unit_id)
        if unit_status is None:
            self._execution_unit_status.setText(tr(self._language, "task_detail.execution.unit_idle"))
        else:
            self._execution_unit_status.setText(
                tr(
                    self._language,
                    "task_detail.execution.unit_value",
                    status=tr(self._language, f"batch_run.status.{unit_status.value}"),
                )
            )

        if self._batch_run_current_unit_id is None or self._task_graph is None:
            self._execution_current_task.setText(tr(self._language, "task_detail.execution.current_task.empty"))
            return
        active_unit = next(
            (candidate for candidate in self._task_graph.units if candidate.id == self._batch_run_current_unit_id),
            None,
        )
        if active_unit is None:
            self._execution_current_task.setText(tr(self._language, "task_detail.execution.current_task.empty"))
            return
        self._execution_current_task.setText(
            tr(self._language, "task_detail.execution.current_task.value", label=active_unit.label)
        )

    def _localize_reason(self, reason: str) -> str:
        direct_map = {
            "class methods are grouped into one task unit": "task_reason.class_group_seed",
            "module-scope execution statements are grouped into one task unit": "task_reason.script_block_seed",
            "top-level function is a standalone task unit": "task_reason.function_seed",
            "mutual internal dependencies merged these blocks into one task group": "task_reason.cycle_merge",
        }
        key = direct_map.get(reason)
        if key is not None:
            return tr(self._language, key)
        return reason

    def _optimization_status_label(self, entry: OptimizationHistoryEntry) -> str:
        label = entry.status.value
        if entry.has_apply_result and not entry.has_rollback_result:
            label += f" · {tr(self._language, 'task_detail.optimization.applied')}"
        elif entry.has_rollback_result:
            label += f" · {tr(self._language, 'task_detail.optimization.rolled_back')}"
        return label

    def _format_timestamp(self, created_at_ms: int) -> str:
        return datetime.fromtimestamp(created_at_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")

    def _emit_assign_unit(self, mode_value: str) -> None:
        if self._current_unit is None:
            return
        self.assign_unit_requested.emit(self._current_unit.id, mode_value)

    def _emit_assign_phase(self, mode_value: str) -> None:
        if self._current_unit is None:
            return
        self.assign_phase_requested.emit(self._current_unit.id, mode_value)

    def _emit_open_history(self) -> None:
        item = self._optimization_history.currentItem()
        if item is None or self._current_unit is None:
            return
        output_dir = item.data(Qt.UserRole)
        if not isinstance(output_dir, str) or not output_dir.strip():
            return
        self.optimization_history_requested.emit(self._current_unit.id, output_dir)

    def _sync_assignment_controls(self) -> None:
        has_unit = self._current_unit is not None
        is_batch_view = self._view_mode == "batches"
        self._execution_card.setVisible(is_batch_view)
        self._assignment_card.setVisible(not is_batch_view)
        self._unit_assignment_row.setVisible(not is_batch_view)
        self._phase_assignment_row.setVisible(is_batch_view)

        self._assign_optimize_button.setEnabled(has_unit)
        self._assign_translate_button.setEnabled(has_unit)
        self._assign_optimize_phase_button.setEnabled(
            has_unit and self._batch_contains_unit(self._optimize_batch, self._current_unit.id if self._current_unit else None)
        )
        self._assign_translate_phase_button.setEnabled(
            has_unit and self._batch_contains_unit(self._translate_batch, self._current_unit.id if self._current_unit else None)
        )

    def _batch_contains_unit(self, batch: TaskBatch | None, unit_id: str | None) -> bool:
        if batch is None or unit_id is None:
            return False
        return any(item.unit_id == unit_id for item in batch.items)

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
