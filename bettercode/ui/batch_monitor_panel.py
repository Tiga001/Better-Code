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

from bettercode.batch_optimize_executor import BatchRunItemRecord, BatchRunItemStatus, BatchRunReport
from bettercode.i18n import LanguageCode, tr
from bettercode.models import TaskBatch, TaskGraph, TaskMode
from bettercode.optimization_history import OptimizationHistoryEntry
from bettercode.optimize_executor import OptimizationStatus


class BatchMonitorPanel(QWidget):
    optimization_history_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None, *, language: LanguageCode = "en") -> None:
        super().__init__(parent)
        self._language = language
        self._task_graph: TaskGraph | None = None
        self._batch: TaskBatch | None = None
        self._report: BatchRunReport | None = None
        self._mode: TaskMode = TaskMode.OPTIMIZE
        self._current_running_unit_id: str | None = None
        self._optimization_history_by_unit: dict[str, list[OptimizationHistoryEntry]] = {}

        self._title = QLabel()
        self._subtitle = QLabel()
        self._summary = QLabel()
        self._progress = QLabel()
        self._current_task = QLabel()
        self._completed_title = QLabel()
        self._issues_title = QLabel()
        self._completed_list = self._create_list_widget()
        self._issues_list = self._create_list_widget()
        self._open_completed_button = QPushButton()
        self._open_issue_button = QPushButton()

        self._title.setObjectName("detailTitle")
        self._subtitle.setObjectName("detailHelper")
        for label in (self._summary, self._progress, self._current_task):
            label.setObjectName("detailMeta")
            label.setWordWrap(True)

        content = QWidget()
        content.setObjectName("detailContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)
        content_layout.addWidget(self._build_header_card())
        content_layout.addWidget(
            self._build_list_card(
                self._completed_title,
                self._completed_list,
                self._open_completed_button,
            )
        )
        content_layout.addWidget(
            self._build_list_card(
                self._issues_title,
                self._issues_list,
                self._open_issue_button,
            )
        )
        content_layout.addStretch(1)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("detailScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)

        self._open_completed_button.clicked.connect(lambda: self._emit_open_history(self._completed_list))
        self._open_issue_button.clicked.connect(lambda: self._emit_open_history(self._issues_list))
        self._completed_list.itemDoubleClicked.connect(lambda _item: self._emit_open_history(self._completed_list))
        self._issues_list.itemDoubleClicked.connect(lambda _item: self._emit_open_history(self._issues_list))
        self._completed_list.itemSelectionChanged.connect(self._sync_open_buttons)
        self._issues_list.itemSelectionChanged.connect(self._sync_open_buttons)

        self._apply_static_text()
        self.clear_panel()

    def set_language(self, language: LanguageCode) -> None:
        self._language = language
        self._apply_static_text()
        self.set_context(
            task_graph=self._task_graph,
            batch=self._batch,
            report=self._report,
            mode=self._mode,
            current_running_unit_id=self._current_running_unit_id,
            optimization_history_by_unit=self._optimization_history_by_unit,
        )

    def clear_panel(self) -> None:
        self._task_graph = None
        self._batch = None
        self._report = None
        self._current_running_unit_id = None
        self._optimization_history_by_unit = {}
        self._title.setText(tr(self._language, "batch_monitor.title"))
        self._subtitle.setText(tr(self._language, "batch_monitor.subtitle.idle"))
        self._summary.setText(tr(self._language, "batch_monitor.summary.empty"))
        self._progress.setText(tr(self._language, "batch_monitor.progress.empty"))
        self._current_task.setText(tr(self._language, "batch_monitor.current_task.empty"))
        self._set_placeholder(self._completed_list, tr(self._language, "batch_monitor.placeholder.no_completed"))
        self._set_placeholder(self._issues_list, tr(self._language, "batch_monitor.placeholder.no_issues"))
        self._sync_open_buttons()

    def set_context(
        self,
        *,
        task_graph: TaskGraph | None,
        batch: TaskBatch | None,
        report: BatchRunReport | None,
        mode: TaskMode,
        current_running_unit_id: str | None,
        optimization_history_by_unit: dict[str, list[OptimizationHistoryEntry]] | None = None,
    ) -> None:
        self._task_graph = task_graph
        self._batch = batch
        self._report = report
        self._mode = mode
        self._current_running_unit_id = current_running_unit_id
        self._optimization_history_by_unit = dict(optimization_history_by_unit or {})

        self._title.setText(tr(self._language, "batch_monitor.title"))
        self._subtitle.setText(tr(self._language, f"batch_monitor.subtitle.{mode.value}"))

        if batch is None:
            self._summary.setText(tr(self._language, "batch_monitor.summary.empty"))
            self._progress.setText(tr(self._language, "batch_monitor.progress.empty"))
            self._current_task.setText(tr(self._language, "batch_monitor.current_task.empty"))
            self._set_placeholder(self._completed_list, tr(self._language, "batch_monitor.placeholder.no_completed"))
            self._set_placeholder(self._issues_list, tr(self._language, "batch_monitor.placeholder.no_issues"))
            self._sync_open_buttons()
            return

        self._summary.setText(
            tr(
                self._language,
                "batch_monitor.summary.value",
                tasks=len(batch.items),
                phases=len(batch.phases),
            )
        )
        self._progress.setText(self._progress_summary(batch, report))
        self._current_task.setText(self._current_task_summary(report, current_running_unit_id))
        completed_items, issue_items = self._history_lists(batch, report)
        self._populate_report_list(
            self._completed_list,
            completed_items,
            empty_message=tr(self._language, "batch_monitor.placeholder.no_completed"),
        )
        self._populate_report_list(
            self._issues_list,
            issue_items,
            empty_message=tr(self._language, "batch_monitor.placeholder.no_issues"),
        )
        self._sync_open_buttons()

    def _apply_static_text(self) -> None:
        self._completed_title.setText(tr(self._language, "batch_monitor.section.completed"))
        self._issues_title.setText(tr(self._language, "batch_monitor.section.issues"))
        self._open_completed_button.setText(tr(self._language, "batch_monitor.button.open_completed"))
        self._open_issue_button.setText(tr(self._language, "batch_monitor.button.open_issue"))

    def _build_header_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailHeaderCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addWidget(self._summary)
        layout.addWidget(self._progress)
        layout.addWidget(self._current_task)
        return frame

    def _build_list_card(self, title_label: QLabel, widget: QListWidget, button: QPushButton) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        title_label.setObjectName("detailSectionTitle")
        layout.addWidget(title_label)
        layout.addWidget(widget)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addStretch(1)
        row_layout.addWidget(button)
        layout.addWidget(row)
        return frame

    def _create_list_widget(self) -> QListWidget:
        widget = QListWidget()
        widget.setObjectName("detailList")
        widget.setMaximumHeight(220)
        return widget

    def _progress_summary(self, batch: TaskBatch, report: BatchRunReport | None) -> str:
        if report is None:
            return tr(self._language, "batch_monitor.progress.not_started")
        counts = {
            BatchRunItemStatus.PENDING: 0,
            BatchRunItemStatus.RUNNING: 0,
            BatchRunItemStatus.PASSED: 0,
            BatchRunItemStatus.FAILED: 0,
            BatchRunItemStatus.BLOCKED: 0,
        }
        for item in report.items:
            counts[item.status] += 1
        return tr(
            self._language,
            "batch_monitor.progress.value",
            status=tr(self._language, f"batch_run.status.{report.status.value}"),
            pending=counts[BatchRunItemStatus.PENDING],
            running=counts[BatchRunItemStatus.RUNNING],
            passed=counts[BatchRunItemStatus.PASSED],
            failed=counts[BatchRunItemStatus.FAILED],
            blocked=counts[BatchRunItemStatus.BLOCKED],
        )

    def _current_task_summary(self, report: BatchRunReport | None, current_running_unit_id: str | None) -> str:
        if report is None or current_running_unit_id is None:
            return tr(self._language, "batch_monitor.current_task.empty")
        running_item = next((item for item in report.items if item.unit_id == current_running_unit_id), None)
        if running_item is None:
            return tr(self._language, "batch_monitor.current_task.empty")
        return tr(
            self._language,
            "batch_monitor.current_task.value",
            label=running_item.label,
            phase=running_item.phase_index,
        )

    def _populate_report_list(
        self,
        widget: QListWidget,
        items: list[BatchRunItemRecord],
        *,
        empty_message: str,
    ) -> None:
        if not items:
            self._set_placeholder(widget, empty_message)
            return
        widget.clear()
        for entry in items:
            text = tr(
                self._language,
                "batch_monitor.item.value",
                label=entry.label,
                status=tr(self._language, f"batch_run.status.{entry.status.value}"),
                phase=entry.phase_index,
            )
            if entry.error:
                text += "\n" + entry.error
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, (entry.unit_id, entry.output_dir or ""))
            widget.addItem(item)
        widget.setCurrentRow(0)

    def _sync_open_buttons(self) -> None:
        self._open_completed_button.setEnabled(self._selected_item_has_output_dir(self._completed_list))
        self._open_issue_button.setEnabled(self._selected_item_has_output_dir(self._issues_list))

    def _selected_item_has_output_dir(self, widget: QListWidget) -> bool:
        item = widget.currentItem()
        if item is None:
            return False
        data = item.data(Qt.UserRole)
        return isinstance(data, tuple) and len(data) == 2 and bool(data[1])

    def _emit_open_history(self, widget: QListWidget) -> None:
        item = widget.currentItem()
        if item is None:
            return
        data = item.data(Qt.UserRole)
        if not isinstance(data, tuple) or len(data) != 2:
            return
        unit_id, output_dir = data
        if not isinstance(unit_id, str) or not isinstance(output_dir, str) or not output_dir.strip():
            return
        self.optimization_history_requested.emit(unit_id, output_dir)

    def _history_lists(
        self,
        batch: TaskBatch,
        report: BatchRunReport | None,
    ) -> tuple[list[BatchRunItemRecord], list[BatchRunItemRecord]]:
        if report is not None:
            return (
                [item for item in report.items if item.status is BatchRunItemStatus.PASSED],
                [
                    item
                    for item in report.items
                    if item.status in {BatchRunItemStatus.FAILED, BatchRunItemStatus.BLOCKED}
                ],
            )

        latest_entries: list[tuple[OptimizationHistoryEntry, BatchRunItemRecord]] = []
        items_by_unit = {item.unit_id: item for item in batch.items}
        for unit_id, batch_item in items_by_unit.items():
            entries = self._optimization_history_by_unit.get(unit_id, [])
            if not entries:
                continue
            entry = entries[0]
            record = BatchRunItemRecord(
                task_id=entry.task_id,
                unit_id=unit_id,
                label=batch_item.label,
                phase_index=batch_item.phase_index,
                order_index=batch_item.order_index,
                status=(
                    BatchRunItemStatus.PASSED
                    if entry.status is OptimizationStatus.OPTIMIZED
                    else BatchRunItemStatus.BLOCKED
                ),
                output_dir=entry.output_dir,
                summary=entry.summary,
                validation_status=entry.validation_status.value,
                failure_category=entry.failure_category.value if entry.failure_category is not None else None,
            )
            latest_entries.append((entry, record))

        latest_entries.sort(key=lambda pair: pair[0].created_at_ms, reverse=True)
        completed_items = [record for entry, record in latest_entries if entry.status is OptimizationStatus.OPTIMIZED]
        issue_items = [record for entry, record in latest_entries if entry.status is not OptimizationStatus.OPTIMIZED]
        return completed_items, issue_items

    def _set_placeholder(self, widget: QListWidget, message: str) -> None:
        widget.clear()
        widget.addItem(QListWidgetItem(message))
