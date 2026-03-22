from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from bettercode.batch_optimize_executor import (
    BatchRunItemStatus,
    BatchRunReport,
    BatchRunStatus,
    create_batch_run_report,
    write_batch_run_report,
)
from bettercode.graph_analysis import GraphInsights, analyze_graph_structure
from bettercode.i18n import LanguageCode, tr
from bettercode.model_config_store import load_model_config, save_model_config
from bettercode.models import FileDetail, GraphNode, NodeKind, ProjectGraph, TaskBatch, TaskBatchPhase, TaskMode
from bettercode.optimize_executor import (
    OptimizationConfigError,
    OptimizationExecutionError,
    apply_optimization_result,
    execute_optimization,
    rollback_optimization_result,
)
from bettercode.optimization_history import (
    load_optimization_history,
    load_saved_apply_result,
    load_saved_optimization_result,
    load_saved_rollback_result,
)
from bettercode.parser import ProjectAnalyzer
from bettercode.task_graph import (
    build_task_batch,
    build_task_execution_plan,
    build_task_graph,
    build_task_unit_package,
    task_batch_to_dict,
    task_unit_package_to_dict,
)
from bettercode.ui.code_block_dialog import CodeBlockDialog
from bettercode.ui.detail_panel import DetailPanel
from bettercode.ui.graph_view import DependencyGraphView
from bettercode.ui.batch_run_report_dialog import BatchRunReportDialog
from bettercode.ui.batch_monitor_panel import BatchMonitorPanel
from bettercode.ui.model_config_dialog import ModelConfigDialog
from bettercode.ui.optimization_review_dialog import OptimizationReviewDialog
from bettercode.ui.subsystem_view import SubsystemCanvasView
from bettercode.ui.task_batch_view import TaskBatchView
from bettercode.ui.task_detail_panel import TaskDetailPanel
from bettercode.ui.task_graph_view import TaskGraphView


class LegendSwatch(QWidget):
    def __init__(
        self,
        *,
        shape: str,
        fill_color: str,
        outer_color: str | None = None,
        dashed_outer: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._shape = shape
        self._fill_color = QColor(fill_color)
        self._outer_color = QColor(outer_color) if outer_color else None
        self._dashed_outer = dashed_outer
        self.setFixedSize(26, 26)

    def sizeHint(self) -> QSize:
        return QSize(26, 26)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._outer_color is not None:
            outer_pen = QPen(self._outer_color, 2.5)
            if self._dashed_outer:
                outer_pen.setStyle(Qt.DashLine)
            painter.setPen(outer_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(2, 2, 22, 22)

        painter.setPen(QPen(QColor("#d9e4ff"), 1.5))
        painter.setBrush(self._fill_color)

        if self._shape == "square":
            painter.drawRoundedRect(4, 4, 18, 18, 4, 4)
        elif self._shape == "edge_strong":
            painter.setPen(QPen(self._fill_color, 2.4))
            painter.drawLine(4, 13, 22, 13)
            painter.setBrush(self._fill_color)
            painter.drawPolygon(QPolygonF([QPointF(22, 13), QPointF(16, 10), QPointF(16, 16)]))
        elif self._shape == "edge_inherit":
            pen = QPen(self._fill_color, 2.2)
            pen.setStyle(Qt.DotLine)
            painter.setPen(pen)
            painter.drawLine(4, 13, 22, 13)
            painter.setBrush(self._fill_color)
            painter.drawPolygon(QPolygonF([QPointF(22, 13), QPointF(16, 10), QPointF(16, 16)]))
        elif self._shape == "edge_context":
            pen = QPen(self._fill_color, 2.0)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(4, 13, 22, 13)
            painter.setBrush(self._fill_color)
            painter.drawPolygon(QPolygonF([QPointF(22, 13), QPointF(16, 10), QPointF(16, 16)]))
        elif self._shape == "task_rect":
            painter.drawRoundedRect(3, 5, 20, 16, 6, 6)
        elif self._shape == "diamond":
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(13, 2),
                        QPointF(23, 13),
                        QPointF(13, 24),
                        QPointF(3, 13),
                    ]
                )
            )
        elif self._shape == "hex":
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(13, 2),
                        QPointF(21, 7),
                        QPointF(21, 19),
                        QPointF(13, 24),
                        QPointF(5, 19),
                        QPointF(5, 7),
                    ]
                )
            )
        else:
            painter.drawEllipse(4, 4, 18, 18)


class _BatchOptimizationWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, *, package, project_root: Path, config) -> None:
        super().__init__()
        self._package = package
        self._project_root = project_root
        self._config = config

    def run(self) -> None:
        try:
            result = execute_optimization(
                self._package,
                project_root=self._project_root,
                config=self._config,
            )
        except (OptimizationExecutionError, OSError, KeyError, ValueError) as error:
            self.failed.emit(str(error))
            return
        self.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._language: LanguageCode = "zh"
        self._graph_mode = "dependency"
        self._graph_modes = [
            ("dependency", "graph_mode.dependency"),
            ("subsystems", "graph_mode.subsystems"),
            ("tasks", "graph_mode.tasks"),
            ("batches", "graph_mode.batches"),
        ]
        self.setWindowTitle(tr(self._language, "app.name"))
        self.resize(1480, 920)

        self._analyzer = ProjectAnalyzer()
        self._graph: ProjectGraph | None = None
        self._insights: GraphInsights | None = None
        self._task_graph = None
        self._optimize_plan = None
        self._translate_plan = None
        self._optimize_batch = None
        self._translate_batch = None
        self._optimization_history_by_unit: dict[str, list] = {}
        self._batch_run_report: BatchRunReport | None = None
        self._batch_run_items = []
        self._batch_run_item_index = 0
        self._batch_run_status_by_unit: dict[str, BatchRunItemStatus] = {}
        self._batch_run_current_unit_id: str | None = None
        self._batch_run_stop_requested = False
        self._batch_run_config = None
        self._batch_run_thread: QThread | None = None
        self._batch_run_worker: _BatchOptimizationWorker | None = None
        self._selected_node_id: str | None = None
        self._selected_task_unit_id: str | None = None
        self._current_project_path: Path | None = None
        self._search_matches: list[str] = []
        self._search_match_index = -1

        self._title_label = QLabel()
        self._language_label = QLabel()
        self._language_selector = QComboBox()
        self._model_config_button = QPushButton()
        self._import_button = QPushButton()
        self._refresh_button = QPushButton()

        self._graph_view = DependencyGraphView()
        self._subsystem_view = SubsystemCanvasView()
        self._task_graph_view = TaskGraphView()
        self._task_batch_view = TaskBatchView(language=self._language)
        self._detail_panel = DetailPanel(language=self._language)
        self._task_detail_panel = TaskDetailPanel(language=self._language)
        self._batch_monitor_panel = BatchMonitorPanel(language=self._language)
        self._search_input = QLineEdit()
        self._focus_filter = QComboBox()
        self._neighbor_label = QLabel()
        self._neighbor_filter = QComboBox()
        self._search_result_label = QLabel()
        self._next_match_button = QPushButton()
        self._reset_view_button = QPushButton()
        self._export_image_button = QPushButton()
        self._graph_mode_buttons: dict[str, QPushButton] = {}
        self._canvas_stack = QStackedWidget()
        self._detail_stack = QStackedWidget()
        self._legend_labels: dict[str, QLabel] = {}
        self._legend_items: dict[str, QWidget] = {}
        self._legend_modes: dict[str, tuple[str, ...]] = {
            "dependency": (
                "legend.python_file",
                "legend.leaf_file",
                "legend.top_level_script",
                "legend.external_package",
                "legend.cycle_member",
                "legend.isolated_file",
            ),
            "subsystems": (
                "legend.python_file",
                "legend.leaf_file",
                "legend.top_level_script",
                "legend.external_package",
                "legend.cycle_member",
                "legend.isolated_file",
            ),
            "tasks": (
                "legend.task_function",
                "legend.task_class_group",
                "legend.task_script_block",
                "legend.task_cycle_group",
                "legend.task_edge_strong",
                "legend.task_edge_inheritance",
                "legend.task_edge_context",
            ),
            "batches": (
                "legend.task_function",
                "legend.task_class_group",
                "legend.task_script_block",
                "legend.task_cycle_group",
                "legend.task_edge_strong",
                "legend.task_edge_inheritance",
                "legend.task_edge_context",
            ),
        }
        self._splitter: QSplitter | None = None

        self._graph_view.node_selected.connect(self._handle_node_selected)
        self._graph_view.node_double_clicked.connect(self._open_code_block_dialog)
        self._graph_view.background_clicked.connect(self._handle_graph_background_clicked)
        self._subsystem_view.node_selected.connect(self._handle_node_selected)
        self._subsystem_view.node_double_clicked.connect(self._open_code_block_dialog)
        self._subsystem_view.background_clicked.connect(self._handle_graph_background_clicked)
        self._task_graph_view.unit_selected.connect(self._handle_task_unit_selected)
        self._task_graph_view.background_clicked.connect(self._handle_graph_background_clicked)
        self._task_batch_view.unit_selected.connect(self._handle_task_unit_selected)
        self._task_batch_view.background_clicked.connect(self._handle_graph_background_clicked)
        self._task_batch_view.run_phase_requested.connect(self._handle_task_batch_run_phase)
        self._task_batch_view.run_batch_requested.connect(self._handle_task_batch_run_all)
        self._task_batch_view.stop_requested.connect(self._handle_task_batch_stop)
        self._task_batch_view.mode_changed.connect(lambda _mode: self._refresh_batch_monitor_panel())
        self._task_detail_panel.assign_unit_requested.connect(self._handle_task_unit_assignment)
        self._task_detail_panel.assign_phase_requested.connect(self._handle_task_phase_assignment)
        self._task_detail_panel.optimization_history_requested.connect(self._open_saved_optimization_history)
        self._batch_monitor_panel.optimization_history_requested.connect(self._open_saved_optimization_history)
        self._language_selector.currentIndexChanged.connect(self._handle_language_changed)

        self._build_ui()
        self._apply_styles()
        self._set_graph_controls_enabled(False)
        self._apply_language()
        self._task_detail_panel.set_view_mode("tasks")

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(16)

        header = QWidget()
        header.setObjectName("appHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_wrap = QVBoxLayout()
        self._title_label.setObjectName("title")
        title_wrap.addWidget(self._title_label)
        header_layout.addLayout(title_wrap, stretch=1)

        actions_wrap = QHBoxLayout()
        self._language_label.setObjectName("metricText")
        self._language_selector.setMinimumWidth(120)
        self._refresh_button.setProperty("variant", "secondary")
        self._model_config_button.setProperty("variant", "secondary")
        self._import_button.clicked.connect(self._select_project_directory)
        self._refresh_button.clicked.connect(self._refresh_current_project)
        self._model_config_button.clicked.connect(self._open_model_config_dialog)
        actions_wrap.addWidget(self._language_label)
        actions_wrap.addWidget(self._language_selector)
        actions_wrap.addWidget(self._model_config_button)
        actions_wrap.addWidget(self._import_button)
        actions_wrap.addWidget(self._refresh_button)
        header_layout.addLayout(actions_wrap)
        root_layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setObjectName("mainSplitter")

        graph_panel = QFrame()
        graph_panel.setObjectName("workspacePanel")
        graph_layout = QVBoxLayout(graph_panel)
        graph_layout.setContentsMargins(16, 16, 16, 16)
        graph_layout.setSpacing(12)

        controls = QFrame()
        controls.setObjectName("toolbarCard")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(14, 14, 14, 14)
        controls_layout.setSpacing(10)
        self._search_input.textChanged.connect(self._handle_search_text_changed)
        self._search_input.returnPressed.connect(self._select_next_search_match)
        self._focus_filter.currentIndexChanged.connect(self._handle_focus_filter_changed)
        self._neighbor_label.setObjectName("metricText")
        self._neighbor_filter.currentIndexChanged.connect(self._handle_neighbor_filter_changed)
        self._next_match_button.setProperty("variant", "secondary")
        self._next_match_button.clicked.connect(self._select_next_search_match)
        self._reset_view_button.setProperty("variant", "secondary")
        self._reset_view_button.clicked.connect(self._handle_reset_view)
        self._export_image_button.setProperty("variant", "secondary")
        self._export_image_button.clicked.connect(self._export_current_canvas_image)
        controls_layout.addWidget(self._search_input, stretch=1)
        controls_layout.addWidget(self._focus_filter)
        controls_layout.addWidget(self._neighbor_label)
        controls_layout.addWidget(self._neighbor_filter)
        controls_layout.addWidget(self._next_match_button)
        controls_layout.addWidget(self._reset_view_button)
        controls_layout.addWidget(self._export_image_button)
        controls_layout.addWidget(self._search_result_label)
        graph_layout.addWidget(controls)

        graph_layout.addWidget(self._build_legend())
        canvas_frame = QFrame()
        canvas_frame.setObjectName("canvasCard")
        canvas_layout = QVBoxLayout(canvas_frame)
        canvas_layout.setContentsMargins(12, 12, 12, 12)
        canvas_layout.setSpacing(10)
        canvas_layout.addWidget(self._build_graph_mode_bar())
        self._canvas_stack.addWidget(self._graph_view)
        self._canvas_stack.addWidget(self._subsystem_view)
        self._canvas_stack.addWidget(self._task_graph_view)
        self._canvas_stack.addWidget(self._task_batch_view)
        canvas_layout.addWidget(self._canvas_stack, stretch=1)
        graph_layout.addWidget(canvas_frame, stretch=1)

        detail_panel = QFrame()
        detail_panel.setObjectName("inspectorPanel")
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(12)
        self._detail_stack.addWidget(self._detail_panel)
        self._detail_stack.addWidget(self._task_detail_panel)
        self._detail_stack.addWidget(self._batch_monitor_panel)
        detail_layout.addWidget(self._detail_stack)

        splitter.addWidget(graph_panel)
        splitter.addWidget(detail_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1040, 420])
        self._splitter = splitter
        root_layout.addWidget(splitter, stretch=1)

        self.setCentralWidget(root)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._batch_run_thread is not None:
            QApplication.processEvents()
            self._batch_run_thread.wait(50)
            if self._batch_run_thread is not None and self._batch_run_thread.isRunning():
                QMessageBox.information(
                    self,
                    tr(self._language, "batch_run.dialog.close_blocked_title"),
                    tr(self._language, "batch_run.dialog.close_blocked_body"),
                )
                event.ignore()
                return
            self._cleanup_batch_worker()
        super().closeEvent(event)

    def _build_legend(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("legendCard")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(16)

        legend_items = [
            ("legend.python_file", LegendSwatch(shape="circle", fill_color="#3559d1")),
            ("legend.leaf_file", LegendSwatch(shape="hex", fill_color="#118c6a")),
            ("legend.top_level_script", LegendSwatch(shape="diamond", fill_color="#9b4fd8")),
            ("legend.external_package", LegendSwatch(shape="square", fill_color="#ff8a3d")),
            ("legend.cycle_member", LegendSwatch(shape="circle", fill_color="#3559d1", outer_color="#ff5d6c")),
            (
                "legend.isolated_file",
                LegendSwatch(shape="circle", fill_color="#3559d1", outer_color="#a06dff", dashed_outer=True),
            ),
            ("legend.task_function", LegendSwatch(shape="task_rect", fill_color="#3559d1")),
            ("legend.task_class_group", LegendSwatch(shape="task_rect", fill_color="#118c6a")),
            ("legend.task_script_block", LegendSwatch(shape="task_rect", fill_color="#d07a1f")),
            ("legend.task_cycle_group", LegendSwatch(shape="task_rect", fill_color="#9b4fd8")),
            ("legend.task_edge_strong", LegendSwatch(shape="edge_strong", fill_color="#6f8fff")),
            ("legend.task_edge_inheritance", LegendSwatch(shape="edge_inherit", fill_color="#49d39b")),
            ("legend.task_edge_context", LegendSwatch(shape="edge_context", fill_color="#8fa1bb")),
        ]

        for key, swatch in legend_items:
            item = QWidget()
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(6)
            label = QLabel()
            self._legend_labels[key] = label
            self._legend_items[key] = item
            item_layout.addWidget(swatch)
            item_layout.addWidget(label)
            layout.addWidget(item)

        layout.addStretch(1)
        return frame

    def _build_graph_mode_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        for mode, translation_key in self._graph_modes:
            button = QPushButton()
            button.setCheckable(True)
            button.setProperty("modeButton", True)
            button.clicked.connect(lambda checked=False, current_mode=mode: self._set_graph_mode(current_mode))
            self._graph_mode_buttons[mode] = button
            layout.addWidget(button)

        layout.addStretch(1)
        return bar

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #101722;
                color: #e9eef7;
                font-family: Helvetica Neue, Arial, sans-serif;
                font-size: 13px;
            }
            QLabel#title {
                font-size: 30px;
                font-weight: 700;
            }
            QLabel#subtitle {
                color: #a7b5c9;
                font-size: 14px;
            }
            QLabel#sectionTitle {
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#canvasTitle {
                color: #f7fbff;
                font-size: 16px;
                font-weight: 700;
                padding: 2px 2px 4px 2px;
            }
            QLabel#panelTitle {
                color: #f4f7fd;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#panelSubtitle {
                color: #7791b3;
                font-size: 12px;
            }
            QLabel#detailSectionTitle {
                color: #aebdd4;
                font-size: 12px;
                font-weight: 700;
                padding-top: 4px;
            }
            QLabel#detailSubsectionTitle {
                color: #7dc6ff;
                font-size: 11px;
                font-weight: 700;
                padding-top: 2px;
            }
            QLabel#detailTitle {
                color: #f8fbff;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#detailHelper {
                color: #8aa0bd;
                font-size: 12px;
            }
            QLabel#detailMeta {
                color: #c4d0e3;
                font-size: 12px;
            }
            QLabel#metricText {
                color: #7f93af;
                font-size: 12px;
                font-weight: 500;
            }
            QFrame#workspacePanel {
                background: #0d1624;
                border: 1px solid #22364f;
                border-radius: 20px;
            }
            QFrame#inspectorPanel {
                background: #111c2c;
                border: 1px solid #35506f;
                border-radius: 20px;
            }
            QFrame#legendCard {
                background: #111a28;
                border: 1px solid #1f3147;
                border-radius: 14px;
            }
            QFrame#toolbarCard {
                background: #111a27;
                border: 1px solid #21364e;
                border-radius: 16px;
            }
            QFrame#canvasCard {
                background: #08111b;
                border: 1px solid #345b84;
                border-radius: 20px;
            }
            QFrame#detailHeaderCard {
                background: #16283d;
                border: 1px solid #4a77a8;
                border-radius: 16px;
            }
            QFrame#detailCard {
                background: #121d2c;
                border: 1px solid #29405d;
                border-radius: 16px;
            }
            QPushButton {
                background: #ff9640;
                color: #08111e;
                border: none;
                border-radius: 18px;
                padding: 10px 16px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #ffac67;
            }
            QPushButton[variant="secondary"] {
                background: #162030;
                color: #e9eef7;
                border: 1px solid #27354b;
            }
            QPushButton[variant="secondary"]:hover {
                background: #1a2638;
            }
            QPushButton[modeButton="true"] {
                background: #121b29;
                color: #d7e4f6;
                border: 1px solid #29405d;
                border-radius: 16px;
                padding: 8px 14px;
                font-weight: 700;
            }
            QPushButton[modeButton="true"]:checked {
                background: #1b3654;
                color: #f7fbff;
                border: 1px solid #69b4ff;
            }
            QListWidget, QTextEdit, QLineEdit, QComboBox {
                background: #141d2b;
                border: 1px solid #202c3f;
                border-radius: 12px;
            }
            QListWidget#detailList {
                background: #0f1825;
                border: 1px solid #2a3c53;
            }
            QListWidget#detailList::item {
                padding: 4px 2px;
            }
            QLineEdit, QComboBox {
                padding: 10px 12px;
            }
            QScrollArea#detailScroll, QWidget#detailContent {
                background: transparent;
            }
            QSplitter#mainSplitter::handle {
                background: #162333;
                width: 10px;
                margin: 8px 0;
                border-radius: 4px;
            }
            QSplitter#mainSplitter::handle:hover {
                background: #26415f;
            }
            """
        )

    def _apply_language(self) -> None:
        self.setWindowTitle(tr(self._language, "app.name"))
        self._title_label.setText(tr(self._language, "app.name"))
        self._language_label.setText(tr(self._language, "language.label"))
        self._model_config_button.setText(tr(self._language, "task.button.configure_model"))
        self._import_button.setText(tr(self._language, "button.import_project"))
        self._refresh_button.setText(tr(self._language, "button.refresh"))
        self._next_match_button.setText(tr(self._language, "button.next_match"))
        self._reset_view_button.setText(tr(self._language, "button.reset_view"))
        self._export_image_button.setText(tr(self._language, "button.export_image"))
        self._neighbor_label.setText(tr(self._language, "neighbor.label"))
        self._rebuild_graph_mode_buttons()
        for key, label in self._legend_labels.items():
            label.setText(tr(self._language, key))
        self._search_input.setPlaceholderText(tr(self._language, "search.placeholder"))
        self._detail_panel.set_language(self._language)
        self._task_detail_panel.set_language(self._language)
        self._batch_monitor_panel.set_language(self._language)
        self._graph_view.set_language(self._language)
        self._subsystem_view.set_language(self._language)
        self._task_graph_view.set_language(self._language)
        self._task_batch_view.set_language(self._language)
        self._refresh_batch_execution_views()
        self._refresh_batch_monitor_panel()
        self._rebuild_language_selector()
        self._rebuild_focus_filter()
        self._rebuild_neighbor_filter()
        self._refresh_search_label()
        self._update_graph_mode_ui()

    def _update_legend_ui(self) -> None:
        active_keys = set(self._legend_modes.get(self._graph_mode, self._legend_modes["dependency"]))
        for key, item in self._legend_items.items():
            item.setVisible(key in active_keys)

    def _rebuild_language_selector(self) -> None:
        current_data = self._language_selector.currentData()
        self._language_selector.blockSignals(True)
        self._language_selector.clear()
        self._language_selector.addItem(tr(self._language, "language.en"), "en")
        self._language_selector.addItem(tr(self._language, "language.zh"), "zh")
        if current_data is None:
            current_data = self._language
        index = self._language_selector.findData(current_data)
        self._language_selector.setCurrentIndex(index if index >= 0 else 0)
        self._language_selector.blockSignals(False)

    def _rebuild_focus_filter(self) -> None:
        current_data = self._focus_filter.currentData() or "all"
        self._focus_filter.blockSignals(True)
        self._focus_filter.clear()
        if self._graph_mode in {"tasks", "batches"}:
            self._focus_filter.addItem(tr(self._language, "focus.task_all"), "task_all")
            self._focus_filter.addItem(tr(self._language, "focus.task_function"), "task_function")
            self._focus_filter.addItem(tr(self._language, "focus.task_class_group"), "task_class_group")
            self._focus_filter.addItem(tr(self._language, "focus.task_script_block"), "task_script_block")
            self._focus_filter.addItem(tr(self._language, "focus.task_cycle_group"), "task_cycle_group")
            self._focus_filter.addItem(tr(self._language, "focus.task_ready"), "task_ready")
            self._focus_filter.addItem(tr(self._language, "focus.task_blocked"), "task_blocked")
        else:
            self._focus_filter.addItem(tr(self._language, "focus.all"), "all")
            self._focus_filter.addItem(tr(self._language, "focus.internal"), "internal")
            self._focus_filter.addItem(tr(self._language, "focus.leaf"), "leaf")
            self._focus_filter.addItem(tr(self._language, "focus.external"), "external")
            self._focus_filter.addItem(tr(self._language, "focus.cycle"), "cycle")
            self._focus_filter.addItem(tr(self._language, "focus.isolated"), "isolated")
        index = self._focus_filter.findData(current_data)
        self._focus_filter.setCurrentIndex(index if index >= 0 else 0)
        self._focus_filter.blockSignals(False)

    def _rebuild_neighbor_filter(self) -> None:
        current_data = self._neighbor_filter.currentData() or 1
        self._neighbor_filter.blockSignals(True)
        self._neighbor_filter.clear()
        self._neighbor_filter.addItem(tr(self._language, "neighbor.one"), 1)
        self._neighbor_filter.addItem(tr(self._language, "neighbor.two"), 2)
        index = self._neighbor_filter.findData(current_data)
        self._neighbor_filter.setCurrentIndex(index if index >= 0 else 0)
        self._neighbor_filter.blockSignals(False)
        neighbor_depth = int(self._neighbor_filter.currentData() or 1)
        self._graph_view.set_neighbor_depth(neighbor_depth)
        self._subsystem_view.set_neighbor_depth(neighbor_depth)
        self._task_graph_view.set_neighbor_depth(neighbor_depth)
        self._task_batch_view.set_neighbor_depth(neighbor_depth)

    def _rebuild_graph_mode_buttons(self) -> None:
        for mode, translation_key in self._graph_modes:
            button = self._graph_mode_buttons[mode]
            button.setText(tr(self._language, translation_key))
            button.setChecked(mode == self._graph_mode)

    def _refresh_search_label(self) -> None:
        if self._graph is None or not self._search_input.text().strip():
            self._search_result_label.setText(tr(self._language, "search.matches.empty"))
            return
        self._search_result_label.setText(
            tr(self._language, "search.matches.value", count=len(self._search_matches))
        )

    def _handle_language_changed(self, _index: int) -> None:
        language = self._language_selector.currentData()
        if language not in {"en", "zh"} or language == self._language:
            return
        self._language = language
        self._apply_language()

    def _select_project_directory(self) -> None:
        selected_directory = QFileDialog.getExistingDirectory(
            self,
            tr(self._language, "dialog.select_project_directory"),
            str(self._current_project_path or Path.home()),
        )
        if selected_directory:
            self._load_project(Path(selected_directory))

    def _refresh_current_project(self) -> None:
        if self._current_project_path is not None:
            self._load_project(self._current_project_path)

    def _open_model_config_dialog(self) -> None:
        dialog = ModelConfigDialog(
            language=self._language,
            initial_config=load_model_config(),
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        save_model_config(dialog.model_config())

    def _resolve_model_config(self, *, interactive: bool) -> object | None:
        current = load_model_config()
        if current.api_token and current.api_url and current.model_name:
            return current
        if not interactive:
            return None
        dialog = ModelConfigDialog(language=self._language, initial_config=current, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return None
        config = dialog.model_config()
        save_model_config(config)
        return config

    def _load_project(self, project_path: Path) -> None:
        if self._batch_run_report is None:
            self._batch_run_status_by_unit = {}
            self._batch_run_current_unit_id = None
        try:
            graph = self._analyzer.analyze(project_path)
        except Exception as error:  # pragma: no cover
            QMessageBox.critical(self, tr(self._language, "dialog.analysis_failed"), str(error))
            return

        self._graph = graph
        self._insights = analyze_graph_structure(graph)
        self._task_graph = build_task_graph(graph)
        self._optimize_plan = build_task_execution_plan(graph, mode=TaskMode.OPTIMIZE)
        self._translate_plan = build_task_execution_plan(graph, mode=TaskMode.TRANSLATE)
        self._optimize_batch = build_task_batch(graph, mode=TaskMode.OPTIMIZE)
        self._translate_batch = build_task_batch(graph, mode=TaskMode.TRANSLATE)
        self._optimization_history_by_unit = load_optimization_history(project_path)
        self._current_project_path = project_path
        self._graph_view.set_graph(graph, self._insights)
        self._graph_view.set_language(self._language)
        self._subsystem_view.set_graph(graph)
        self._subsystem_view.set_language(self._language)
        self._task_graph_view.set_task_graph(self._task_graph)
        self._task_graph_view.set_language(self._language)
        self._task_batch_view.set_batches(
            task_graph=self._task_graph,
            optimize_batch=self._optimize_batch,
            translate_batch=self._translate_batch,
        )
        self._task_batch_view.set_language(self._language)
        self._refresh_batch_execution_views()
        self._refresh_batch_monitor_panel()
        self._set_graph_controls_enabled(True)
        self._handle_node_selected(None)
        self._handle_task_unit_selected(None)
        self._apply_focus_and_search(auto_select=False)
        self._update_graph_mode_ui()

    def _handle_node_selected(self, node_id: str | None) -> None:
        self._selected_node_id = node_id
        self._graph_view.select_node(node_id)
        self._subsystem_view.select_node(node_id)
        if self._graph is None or node_id is None:
            self._detail_panel.clear_panel()
            return

        node = next((candidate for candidate in self._graph.nodes if candidate.id == node_id), None)
        self._detail_panel.set_selection(self._graph, self._insights, node)

    def _handle_task_unit_selected(self, unit_id: str | None) -> None:
        self._selected_task_unit_id = unit_id
        self._task_graph_view.select_unit(unit_id)
        self._task_batch_view.select_unit(unit_id)
        if self._graph_mode == "batches":
            self._refresh_batch_monitor_panel()
            return
        if self._task_graph is None or unit_id is None:
            self._task_detail_panel.clear_panel()
            return

        unit = next((candidate for candidate in self._task_graph.units if candidate.id == unit_id), None)
        self._task_detail_panel.set_selection(
            project_graph=self._graph,
            task_graph=self._task_graph,
            optimize_plan=self._optimize_plan,
            translate_plan=self._translate_plan,
            optimize_batch=self._optimize_batch,
            translate_batch=self._translate_batch,
            optimization_history_by_unit=self._optimization_history_by_unit,
            batch_run_report=self._batch_run_report,
            batch_run_status_by_unit=self._batch_run_status_by_unit,
            batch_run_current_unit_id=self._batch_run_current_unit_id,
            unit=unit,
        )

    def _handle_graph_background_clicked(self) -> None:
        if self._graph_mode in {"tasks", "batches"}:
            self._handle_task_unit_selected(None)
            return
        self._handle_node_selected(None)

    def _open_code_block_dialog(self, node_id: str) -> None:
        if self._graph is None or self._current_project_path is None:
            return

        node = next((candidate for candidate in self._graph.nodes if candidate.id == node_id), None)
        if node is None or node.kind is NodeKind.EXTERNAL_PACKAGE:
            return

        detail: FileDetail | None = self._graph.file_details.get(node_id)
        if detail is None:
            return

        dialog = CodeBlockDialog(
            project_root=self._current_project_path,
            graph=self._graph,
            node=node,
            detail=detail,
            language=self._language,
            parent=self,
        )
        dialog.exec()

    def _handle_search_text_changed(self, _text: str) -> None:
        self._refresh_search_matches(auto_select=True)

    def _handle_focus_filter_changed(self, _index: int) -> None:
        self._apply_focus_and_search(auto_select=False)

    def _handle_neighbor_filter_changed(self, _index: int) -> None:
        neighbor_depth = int(self._neighbor_filter.currentData() or 1)
        self._graph_view.set_neighbor_depth(neighbor_depth)
        self._subsystem_view.set_neighbor_depth(neighbor_depth)
        self._task_graph_view.set_neighbor_depth(neighbor_depth)
        self._task_batch_view.set_neighbor_depth(neighbor_depth)

    def _set_graph_mode(self, mode: str) -> None:
        if mode not in self._graph_mode_buttons:
            return
        self._graph_mode = mode
        self._rebuild_focus_filter()
        self._update_graph_mode_ui()

    def _update_graph_mode_ui(self) -> None:
        has_graph = self._graph is not None
        for mode, button in self._graph_mode_buttons.items():
            button.setChecked(mode == self._graph_mode)
            button.setEnabled(has_graph)
        self._reset_view_button.setEnabled(has_graph)
        self._export_image_button.setEnabled(has_graph)
        if self._graph_mode == "subsystems":
            self._canvas_stack.setCurrentWidget(self._subsystem_view)
            self._detail_stack.setCurrentWidget(self._detail_panel)
        elif self._graph_mode == "tasks":
            self._canvas_stack.setCurrentWidget(self._task_graph_view)
            self._detail_stack.setCurrentWidget(self._task_detail_panel)
            self._task_detail_panel.set_view_mode("tasks")
        elif self._graph_mode == "batches":
            self._canvas_stack.setCurrentWidget(self._task_batch_view)
            self._detail_stack.setCurrentWidget(self._batch_monitor_panel)
            self._refresh_batch_monitor_panel()
        else:
            self._canvas_stack.setCurrentWidget(self._graph_view)
            self._detail_stack.setCurrentWidget(self._detail_panel)
        if self._graph_mode in {"tasks", "batches"}:
            if self._selected_task_unit_id is None:
                self._task_detail_panel.clear_panel()
            else:
                self._handle_task_unit_selected(self._selected_task_unit_id)
        else:
            if self._selected_node_id is None:
                self._detail_panel.clear_panel()
            else:
                self._handle_node_selected(self._selected_node_id)
        self._apply_focus_and_search(auto_select=False)
        self._update_legend_ui()
        self._update_dependency_controls()

    def _update_dependency_controls(self) -> None:
        has_graph = self._graph is not None
        search_controls_enabled = has_graph
        neighbor_enabled = has_graph and self._graph_mode in {"dependency", "subsystems", "tasks"}
        self._search_input.setEnabled(search_controls_enabled)
        self._focus_filter.setEnabled(search_controls_enabled)
        self._neighbor_filter.setEnabled(neighbor_enabled)
        self._neighbor_label.setEnabled(neighbor_enabled)
        self._next_match_button.setEnabled(search_controls_enabled and bool(self._search_matches))
        self._search_result_label.setEnabled(search_controls_enabled)

    def _handle_reset_view(self) -> None:
        if self._graph_mode == "subsystems":
            self._subsystem_view.reset_view()
            return
        if self._graph_mode == "tasks":
            self._task_graph_view.reset_view()
            return
        if self._graph_mode == "batches":
            self._task_batch_view.reset_view()
            return
        self._graph_view.reset_view()

    def _export_current_canvas_image(self) -> None:
        if self._current_project_path is None or self._graph is None:
            return

        default_name = f"{self._graph_mode}.png"
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            tr(self._language, "image_export.dialog.title"),
            str(self._current_project_path / default_name),
            tr(self._language, "image_export.dialog.filter"),
        )
        if not file_name:
            return

        output_path = Path(file_name)
        if output_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".svg"}:
            if "svg" in selected_filter.lower():
                output_path = output_path.with_suffix(".svg")
            elif "jpg" in selected_filter.lower() or "jpeg" in selected_filter.lower():
                output_path = output_path.with_suffix(".jpg")
            else:
                output_path = output_path.with_suffix(".png")

        try:
            if self._graph_mode == "subsystems":
                self._subsystem_view.export_image(str(output_path))
            elif self._graph_mode == "tasks":
                self._task_graph_view.export_image(str(output_path))
            elif self._graph_mode == "batches":
                self._task_batch_view.export_image(str(output_path))
            else:
                self._graph_view.export_image(str(output_path))
        except (OSError, ValueError) as error:
            QMessageBox.warning(
                self,
                tr(self._language, "image_export.dialog.error_title"),
                tr(self._language, "image_export.dialog.error_body", error=str(error)),
            )
            return

        QMessageBox.information(
            self,
            tr(self._language, "image_export.dialog.success_title"),
            tr(self._language, "image_export.dialog.success_body", path=str(output_path)),
        )

    def _apply_focus_and_search(self, *, auto_select: bool) -> None:
        if self._graph is None:
            return

        if self._graph_mode in {"tasks", "batches"}:
            focused_unit_ids = self._focused_task_unit_ids()
            self._task_graph_view.set_focused_unit_ids(focused_unit_ids)
            self._task_batch_view.set_focused_unit_ids(focused_unit_ids)
            if auto_select and focused_unit_ids is not None and self._selected_task_unit_id not in focused_unit_ids:
                fallback_unit_id = self._preferred_task_unit_id(focused_unit_ids)
                self._handle_task_unit_selected(fallback_unit_id)
            elif self._selected_task_unit_id is None and auto_select:
                fallback_unit_id = self._preferred_task_unit_id(focused_unit_ids)
                self._handle_task_unit_selected(fallback_unit_id)
        else:
            focused_node_ids = self._focused_node_ids()
            self._graph_view.set_focused_node_ids(focused_node_ids)
            self._subsystem_view.set_focused_node_ids(focused_node_ids)

            if auto_select and focused_node_ids is not None and self._selected_node_id not in focused_node_ids:
                fallback_node_id = self._preferred_node_id(focused_node_ids)
                self._handle_node_selected(fallback_node_id)
            elif self._selected_node_id is None and auto_select:
                fallback_node_id = self._preferred_node_id(focused_node_ids)
                self._handle_node_selected(fallback_node_id)

        self._refresh_search_matches(auto_select=auto_select)

    def _refresh_search_matches(self, *, auto_select: bool) -> None:
        if self._graph is None:
            self._search_matches = []
            self._search_match_index = -1
            self._next_match_button.setEnabled(False)
            self._graph_view.set_search_match_node_ids(set())
            self._subsystem_view.set_search_match_node_ids(set())
            self._task_graph_view.set_search_match_unit_ids(set())
            self._task_batch_view.set_search_match_unit_ids(set())
            self._refresh_search_label()
            return

        query = self._search_input.text().strip().lower()
        if not query:
            self._search_matches = []
            self._search_match_index = -1
            self._next_match_button.setEnabled(False)
            self._graph_view.set_search_match_node_ids(set())
            self._subsystem_view.set_search_match_node_ids(set())
            self._task_graph_view.set_search_match_unit_ids(set())
            self._task_batch_view.set_search_match_unit_ids(set())
            self._refresh_search_label()
            return

        if self._graph_mode in {"tasks", "batches"}:
            visible_unit_ids = self._focused_task_unit_ids()
            candidate_units = [
                unit
                for unit in (self._task_graph.units if self._task_graph is not None else [])
                if visible_unit_ids is None or unit.id in visible_unit_ids
            ]
            self._search_matches = [
                unit.id
                for unit in candidate_units
                if self._task_unit_matches_query(unit, query)
            ]
            self._task_graph_view.set_search_match_unit_ids(set(self._search_matches))
            self._task_batch_view.set_search_match_unit_ids(set(self._search_matches))
            self._graph_view.set_search_match_node_ids(set())
            self._subsystem_view.set_search_match_node_ids(set())
        else:
            visible_node_ids = self._focused_node_ids()
            candidate_nodes = [
                node
                for node in self._graph.nodes
                if visible_node_ids is None or node.id in visible_node_ids
            ]
            self._search_matches = [
                node.id
                for node in candidate_nodes
                if self._node_matches_query(node, query)
            ]
            self._graph_view.set_search_match_node_ids(set(self._search_matches))
            self._subsystem_view.set_search_match_node_ids(set(self._search_matches))
            self._task_graph_view.set_search_match_unit_ids(set())
            self._task_batch_view.set_search_match_unit_ids(set())
        self._next_match_button.setEnabled(bool(self._search_matches))
        self._refresh_search_label()

        if not self._search_matches:
            self._search_match_index = -1
            return

        current_selected = self._selected_task_unit_id if self._graph_mode in {"tasks", "batches"} else self._selected_node_id
        if current_selected in self._search_matches:
            self._search_match_index = self._search_matches.index(current_selected)
            if auto_select:
                if self._graph_mode in {"tasks", "batches"}:
                    self._handle_task_unit_selected(current_selected)
                else:
                    self._handle_node_selected(current_selected)
            return

        self._search_match_index = 0
        if auto_select:
            if self._graph_mode in {"tasks", "batches"}:
                self._handle_task_unit_selected(self._search_matches[0])
            else:
                self._handle_node_selected(self._search_matches[0])

    def _select_next_search_match(self) -> None:
        if not self._search_matches:
            return
        self._search_match_index = (self._search_match_index + 1) % len(self._search_matches)
        if self._graph_mode in {"tasks", "batches"}:
            self._handle_task_unit_selected(self._search_matches[self._search_match_index])
            return
        self._handle_node_selected(self._search_matches[self._search_match_index])

    def _focused_node_ids(self) -> set[str] | None:
        if self._graph is None or self._insights is None:
            return None

        filter_key = self._focus_filter.currentData()
        if filter_key == "all":
            return None
        if filter_key == "internal":
            return {node.id for node in self._graph.nodes if node.kind is not NodeKind.EXTERNAL_PACKAGE}
        if filter_key == "leaf":
            return {node.id for node in self._graph.nodes if node.kind is NodeKind.LEAF_FILE}
        if filter_key == "external":
            return {node.id for node in self._graph.nodes if node.kind is NodeKind.EXTERNAL_PACKAGE}
        if filter_key == "cycle":
            return set(self._insights.cycle_node_ids)
        if filter_key == "isolated":
            return set(self._insights.isolated_node_ids)
        return None

    def _focused_task_unit_ids(self) -> set[str] | None:
        if self._task_graph is None:
            return None
        filter_key = self._focus_filter.currentData()
        if filter_key in {None, "task_all"}:
            return None
        if filter_key == "task_function":
            return {unit.id for unit in self._task_graph.units if unit.kind.value == "function"}
        if filter_key == "task_class_group":
            return {unit.id for unit in self._task_graph.units if unit.kind.value == "class_group"}
        if filter_key == "task_script_block":
            return {unit.id for unit in self._task_graph.units if unit.kind.value == "script_block"}
        if filter_key == "task_cycle_group":
            return {unit.id for unit in self._task_graph.units if unit.kind.value == "cycle_group"}
        if filter_key == "task_ready":
            return {unit.id for unit in self._task_graph.units if unit.ready_to_run}
        if filter_key == "task_blocked":
            return {unit.id for unit in self._task_graph.units if not unit.ready_to_run}
        return None

    def _preferred_node_id(self, allowed_node_ids: set[str] | None) -> str | None:
        if self._graph is None:
            return None

        candidates = [
            node
            for node in self._graph.nodes
            if allowed_node_ids is None or node.id in allowed_node_ids
        ]
        preferred = next((node for node in candidates if node.kind is not NodeKind.EXTERNAL_PACKAGE), None)
        return preferred.id if preferred else (candidates[0].id if candidates else None)

    def _preferred_task_unit_id(self, allowed_unit_ids: set[str] | None) -> str | None:
        if self._task_graph is None:
            return None
        candidates = [
            unit
            for unit in self._task_graph.units
            if allowed_unit_ids is None or unit.id in allowed_unit_ids
        ]
        preferred = next((unit for unit in candidates if unit.kind.value == "function"), None)
        return preferred.id if preferred else (candidates[0].id if candidates else None)

    def _node_matches_query(self, node: GraphNode, query: str) -> bool:
        haystacks = [node.label, node.path or "", node.module or ""]
        return any(query in haystack.lower() for haystack in haystacks)

    def _task_unit_matches_query(self, unit, query: str) -> bool:
        if self._graph is None:
            return False
        node_lookup = {node.id: node for node in self._graph.nodes}
        haystacks = [unit.label]
        for node_id in unit.node_ids:
            node = node_lookup.get(node_id)
            if node is None:
                continue
            haystacks.extend([node.label, node.path or "", node.module or ""])
        return any(query in haystack.lower() for haystack in haystacks)

    def _handle_task_unit_assignment(self, unit_id: str, mode_value: str) -> None:
        if mode_value == TaskMode.OPTIMIZE.value:
            self._run_task_unit_optimization(unit_id)
            return
        self._export_task_unit_package(unit_id, mode_value)

    def _handle_task_phase_assignment(self, unit_id: str, mode_value: str) -> None:
        self._export_task_batch_phase_for_unit(unit_id, mode_value)

    def _handle_task_batch_run_phase(self, mode_value: str) -> None:
        if mode_value != TaskMode.OPTIMIZE.value:
            QMessageBox.information(
                self,
                tr(self._language, "batch_run.dialog.unsupported_title"),
                tr(self._language, "batch_run.dialog.optimize_only_body"),
            )
            return
        phase_index = self._selected_phase_index_for_unit(self._selected_task_unit_id)
        if phase_index is None:
            QMessageBox.information(
                self,
                tr(self._language, "batch_run.dialog.select_phase_title"),
                tr(self._language, "batch_run.dialog.select_phase_body"),
            )
            return
        self._start_batch_optimization(scope="current_phase", selected_phase=phase_index)

    def _handle_task_batch_run_all(self, mode_value: str) -> None:
        if mode_value != TaskMode.OPTIMIZE.value:
            QMessageBox.information(
                self,
                tr(self._language, "batch_run.dialog.unsupported_title"),
                tr(self._language, "batch_run.dialog.optimize_only_body"),
            )
            return
        self._start_batch_optimization(scope="full_batch", selected_phase=None)

    def _handle_task_batch_stop(self) -> None:
        if self._batch_run_report is None:
            return
        self._batch_run_stop_requested = True
        self._refresh_batch_execution_views(
            status_text=tr(self._language, "task_batch_view.execution.stop_requested"),
            is_running=True,
        )

    def _start_batch_optimization(self, *, scope: str, selected_phase: int | None) -> None:
        if self._batch_run_report is not None:
            QMessageBox.information(
                self,
                tr(self._language, "batch_run.dialog.already_running_title"),
                tr(self._language, "batch_run.dialog.already_running_body"),
            )
            return
        if self._graph is None or self._current_project_path is None or self._optimize_batch is None:
            return
        try:
            config = self._resolve_model_config(interactive=True)
            if config is None:
                return
        except OptimizationConfigError as error:
            QMessageBox.warning(
                self,
                tr(self._language, "task.dialog.optimize_error_title"),
                tr(self._language, "task.dialog.optimize_error_body", error=str(error)),
            )
            return

        batch_items = [
            item
            for item in self._optimize_batch.items
            if selected_phase is None or item.phase_index == selected_phase
        ]
        batch_items = sorted(batch_items, key=lambda item: (item.phase_index, item.order_index))
        if not batch_items:
            return

        self._batch_run_report = create_batch_run_report(
            project_root=self._current_project_path,
            mode=TaskMode.OPTIMIZE,
            scope=scope,
            selected_phase=selected_phase,
            items=batch_items,
        )
        self._batch_run_items = batch_items
        self._batch_run_item_index = 0
        self._batch_run_status_by_unit = {item.unit_id: BatchRunItemStatus.PENDING for item in batch_items}
        self._batch_run_current_unit_id = None
        self._batch_run_stop_requested = False
        self._batch_run_config = config
        self._refresh_batch_execution_views(
            status_text=tr(
                self._language,
                "task_batch_view.execution.preparing",
                count=len(batch_items),
            ),
            is_running=True,
        )
        QTimer.singleShot(0, self._run_next_batch_optimization_item)

    def _run_next_batch_optimization_item(self) -> None:
        if self._batch_run_report is None or self._graph is None or self._current_project_path is None:
            return
        if self._batch_run_stop_requested:
            self._block_remaining_batch_items(
                reason=tr(self._language, "batch_run.stop.blocked_reason"),
            )
            self._finish_batch_run(BatchRunStatus.STOPPED)
            return
        if self._batch_run_item_index >= len(self._batch_run_items):
            self._finish_batch_run(BatchRunStatus.PASSED)
            return

        batch_item = self._batch_run_items[self._batch_run_item_index]
        report_item = self._batch_run_report.items[self._batch_run_item_index]
        report_item.status = BatchRunItemStatus.RUNNING
        report_item.started_at_ms = self._now_ms()
        self._batch_run_current_unit_id = batch_item.unit_id
        self._batch_run_status_by_unit[batch_item.unit_id] = BatchRunItemStatus.RUNNING
        write_batch_run_report(self._batch_run_report)
        self._handle_task_unit_selected(batch_item.unit_id)
        self._refresh_batch_execution_views(
            status_text=tr(
                self._language,
                "task_batch_view.execution.running",
                label=batch_item.label,
                phase=batch_item.phase_index,
            ),
            is_running=True,
        )
        QApplication.processEvents()

        package = build_task_unit_package(self._graph, unit_id=batch_item.unit_id, mode=TaskMode.OPTIMIZE)
        self._start_batch_worker(package)

    def _start_batch_worker(self, package) -> None:
        if self._current_project_path is None or self._batch_run_config is None:
            return
        self._batch_run_thread = QThread(self)
        self._batch_run_worker = _BatchOptimizationWorker(
            package=package,
            project_root=self._current_project_path,
            config=self._batch_run_config,
        )
        self._batch_run_worker.moveToThread(self._batch_run_thread)
        self._batch_run_thread.started.connect(self._batch_run_worker.run)
        self._batch_run_worker.finished.connect(self._handle_batch_worker_finished)
        self._batch_run_worker.failed.connect(self._handle_batch_worker_failed)
        self._batch_run_worker.finished.connect(self._batch_run_thread.quit)
        self._batch_run_worker.failed.connect(self._batch_run_thread.quit)
        self._batch_run_thread.finished.connect(self._cleanup_batch_worker)
        self._batch_run_thread.start()

    def _handle_batch_worker_finished(self, result) -> None:
        if self._batch_run_report is None or self._current_project_path is None:
            return
        batch_item = self._batch_run_items[self._batch_run_item_index]
        report_item = self._batch_run_report.items[self._batch_run_item_index]
        report_item.output_dir = result.output_dir
        report_item.summary = result.summary
        report_item.validation_status = result.validation_report.status.value
        report_item.failure_category = result.failure_category.value if result.failure_category is not None else None
        if result.status.value == "optimized" and result.validation_report.status.value == "passed":
            report_item.status = BatchRunItemStatus.PASSED
        else:
            report_item.status = BatchRunItemStatus.BLOCKED
        self._finalize_batch_run_item(batch_item.unit_id, report_item.status)

    def _handle_batch_worker_failed(self, error: str) -> None:
        if self._batch_run_report is None:
            return
        batch_item = self._batch_run_items[self._batch_run_item_index]
        report_item = self._batch_run_report.items[self._batch_run_item_index]
        report_item.status = BatchRunItemStatus.FAILED
        report_item.error = error
        self._finalize_batch_run_item(batch_item.unit_id, report_item.status)

    def _finalize_batch_run_item(self, unit_id: str, status: BatchRunItemStatus) -> None:
        if self._batch_run_report is None or self._current_project_path is None:
            return
        report_item = self._batch_run_report.items[self._batch_run_item_index]
        report_item.finished_at_ms = self._now_ms()
        self._batch_run_status_by_unit[unit_id] = status
        write_batch_run_report(self._batch_run_report)
        self._optimization_history_by_unit = load_optimization_history(self._current_project_path)
        self._handle_task_unit_selected(unit_id)

        self._batch_run_item_index += 1
        if status is not BatchRunItemStatus.PASSED:
            self._block_remaining_batch_items(
                reason=tr(self._language, "batch_run.failure.blocked_reason"),
            )
            self._finish_batch_run(BatchRunStatus.FAILED)
            return

        QTimer.singleShot(0, self._run_next_batch_optimization_item)

    def _cleanup_batch_worker(self) -> None:
        if self._batch_run_worker is not None:
            self._batch_run_worker.deleteLater()
        if self._batch_run_thread is not None:
            self._batch_run_thread.wait(1000)
            self._batch_run_thread.deleteLater()
        self._batch_run_worker = None
        self._batch_run_thread = None

    def _block_remaining_batch_items(self, *, reason: str) -> None:
        if self._batch_run_report is None:
            return
        for report_item in self._batch_run_report.items[self._batch_run_item_index :]:
            if report_item.status is not BatchRunItemStatus.PENDING:
                continue
            report_item.status = BatchRunItemStatus.BLOCKED
            report_item.error = reason
            report_item.finished_at_ms = self._now_ms()
            self._batch_run_status_by_unit[report_item.unit_id] = BatchRunItemStatus.BLOCKED
        write_batch_run_report(self._batch_run_report)

    def _finish_batch_run(self, status: BatchRunStatus) -> None:
        if self._batch_run_report is None:
            return
        self._batch_run_report.status = status
        self._batch_run_report.finished_at_ms = self._now_ms()
        write_batch_run_report(self._batch_run_report)
        self._batch_run_current_unit_id = None
        self._refresh_batch_execution_views(
            status_text=self._batch_run_summary_text(self._batch_run_report),
            is_running=False,
        )
        dialog = BatchRunReportDialog(language=self._language, report=self._batch_run_report, parent=self)
        dialog.exec()
        self._batch_run_report = None
        self._batch_run_items = []
        self._batch_run_item_index = 0
        self._batch_run_stop_requested = False
        self._batch_run_config = None

    def _refresh_batch_execution_views(self, *, status_text: str | None = None, is_running: bool | None = None) -> None:
        effective_running = self._batch_run_report is not None if is_running is None else is_running
        text = status_text if status_text is not None else self._batch_run_summary_text(self._batch_run_report)
        self._task_graph_view.set_execution_state(self._batch_run_status_by_unit)
        self._task_batch_view.set_execution_state(
            status_by_unit=self._batch_run_status_by_unit,
            status_text=text,
            is_running=effective_running,
        )
        self._refresh_batch_monitor_panel()

    def _refresh_batch_monitor_panel(self) -> None:
        mode = self._task_batch_view.current_mode()
        batch = self._optimize_batch if mode is TaskMode.OPTIMIZE else self._translate_batch
        report = self._batch_run_report if mode is TaskMode.OPTIMIZE else None
        self._batch_monitor_panel.set_context(
            task_graph=self._task_graph,
            batch=batch,
            report=report,
            mode=mode,
            current_running_unit_id=self._batch_run_current_unit_id,
            optimization_history_by_unit=self._optimization_history_by_unit,
        )

    def _batch_run_summary_text(self, report: BatchRunReport | None) -> str:
        if report is None:
            return tr(self._language, "task_batch_view.execution.idle")
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
            "task_batch_view.execution.summary",
            status=tr(self._language, f"batch_run.status.{report.status.value}"),
            pending=counts[BatchRunItemStatus.PENDING],
            running=counts[BatchRunItemStatus.RUNNING],
            passed=counts[BatchRunItemStatus.PASSED],
            failed=counts[BatchRunItemStatus.FAILED],
            blocked=counts[BatchRunItemStatus.BLOCKED],
        )

    def _selected_phase_index_for_unit(self, unit_id: str | None) -> int | None:
        if self._optimize_batch is None or unit_id is None:
            return None
        item = next((candidate for candidate in self._optimize_batch.items if candidate.unit_id == unit_id), None)
        return item.phase_index if item is not None else None

    def _now_ms(self) -> int:
        from time import time

        return int(time() * 1000)

    def _export_task_unit_package(self, unit_id: str, mode_value: str) -> None:
        if self._graph is None or self._current_project_path is None:
            return
        try:
            mode = TaskMode(mode_value)
            package = build_task_unit_package(self._graph, unit_id=unit_id, mode=mode)
        except Exception as error:  # pragma: no cover
            QMessageBox.warning(
                self,
                tr(self._language, "task_package.dialog.export_error_title"),
                tr(self._language, "task_package.dialog.export_error_body", error=str(error)),
            )
            return

        safe_unit_id = "".join(
            character if character.isalnum() or character in {"-", "_", "."} else "_"
            for character in f"{unit_id}.{mode.value}.task_unit_package"
        )
        file_name, _selected_filter = QFileDialog.getSaveFileName(
            self,
            tr(self._language, "task_package.dialog.export_title"),
            str(self._current_project_path / f"{safe_unit_id}.json"),
            tr(self._language, "task_package.dialog.export_filter"),
        )
        if not file_name:
            return

        try:
            Path(file_name).write_text(
                json.dumps(task_unit_package_to_dict(package), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.warning(
                self,
                tr(self._language, "task_package.dialog.export_error_title"),
                tr(self._language, "task_package.dialog.export_error_body", error=str(error)),
            )
            return

        QMessageBox.information(
            self,
            tr(self._language, "task_package.dialog.export_success_title"),
            tr(self._language, "task_package.dialog.export_success_body", path=file_name),
        )

    def _run_task_unit_optimization(self, unit_id: str) -> None:
        if self._graph is None or self._current_project_path is None:
            return
        try:
            config = self._resolve_model_config(interactive=True)
            if config is None:
                return
            package = build_task_unit_package(self._graph, unit_id=unit_id, mode=TaskMode.OPTIMIZE)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                result = execute_optimization(package, project_root=self._current_project_path, config=config)
            finally:
                QApplication.restoreOverrideCursor()
        except (OptimizationConfigError, OptimizationExecutionError, OSError) as error:
            QMessageBox.warning(
                self,
                tr(self._language, "task.dialog.optimize_error_title"),
                tr(self._language, "task.dialog.optimize_error_body", error=str(error)),
            )
            return

        diff_text = Path(result.diff_path).read_text(encoding="utf-8", errors="replace")
        dialog = OptimizationReviewDialog(
            language=self._language,
            result=result,
            diff_text=diff_text,
            parent=self,
        )
        dialog.apply_requested.connect(lambda: self._apply_optimization_patch(dialog, result, unit_id))
        dialog.rollback_requested.connect(lambda: self._rollback_optimization_patch(dialog, result, unit_id))
        dialog.exec()

    def _open_saved_optimization_history(self, unit_id: str, output_dir: str) -> None:
        output_path = Path(output_dir)
        try:
            result = load_saved_optimization_result(output_path)
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as error:
            QMessageBox.warning(
                self,
                tr(self._language, "task_history.dialog.open_error_title"),
                tr(self._language, "task_history.dialog.open_error_body", error=str(error)),
            )
            return

        diff_path = Path(result.diff_path)
        diff_text = diff_path.read_text(encoding="utf-8", errors="replace") if diff_path.is_file() else ""
        dialog = OptimizationReviewDialog(
            language=self._language,
            result=result,
            diff_text=diff_text,
            parent=self,
        )
        apply_result = load_saved_apply_result(output_path)
        rollback_result = load_saved_rollback_result(output_path)
        if apply_result is not None and rollback_result is None:
            dialog.set_applied_result(apply_result)
        elif rollback_result is not None:
            dialog.set_rollback_result(rollback_result)
        dialog.apply_requested.connect(lambda: self._apply_optimization_patch(dialog, result, unit_id))
        dialog.rollback_requested.connect(lambda: self._rollback_optimization_patch(dialog, result, unit_id))
        dialog.exec()

    def _apply_optimization_patch(
        self,
        dialog: OptimizationReviewDialog,
        result,
        unit_id: str,
    ) -> None:
        if self._current_project_path is None:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                apply_result = apply_optimization_result(result, project_root=self._current_project_path)
            finally:
                QApplication.restoreOverrideCursor()
        except OptimizationExecutionError as error:
            QMessageBox.warning(
                self,
                tr(self._language, "optimize_apply.error_title"),
                tr(self._language, "optimize_apply.error_body", error=str(error)),
            )
            return

        dialog.set_applied_result(apply_result)
        self._reload_project_after_workspace_change(unit_id)
        QMessageBox.information(
            self,
            tr(self._language, "optimize_apply.success_title"),
            tr(
                self._language,
                "optimize_apply.success_body",
                status=apply_result.validation_report.status.value,
            ),
        )

    def _rollback_optimization_patch(
        self,
        dialog: OptimizationReviewDialog,
        result,
        unit_id: str,
    ) -> None:
        if self._current_project_path is None:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                rollback_result = rollback_optimization_result(result, project_root=self._current_project_path)
            finally:
                QApplication.restoreOverrideCursor()
        except OptimizationExecutionError as error:
            QMessageBox.warning(
                self,
                tr(self._language, "optimize_rollback.error_title"),
                tr(self._language, "optimize_rollback.error_body", error=str(error)),
            )
            return

        dialog.set_rollback_result(rollback_result)
        self._reload_project_after_workspace_change(unit_id)
        QMessageBox.information(
            self,
            tr(self._language, "optimize_rollback.success_title"),
            tr(
                self._language,
                "optimize_rollback.success_body",
                status=rollback_result.validation_report.status.value,
            ),
        )

    def _reload_project_after_workspace_change(self, unit_id: str) -> None:
        if self._current_project_path is None:
            return
        self._load_project(self._current_project_path)
        if self._graph_mode in {"tasks", "batches"}:
            if self._task_graph is None:
                return
            if any(unit.id == unit_id for unit in self._task_graph.units):
                self._handle_task_unit_selected(unit_id)

    def _export_task_batch(self, mode_value: str) -> None:
        if self._current_project_path is None:
            return
        try:
            mode = TaskMode(mode_value)
            batch = self._optimize_batch if mode is TaskMode.OPTIMIZE else self._translate_batch
            if batch is None:
                raise ValueError("Task batch is not available")
        except Exception as error:  # pragma: no cover
            QMessageBox.warning(
                self,
                tr(self._language, "task_batch.dialog.export_error_title"),
                tr(self._language, "task_batch.dialog.export_error_body", error=str(error)),
            )
            return

        file_name, _selected_filter = QFileDialog.getSaveFileName(
            self,
            tr(self._language, "task_batch.dialog.export_title"),
            str(self._current_project_path / f"{mode.value}.task_batch.json"),
            tr(self._language, "task_batch.dialog.export_filter"),
        )
        if not file_name:
            return

        try:
            Path(file_name).write_text(
                json.dumps(task_batch_to_dict(batch), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.warning(
                self,
                tr(self._language, "task_batch.dialog.export_error_title"),
                tr(self._language, "task_batch.dialog.export_error_body", error=str(error)),
            )
            return

        QMessageBox.information(
            self,
            tr(self._language, "task_batch.dialog.export_success_title"),
            tr(self._language, "task_batch.dialog.export_success_body", path=file_name),
        )

    def _export_task_batch_phase_for_unit(self, unit_id: str, mode_value: str) -> None:
        if self._current_project_path is None:
            return
        try:
            mode = TaskMode(mode_value)
            batch = self._optimize_batch if mode is TaskMode.OPTIMIZE else self._translate_batch
            if batch is None:
                raise ValueError("Task batch is not available")
            selected_item = next((item for item in batch.items if item.unit_id == unit_id), None)
            if selected_item is None:
                raise ValueError("Selected task unit is not available in the current batch")
            phase_items = [item for item in batch.items if item.phase_index == selected_item.phase_index]
            phase_batch = TaskBatch(
                mode=mode,
                items=phase_items,
                phases=[
                    TaskBatchPhase(
                        index=selected_item.phase_index,
                        item_ids=[item.id for item in phase_items],
                    )
                ],
            )
        except Exception as error:  # pragma: no cover
            QMessageBox.warning(
                self,
                tr(self._language, "task_batch.dialog.export_error_title"),
                tr(self._language, "task_batch.dialog.export_error_body", error=str(error)),
            )
            return

        file_name, _selected_filter = QFileDialog.getSaveFileName(
            self,
            tr(self._language, "task_batch.dialog.export_title"),
            str(self._current_project_path / f"{mode.value}.phase_{selected_item.phase_index}.task_batch.json"),
            tr(self._language, "task_batch.dialog.export_filter"),
        )
        if not file_name:
            return

        try:
            Path(file_name).write_text(
                json.dumps(task_batch_to_dict(phase_batch), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.warning(
                self,
                tr(self._language, "task_batch.dialog.export_error_title"),
                tr(self._language, "task_batch.dialog.export_error_body", error=str(error)),
            )
            return

        QMessageBox.information(
            self,
            tr(self._language, "task_batch.dialog.export_success_title"),
            tr(self._language, "task_batch.dialog.export_success_body", path=file_name),
        )

    def _set_graph_controls_enabled(self, enabled: bool) -> None:
        self._update_dependency_controls()
        if not enabled:
            for button in self._graph_mode_buttons.values():
                button.setEnabled(False)
