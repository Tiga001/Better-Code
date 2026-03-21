from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from bettercode.graph_analysis import GraphInsights
from bettercode.i18n import LanguageCode, tr
from bettercode.models import FileDetail, GraphNode, ImportKind, NodeKind, ProjectGraph


class DetailPanel(QWidget):
    def __init__(self, parent: QWidget | None = None, *, language: LanguageCode = "en") -> None:
        super().__init__(parent)
        self._language: LanguageCode = language
        self._current_graph: ProjectGraph | None = None
        self._current_insights: GraphInsights | None = None
        self._current_node: GraphNode | None = None

        self._title = QLabel()
        self._subtitle = QLabel()
        self._role_chip = QLabel()
        self._syntax_chip = QLabel()
        self._path = QLabel("-")
        self._module = QLabel("-")
        self._syntax = QLabel()
        self._summary = QLabel()
        self._dependencies = self._create_list_widget(max_height=120)
        self._dependents = self._create_list_widget(max_height=120)
        self._imports = self._create_list_widget(max_height=150)
        self._classes = self._create_list_widget(max_height=120)
        self._functions = self._create_list_widget(max_height=120)
        self._dependency_surface_title = self._section_label("")
        self._depends_on_title = self._subsection_label("")
        self._depended_on_by_title = self._subsection_label("")
        self._import_trace_title = self._section_label("")
        self._code_structure_title = self._section_label("")
        self._classes_title = self._subsection_label("")
        self._functions_title = self._subsection_label("")

        self._title.setObjectName("detailTitle")
        self._subtitle.setObjectName("detailHelper")
        self._path.setObjectName("detailMeta")
        self._module.setObjectName("detailMeta")
        self._syntax.setObjectName("detailMeta")
        self._summary.setObjectName("detailMeta")
        for chip in [self._role_chip, self._syntax_chip]:
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
                (self._depends_on_title, self._dependencies),
                (self._depended_on_by_title, self._dependents),
            )
        )
        content_layout.addWidget(self._build_section_card(self._import_trace_title, self._imports))
        content_layout.addWidget(
            self._build_two_section_card(
                self._code_structure_title,
                (self._classes_title, self._classes),
                (self._functions_title, self._functions),
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

        self._subtitle.setWordWrap(True)
        self._path.setWordWrap(True)
        self._module.setWordWrap(True)
        self._syntax.setWordWrap(True)
        self._summary.setWordWrap(True)
        self._apply_static_text()
        self.clear_panel()

    def set_language(self, language: LanguageCode) -> None:
        self._language = language
        self._apply_static_text()
        if self._current_graph is None or self._current_insights is None or self._current_node is None:
            self.clear_panel()
            return
        self.set_selection(self._current_graph, self._current_insights, self._current_node)

    def clear_panel(self) -> None:
        self._current_graph = None
        self._current_insights = None
        self._current_node = None
        self._title.setText(tr(self._language, "detail.title.default"))
        self._subtitle.setText(tr(self._language, "detail.subtitle.default"))
        self._role_chip.setText(tr(self._language, "detail.role.empty"))
        self._syntax_chip.setText(tr(self._language, "detail.syntax.unknown"))
        self._apply_chip_style(self._role_chip, "neutral")
        self._apply_chip_style(self._syntax_chip, "neutral")
        self._path.setText("-")
        self._module.setText("-")
        self._syntax.setText(tr(self._language, "detail.syntax.empty"))
        self._summary.setText(tr(self._language, "detail.summary.empty"))
        self._set_placeholder(self._dependencies, tr(self._language, "detail.placeholder.no_dependency_nodes"))
        self._set_placeholder(self._dependents, tr(self._language, "detail.placeholder.no_dependent_nodes"))
        self._set_placeholder(self._imports, tr(self._language, "detail.placeholder.no_imports"))
        self._set_placeholder(self._classes, tr(self._language, "detail.placeholder.no_classes"))
        self._set_placeholder(self._functions, tr(self._language, "detail.placeholder.no_functions"))

    def set_selection(
        self,
        graph: ProjectGraph | None,
        insights: GraphInsights | None,
        node: GraphNode | None,
    ) -> None:
        if graph is None or insights is None or node is None:
            self.clear_panel()
            return

        self._current_graph = graph
        self._current_insights = insights
        self._current_node = node

        self._title.setText(node.label)
        self._subtitle.setText(tr(self._language, "detail.subtitle.selected"))
        self._role_chip.setText(self._kind_label(node.kind))
        self._apply_chip_style(self._role_chip, self._role_tone(node.kind))
        self._path.setText(tr(self._language, "detail.path.value", path=node.path or "-"))
        self._module.setText(tr(self._language, "detail.module.value", module=node.module or "-"))

        node_lookup = {candidate.id: candidate for candidate in graph.nodes}
        self._populate_relationships(
            self._dependencies,
            insights.outgoing_node_ids.get(node.id, []),
            node_lookup,
            empty_message=tr(self._language, "detail.placeholder.no_dependency_nodes"),
        )
        self._populate_relationships(
            self._dependents,
            insights.incoming_node_ids.get(node.id, []),
            node_lookup,
            empty_message=tr(self._language, "detail.placeholder.no_dependent_nodes"),
        )

        detail: FileDetail | None = graph.file_details.get(node.id)
        if detail is None:
            self._syntax_chip.setText(tr(self._language, "detail.syntax.external_chip"))
            self._apply_chip_style(self._syntax_chip, "neutral")
            self._syntax.setText(tr(self._language, "detail.syntax.not_applicable"))
            self._summary.setText(tr(self._language, "detail.summary.value", classes=0, functions=0, imports=0))
            self._set_placeholder(self._imports, tr(self._language, "detail.placeholder.external_node"))
            self._set_placeholder(self._classes, tr(self._language, "detail.placeholder.no_classes"))
            self._set_placeholder(self._functions, tr(self._language, "detail.placeholder.no_functions"))
            return

        if detail.syntax_error:
            self._syntax_chip.setText(tr(self._language, "detail.syntax.error_chip"))
            self._apply_chip_style(self._syntax_chip, "error")
            self._syntax.setText(tr(self._language, "detail.syntax.error_value", error=detail.syntax_error))
        else:
            self._syntax_chip.setText(tr(self._language, "detail.syntax.ok_chip"))
            self._apply_chip_style(self._syntax_chip, "ok")
            self._syntax.setText(tr(self._language, "detail.syntax.ok_value"))
        self._summary.setText(
            tr(
                self._language,
                "detail.summary.value",
                classes=len(detail.classes),
                functions=len(detail.functions),
                imports=len(detail.imports),
            )
        )

        if detail.imports:
            self._imports.clear()
            for import_record in detail.imports:
                self._imports.addItem(
                    QListWidgetItem(
                        f"{import_record.module} [{self._import_kind_label(import_record.kind)}] (L{import_record.line})"
                    )
                )
        else:
            self._set_placeholder(self._imports, tr(self._language, "detail.placeholder.no_imports"))

        if detail.classes:
            self._classes.clear()
            for class_summary in detail.classes:
                self._classes.addItem(QListWidgetItem(f"{class_summary.name} (L{class_summary.line})"))
        else:
            self._set_placeholder(self._classes, tr(self._language, "detail.placeholder.no_classes"))

        if detail.functions:
            self._functions.clear()
            for function_summary in detail.functions:
                self._functions.addItem(QListWidgetItem(f"{function_summary.name} (L{function_summary.line})"))
        else:
            self._set_placeholder(self._functions, tr(self._language, "detail.placeholder.no_functions"))

    def _apply_static_text(self) -> None:
        self._dependency_surface_title.setText(tr(self._language, "detail.section.dependency_surface"))
        self._depends_on_title.setText(tr(self._language, "detail.section.depends_on"))
        self._depended_on_by_title.setText(tr(self._language, "detail.section.depended_on_by"))
        self._import_trace_title.setText(tr(self._language, "detail.section.import_trace"))
        self._code_structure_title.setText(tr(self._language, "detail.section.code_structure"))
        self._classes_title.setText(tr(self._language, "detail.section.classes"))
        self._functions_title.setText(tr(self._language, "detail.section.functions"))

    def _populate_relationships(
        self,
        widget: QListWidget,
        node_ids: list[str],
        node_lookup: dict[str, GraphNode],
        *,
        empty_message: str,
    ) -> None:
        if not node_ids:
            self._set_placeholder(widget, empty_message)
            return

        widget.clear()
        related_nodes = (node_lookup[node_id] for node_id in node_ids if node_id in node_lookup)
        for related_node in sorted(related_nodes, key=self._sort_key):
            descriptor = related_node.path or related_node.label
            widget.addItem(QListWidgetItem(f"{descriptor} [{self._kind_label(related_node.kind)}]"))

    def _set_placeholder(self, widget: QListWidget, message: str) -> None:
        widget.clear()
        widget.addItem(QListWidgetItem(message))

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
        status_row_layout.addWidget(self._role_chip)
        status_row_layout.addWidget(self._syntax_chip)
        status_row_layout.addStretch(1)
        layout.addWidget(status_row)
        layout.addWidget(self._subtitle)
        layout.addWidget(self._path)
        layout.addWidget(self._module)
        layout.addWidget(self._syntax)
        layout.addWidget(self._summary)
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

    def _sort_key(self, node: GraphNode) -> tuple[int, str]:
        return (0 if node.kind is NodeKind.EXTERNAL_PACKAGE else 1, (node.path or node.label).lower())

    def _role_tone(self, kind: NodeKind) -> str:
        if kind is NodeKind.LEAF_FILE:
            return "leaf"
        if kind is NodeKind.TOP_LEVEL_SCRIPT:
            return "top_script"
        if kind is NodeKind.PYTHON_FILE:
            return "file"
        return "external"

    def _apply_chip_style(self, label: QLabel, tone: str) -> None:
        styles = {
            "leaf": "background:#123f36;color:#a7f3d0;border:1px solid #2bb58e;",
            "top_script": "background:#3d2155;color:#ebd4ff;border:1px solid #b47dff;",
            "file": "background:#142d63;color:#c8d8ff;border:1px solid #4e79ff;",
            "external": "background:#4b2a10;color:#ffd8b1;border:1px solid #ff9a48;",
            "ok": "background:#103629;color:#9ef0c8;border:1px solid #34c38f;",
            "error": "background:#4a1820;color:#ffc3cb;border:1px solid #ff6b78;",
            "neutral": "background:#1a2638;color:#c4d0e3;border:1px solid #314863;",
        }
        label.setStyleSheet(
            f"padding: 6px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; {styles[tone]}"
        )

    def _kind_label(self, kind: NodeKind) -> str:
        if kind is NodeKind.LEAF_FILE:
            return tr(self._language, "detail.kind.leaf")
        if kind is NodeKind.TOP_LEVEL_SCRIPT:
            return tr(self._language, "detail.kind.top_script")
        if kind is NodeKind.PYTHON_FILE:
            return tr(self._language, "detail.kind.file")
        return tr(self._language, "detail.kind.external")

    def _import_kind_label(self, kind: ImportKind) -> str:
        return tr(self._language, f"import_kind.{kind.value}")
