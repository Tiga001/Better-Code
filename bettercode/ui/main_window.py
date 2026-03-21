from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
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

from bettercode.graph_analysis import GraphInsights, analyze_graph_structure
from bettercode.i18n import LanguageCode, tr
from bettercode.models import FileDetail, GraphNode, NodeKind, ProjectGraph
from bettercode.parser import ProjectAnalyzer
from bettercode.ui.code_block_dialog import CodeBlockDialog
from bettercode.ui.detail_panel import DetailPanel
from bettercode.ui.graph_view import DependencyGraphView
from bettercode.ui.subsystem_view import SubsystemCanvasView


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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._language: LanguageCode = "zh"
        self._graph_mode = "dependency"
        self._graph_modes = [
            ("dependency", "graph_mode.dependency"),
            ("subsystems", "graph_mode.subsystems"),
        ]
        self.setWindowTitle(tr(self._language, "app.name"))
        self.resize(1480, 920)

        self._analyzer = ProjectAnalyzer()
        self._graph: ProjectGraph | None = None
        self._insights: GraphInsights | None = None
        self._selected_node_id: str | None = None
        self._current_project_path: Path | None = None
        self._search_matches: list[str] = []
        self._search_match_index = -1

        self._title_label = QLabel()
        self._language_label = QLabel()
        self._language_selector = QComboBox()
        self._import_button = QPushButton()
        self._refresh_button = QPushButton()

        self._graph_view = DependencyGraphView()
        self._subsystem_view = SubsystemCanvasView()
        self._detail_panel = DetailPanel(language=self._language)
        self._search_input = QLineEdit()
        self._focus_filter = QComboBox()
        self._neighbor_label = QLabel()
        self._neighbor_filter = QComboBox()
        self._search_result_label = QLabel()
        self._next_match_button = QPushButton()
        self._reset_view_button = QPushButton()
        self._graph_mode_buttons: dict[str, QPushButton] = {}
        self._canvas_stack = QStackedWidget()
        self._legend_labels: dict[str, QLabel] = {}
        self._splitter: QSplitter | None = None

        self._graph_view.node_selected.connect(self._handle_node_selected)
        self._graph_view.node_double_clicked.connect(self._open_code_block_dialog)
        self._graph_view.background_clicked.connect(self._handle_graph_background_clicked)
        self._subsystem_view.node_selected.connect(self._handle_node_selected)
        self._subsystem_view.node_double_clicked.connect(self._open_code_block_dialog)
        self._subsystem_view.background_clicked.connect(self._handle_graph_background_clicked)
        self._language_selector.currentIndexChanged.connect(self._handle_language_changed)

        self._build_ui()
        self._apply_styles()
        self._set_graph_controls_enabled(False)
        self._apply_language()

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
        self._import_button.clicked.connect(self._select_project_directory)
        self._refresh_button.clicked.connect(self._refresh_current_project)
        actions_wrap.addWidget(self._language_label)
        actions_wrap.addWidget(self._language_selector)
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
        controls_layout.addWidget(self._search_input, stretch=1)
        controls_layout.addWidget(self._focus_filter)
        controls_layout.addWidget(self._neighbor_label)
        controls_layout.addWidget(self._neighbor_filter)
        controls_layout.addWidget(self._next_match_button)
        controls_layout.addWidget(self._reset_view_button)
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
        canvas_layout.addWidget(self._canvas_stack, stretch=1)
        graph_layout.addWidget(canvas_frame, stretch=1)

        detail_panel = QFrame()
        detail_panel.setObjectName("inspectorPanel")
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(12)
        detail_layout.addWidget(self._detail_panel)

        splitter.addWidget(graph_panel)
        splitter.addWidget(detail_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1040, 420])
        self._splitter = splitter
        root_layout.addWidget(splitter, stretch=1)

        self.setCentralWidget(root)

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
        ]

        for key, swatch in legend_items:
            item = QWidget()
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(6)
            label = QLabel()
            self._legend_labels[key] = label
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
        self._import_button.setText(tr(self._language, "button.import_project"))
        self._refresh_button.setText(tr(self._language, "button.refresh"))
        self._next_match_button.setText(tr(self._language, "button.next_match"))
        self._reset_view_button.setText(tr(self._language, "button.reset_view"))
        self._neighbor_label.setText(tr(self._language, "neighbor.label"))
        self._rebuild_graph_mode_buttons()
        for key, label in self._legend_labels.items():
            label.setText(tr(self._language, key))
        self._search_input.setPlaceholderText(tr(self._language, "search.placeholder"))
        self._detail_panel.set_language(self._language)
        self._graph_view.set_language(self._language)
        self._subsystem_view.set_language(self._language)
        self._rebuild_language_selector()
        self._rebuild_focus_filter()
        self._rebuild_neighbor_filter()
        self._refresh_search_label()
        self._update_graph_mode_ui()

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

    def _load_project(self, project_path: Path) -> None:
        try:
            graph = self._analyzer.analyze(project_path)
        except Exception as error:  # pragma: no cover
            QMessageBox.critical(self, tr(self._language, "dialog.analysis_failed"), str(error))
            return

        self._graph = graph
        self._insights = analyze_graph_structure(graph)
        self._current_project_path = project_path
        self._graph_view.set_graph(graph, self._insights)
        self._graph_view.set_language(self._language)
        self._subsystem_view.set_graph(graph)
        self._subsystem_view.set_language(self._language)
        self._set_graph_controls_enabled(True)
        self._handle_node_selected(None)
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

    def _handle_graph_background_clicked(self) -> None:
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

    def _set_graph_mode(self, mode: str) -> None:
        if mode not in self._graph_mode_buttons:
            return
        self._graph_mode = mode
        self._update_graph_mode_ui()

    def _update_graph_mode_ui(self) -> None:
        has_graph = self._graph is not None
        for mode, button in self._graph_mode_buttons.items():
            button.setChecked(mode == self._graph_mode)
            button.setEnabled(has_graph)
        self._reset_view_button.setEnabled(has_graph)
        if self._graph_mode == "subsystems":
            self._canvas_stack.setCurrentWidget(self._subsystem_view)
        else:
            self._canvas_stack.setCurrentWidget(self._graph_view)
        if self._selected_node_id is None:
            self._detail_panel.clear_panel()
        else:
            self._handle_node_selected(self._selected_node_id)
        self._update_dependency_controls()

    def _update_dependency_controls(self) -> None:
        has_graph = self._graph is not None
        dependency_mode = self._graph_mode == "dependency"
        dependency_controls_enabled = has_graph and dependency_mode
        self._search_input.setEnabled(dependency_controls_enabled)
        self._focus_filter.setEnabled(dependency_controls_enabled)
        self._neighbor_filter.setEnabled(has_graph)
        self._neighbor_label.setEnabled(has_graph)
        self._next_match_button.setEnabled(dependency_controls_enabled and bool(self._search_matches))
        self._search_result_label.setEnabled(dependency_controls_enabled)

    def _handle_reset_view(self) -> None:
        if self._graph_mode == "subsystems":
            self._subsystem_view.reset_view()
            return
        self._graph_view.reset_view()

    def _apply_focus_and_search(self, *, auto_select: bool) -> None:
        if self._graph is None or self._insights is None:
            return

        focused_node_ids = self._focused_node_ids()
        self._graph_view.set_focused_node_ids(focused_node_ids)

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
            self._refresh_search_label()
            return

        query = self._search_input.text().strip().lower()
        visible_node_ids = self._focused_node_ids()
        candidate_nodes = [
            node
            for node in self._graph.nodes
            if visible_node_ids is None or node.id in visible_node_ids
        ]

        if not query:
            self._search_matches = []
            self._search_match_index = -1
            self._next_match_button.setEnabled(False)
            self._graph_view.set_search_match_node_ids(set())
            self._refresh_search_label()
            return

        self._search_matches = [
            node.id
            for node in candidate_nodes
            if self._node_matches_query(node, query)
        ]
        self._graph_view.set_search_match_node_ids(set(self._search_matches))
        self._next_match_button.setEnabled(bool(self._search_matches))
        self._refresh_search_label()

        if not self._search_matches:
            self._search_match_index = -1
            return

        if self._selected_node_id in self._search_matches:
            self._search_match_index = self._search_matches.index(self._selected_node_id)
            if auto_select:
                self._handle_node_selected(self._selected_node_id)
            return

        self._search_match_index = 0
        if auto_select:
            self._handle_node_selected(self._search_matches[0])

    def _select_next_search_match(self) -> None:
        if not self._search_matches:
            return
        self._search_match_index = (self._search_match_index + 1) % len(self._search_matches)
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

    def _node_matches_query(self, node: GraphNode, query: str) -> bool:
        haystacks = [node.label, node.path or "", node.module or ""]
        return any(query in haystack.lower() for haystack in haystacks)

    def _set_graph_controls_enabled(self, enabled: bool) -> None:
        self._update_dependency_controls()
        if not enabled:
            for button in self._graph_mode_buttons.values():
                button.setEnabled(False)
