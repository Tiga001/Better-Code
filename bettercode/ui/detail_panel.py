from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bettercode.graph_analysis import GraphInsights
from bettercode.models import FileDetail, GraphNode, NodeKind, ProjectGraph


class DetailPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = QLabel("Node Details")
        self._subtitle = QLabel("Import a project and click a node to inspect it.")
        self._role_chip = QLabel("Role")
        self._syntax_chip = QLabel("Syntax")
        self._path = QLabel("-")
        self._module = QLabel("-")
        self._syntax = QLabel("Syntax: -")
        self._summary = QLabel("Classes: - · Functions: - · Imports: -")
        self._dependencies = self._create_list_widget(max_height=120)
        self._dependents = self._create_list_widget(max_height=120)
        self._imports = self._create_list_widget(max_height=150)
        self._classes = self._create_list_widget(max_height=120)
        self._functions = self._create_list_widget(max_height=120)
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMinimumHeight(260)
        self._preview.setPlaceholderText("No source summary available.")
        self._title.setObjectName("detailTitle")
        self._subtitle.setObjectName("detailHelper")
        self._path.setObjectName("detailMeta")
        self._module.setObjectName("detailMeta")
        self._syntax.setObjectName("detailMeta")
        self._summary.setObjectName("detailMeta")
        self._preview.setObjectName("detailPreview")
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
                "Dependency Surface",
                ("Depends On", self._dependencies),
                ("Depended On By", self._dependents),
            )
        )
        content_layout.addWidget(self._build_section_card("Import Trace", self._imports))
        content_layout.addWidget(
            self._build_two_section_card(
                "Code Structure",
                ("Classes", self._classes),
                ("Functions", self._functions),
            )
        )
        content_layout.addWidget(self._build_section_card("Source Summary", self._preview))
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
        self.clear_panel()

    def clear_panel(self) -> None:
        self._title.setText("Node Details")
        self._subtitle.setText("Import a project and click a node to inspect it.")
        self._role_chip.setText("No file role")
        self._syntax_chip.setText("Syntax unknown")
        self._apply_chip_style(self._role_chip, "neutral")
        self._apply_chip_style(self._syntax_chip, "neutral")
        self._path.setText("-")
        self._module.setText("-")
        self._syntax.setText("Syntax: -")
        self._summary.setText("Classes: - · Functions: - · Imports: -")
        self._set_placeholder(self._dependencies, "No dependency nodes")
        self._set_placeholder(self._dependents, "No dependent nodes")
        self._set_placeholder(self._imports, "No imports")
        self._set_placeholder(self._classes, "No classes")
        self._set_placeholder(self._functions, "No functions")
        self._preview.clear()

    def set_selection(
        self,
        graph: ProjectGraph | None,
        insights: GraphInsights | None,
        node: GraphNode | None,
    ) -> None:
        if graph is None or insights is None or node is None:
            self.clear_panel()
            return

        self._title.setText(node.label)
        self._subtitle.setText("Single-file analysis snapshot")
        self._role_chip.setText(self._kind_label(node.kind))
        self._apply_chip_style(self._role_chip, self._role_tone(node.kind))
        self._path.setText(f"Path: {node.path or '-'}")
        self._module.setText(f"Module: {node.module or '-'}")

        node_lookup = {candidate.id: candidate for candidate in graph.nodes}
        self._populate_relationships(
            self._dependencies,
            insights.outgoing_node_ids.get(node.id, []),
            node_lookup,
            empty_message="No dependency nodes",
        )
        self._populate_relationships(
            self._dependents,
            insights.incoming_node_ids.get(node.id, []),
            node_lookup,
            empty_message="No dependent nodes",
        )

        detail: FileDetail | None = graph.file_details.get(node.id)
        if detail is None:
            self._syntax_chip.setText("External node")
            self._apply_chip_style(self._syntax_chip, "neutral")
            self._syntax.setText("Syntax: not applicable")
            self._summary.setText("Classes: 0 · Functions: 0 · Imports: 0")
            self._set_placeholder(self._imports, "External dependency node")
            self._set_placeholder(self._classes, "No classes")
            self._set_placeholder(self._functions, "No functions")
            self._preview.setPlainText("")
            return

        if detail.syntax_error:
            self._syntax_chip.setText("Syntax error")
            self._apply_chip_style(self._syntax_chip, "error")
            self._syntax.setText(f"Syntax Error: {detail.syntax_error}")
        else:
            self._syntax_chip.setText("Syntax OK")
            self._apply_chip_style(self._syntax_chip, "ok")
            self._syntax.setText("Syntax: OK")
        self._summary.setText(
            f"Classes: {len(detail.classes)} · Functions: {len(detail.functions)} · Imports: {len(detail.imports)}"
        )

        if detail.imports:
            self._imports.clear()
            for import_record in detail.imports:
                self._imports.addItem(
                    QListWidgetItem(f"{import_record.module} [{import_record.kind.value}] (L{import_record.line})")
                )
        else:
            self._set_placeholder(self._imports, "No imports")

        if detail.classes:
            self._classes.clear()
            for class_summary in detail.classes:
                self._classes.addItem(QListWidgetItem(f"{class_summary.name} (L{class_summary.line})"))
        else:
            self._set_placeholder(self._classes, "No classes")

        if detail.functions:
            self._functions.clear()
            for function_summary in detail.functions:
                self._functions.addItem(QListWidgetItem(f"{function_summary.name} (L{function_summary.line})"))
        else:
            self._set_placeholder(self._functions, "No functions")

        preview_parts = []
        if detail.syntax_error:
            preview_parts.append(f"# Syntax error: {detail.syntax_error}")
            preview_parts.append("")
        preview_parts.append(detail.source_preview or "# Empty file")
        self._preview.setPlainText("\n".join(preview_parts))

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
        for related_node in sorted((node_lookup[node_id] for node_id in node_ids if node_id in node_lookup), key=self._sort_key):
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

    def _build_section_card(self, title: str, widget: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self._section_label(title))
        layout.addWidget(widget)
        return frame

    def _build_two_section_card(
        self,
        title: str,
        first: tuple[str, QWidget],
        second: tuple[str, QWidget],
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self._section_label(title))
        layout.addWidget(self._subsection_label(first[0]))
        layout.addWidget(first[1])
        layout.addWidget(self._subsection_label(second[0]))
        layout.addWidget(second[1])
        return frame

    def _sort_key(self, node: GraphNode) -> tuple[int, str]:
        return (0 if node.kind is NodeKind.EXTERNAL_PACKAGE else 1, (node.path or node.label).lower())

    def _role_tone(self, kind: NodeKind) -> str:
        if kind is NodeKind.LEAF_FILE:
            return "leaf"
        if kind is NodeKind.PYTHON_FILE:
            return "file"
        return "external"

    def _apply_chip_style(self, label: QLabel, tone: str) -> None:
        styles = {
            "leaf": "background:#123f36;color:#a7f3d0;border:1px solid #2bb58e;",
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
            return "Dependency leaf"
        if kind is NodeKind.PYTHON_FILE:
            return "Python file"
        return "External package"
