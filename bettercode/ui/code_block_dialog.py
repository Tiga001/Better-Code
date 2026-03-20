from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bettercode.models import (
    AgentTaskSuitability,
    CodeBlockCall,
    CodeBlockKind,
    CodeBlockSummary,
    FileDetail,
    GraphNode,
    ProjectGraph,
)


class CodeBlockDialog(QDialog):
    def __init__(
        self,
        *,
        project_root: Path,
        graph: ProjectGraph | None,
        node: GraphNode,
        detail: FileDetail,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Code Blocks · {node.label}")
        self.resize(1060, 720)
        self.setModal(True)

        self._detail = detail
        self._source_lines = self._load_source_lines(project_root / detail.path)
        self._blocks_by_id = {block.id: block for block in detail.code_blocks}
        self._graph = graph
        self._global_blocks_by_id: dict[str, CodeBlockSummary] = {}
        self._owner_details_by_block_id: dict[str, FileDetail] = {}
        self._node_by_id: dict[str, GraphNode] = {}
        self._calls_by_source: dict[str, list[CodeBlockCall]] = {}
        self._calls_by_target: dict[str, list[CodeBlockCall]] = {}
        if graph is not None:
            self._node_by_id = {candidate.id: candidate for candidate in graph.nodes}
            for file_detail in graph.file_details.values():
                for block in file_detail.code_blocks:
                    self._global_blocks_by_id[block.id] = block
                    self._owner_details_by_block_id[block.id] = file_detail
                for call in file_detail.code_block_calls:
                    self._calls_by_source.setdefault(call.source_id, []).append(call)
                    self._calls_by_target.setdefault(call.target_id, []).append(call)
        else:
            self._global_blocks_by_id = dict(self._blocks_by_id)
            for block in detail.code_blocks:
                self._owner_details_by_block_id[block.id] = detail
            for call in detail.code_block_calls:
                self._calls_by_source.setdefault(call.source_id, []).append(call)
                self._calls_by_target.setdefault(call.target_id, []).append(call)

        self._title = QLabel(node.label)
        self._title.setObjectName("dialogTitle")
        self._meta = QLabel(f"Path: {detail.path}\nModule: {detail.module}")
        self._meta.setObjectName("dialogMeta")
        self._status = QLabel("Double-clicked file structure")
        self._status.setObjectName("dialogStatus")
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Code Block", "Lines"])
        self._kind_chip = QLabel("Block")
        self._fit_chip = QLabel("Agent fit")
        self._signature = QLabel("-")
        self._signature.setObjectName("dialogMeta")
        self._signature.setWordWrap(True)
        self._lines = QLabel("Lines: -")
        self._lines.setObjectName("dialogMeta")
        self._returns = QLabel("Returns: -")
        self._returns.setObjectName("dialogMeta")
        self._stats = QLabel("Depth: - · Calls out: - · Called by: -")
        self._stats.setObjectName("dialogMeta")
        self._parameters = self._create_list_widget(max_height=110)
        self._outgoing_calls = self._create_list_widget(max_height=110)
        self._incoming_calls = self._create_list_widget(max_height=110)
        self._agent_notes = self._create_list_widget(max_height=110)
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setObjectName("dialogPreview")
        self._preview.setPlaceholderText("Select a code block to inspect it.")

        self._build_ui()
        self._apply_styles()
        self._populate_tree()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("dialogHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 14)
        header_layout.setSpacing(8)
        header_layout.addWidget(self._title)
        header_layout.addWidget(self._status)
        header_layout.addWidget(self._meta)
        root_layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        tree_panel = QFrame()
        tree_panel.setObjectName("dialogPanel")
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(12, 12, 12, 12)
        tree_layout.setSpacing(8)
        tree_title = QLabel("File Blocks")
        tree_title.setObjectName("dialogSectionTitle")
        tree_layout.addWidget(tree_title)
        self._tree.itemSelectionChanged.connect(self._handle_tree_selection_changed)
        tree_layout.addWidget(self._tree)

        analysis_panel = QWidget()
        analysis_layout = QVBoxLayout(analysis_panel)
        analysis_layout.setContentsMargins(0, 0, 0, 0)
        analysis_layout.setSpacing(10)
        analysis_layout.addWidget(self._build_summary_card())
        analysis_layout.addWidget(
            self._build_two_section_card(
                "Block Call Links",
                ("Calls Out", self._outgoing_calls),
                ("Called By", self._incoming_calls),
            )
        )
        analysis_layout.addWidget(self._build_section_card("Agent Task Notes", self._agent_notes))
        analysis_layout.addWidget(self._build_section_card("Block Source", self._preview), stretch=1)

        splitter.addWidget(tree_panel)
        splitter.addWidget(analysis_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([330, 700])
        root_layout.addWidget(splitter, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog, QWidget {
                background: #101722;
                color: #e9eef7;
                font-family: Helvetica Neue, Arial, sans-serif;
                font-size: 13px;
            }
            QFrame#dialogHeader {
                background: #16283d;
                border: 1px solid #3d6490;
                border-radius: 16px;
            }
            QFrame#dialogPanel {
                background: #111a28;
                border: 1px solid #29405d;
                border-radius: 16px;
            }
            QLabel#dialogTitle {
                color: #f8fbff;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#dialogStatus {
                color: #9bd8ff;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#dialogMeta {
                color: #c1cee1;
                font-size: 12px;
            }
            QLabel#dialogSectionTitle {
                color: #f4f7fd;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#dialogSubsectionTitle {
                color: #8ecfff;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#dialogChip {
                padding: 6px 10px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 700;
            }
            QTreeWidget, QTextEdit, QListWidget {
                background: #0d1521;
                border: 1px solid #29405d;
                border-radius: 12px;
            }
            QTreeWidget::item, QListWidget::item {
                padding: 4px 2px;
            }
            """
        )

    def _populate_tree(self) -> None:
        self._tree.clear()
        if not self._detail.code_blocks:
            item = QTreeWidgetItem(["No extracted code blocks", "-"])
            self._tree.addTopLevelItem(item)
            self._set_list_content(self._parameters, [], "No parameters")
            self._set_list_content(self._outgoing_calls, [], "No block calls")
            self._set_list_content(self._incoming_calls, [], "No block callers")
            self._set_list_content(self._agent_notes, [], "No agent-task notes")
            self._signature.setText("Signature: -")
            self._lines.setText("Lines: -")
            self._returns.setText("Returns: -")
            self._stats.setText("Depth: - · Calls out: 0 · Called by: 0")
            self._preview.setPlainText("No classes, functions, or methods were extracted from this file.")
            return

        children_by_parent: dict[str | None, list[CodeBlockSummary]] = {}
        for block in self._detail.code_blocks:
            children_by_parent.setdefault(block.parent_id, []).append(block)

        for parent_id in children_by_parent:
            children_by_parent[parent_id].sort(key=lambda block: (block.line, block.name))

        for block in children_by_parent.get(None, []):
            self._tree.addTopLevelItem(self._create_tree_item(block, children_by_parent))

        self._tree.expandToDepth(1)
        first_item = self._tree.topLevelItem(0)
        if first_item is not None:
            self._tree.setCurrentItem(first_item)

    def _create_tree_item(
        self,
        block: CodeBlockSummary,
        children_by_parent: dict[str | None, list[CodeBlockSummary]],
    ) -> QTreeWidgetItem:
        label = block.signature or block.name
        item = QTreeWidgetItem([label, f"L{block.line}-{block.end_line}"])
        item.setData(0, Qt.UserRole, block.id)
        for child in children_by_parent.get(block.id, []):
            item.addChild(self._create_tree_item(child, children_by_parent))
        return item

    def _handle_tree_selection_changed(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return

        block_id = item.data(0, Qt.UserRole)
        if not block_id or block_id not in self._blocks_by_id:
            self._status.setText("No extracted block selected")
            return

        block = self._blocks_by_id[block_id]
        self._status.setText(
            f"{self._kind_label(block.kind)} · Lines {block.line}-{block.end_line}"
        )
        self._kind_chip.setText(self._kind_label(block.kind))
        self._apply_chip_style(self._kind_chip, self._kind_tone(block.kind))
        self._fit_chip.setText(self._task_fit_label(block.agent_task_fit))
        self._apply_chip_style(self._fit_chip, self._task_fit_tone(block.agent_task_fit))
        self._signature.setText(f"Signature: {block.signature or block.name}")
        self._lines.setText(f"Lines: {block.line}-{block.end_line}")
        self._returns.setText(f"Returns: {self._return_label(block)}")
        outgoing_calls = self._calls_by_source.get(block.id, [])
        incoming_calls = self._calls_by_target.get(block.id, [])
        child_count = sum(1 for candidate in self._detail.code_blocks if candidate.parent_id == block.id)
        self._stats.setText(
            f"Depth: {block.depth} · Child blocks: {child_count} · Calls out: {len(outgoing_calls)} · Called by: {len(incoming_calls)}"
        )
        self._set_list_content(self._parameters, block.parameters, "No explicit parameters")
        self._set_list_content(
            self._outgoing_calls,
            [self._call_display(call, direction="out") for call in outgoing_calls],
            "No block calls",
        )
        self._set_list_content(
            self._incoming_calls,
            [self._call_display(call, direction="in") for call in incoming_calls],
            "No block callers",
        )
        self._set_list_content(self._agent_notes, block.agent_task_reasons, "No agent-task notes")
        self._preview.setPlainText(self._source_excerpt(block))

    def _source_excerpt(self, block: CodeBlockSummary) -> str:
        start = max(block.line - 1, 0)
        end = min(block.end_line, len(self._source_lines))
        excerpt = self._source_lines[start:end]
        if not excerpt:
            return "# No source excerpt available"
        return "\n".join(excerpt)

    def _load_source_lines(self, file_path: Path) -> list[str]:
        try:
            return file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

    def _kind_label(self, kind: CodeBlockKind) -> str:
        if kind is CodeBlockKind.CLASS:
            return "Class"
        if kind is CodeBlockKind.METHOD:
            return "Method"
        return "Function"

    def _kind_tone(self, kind: CodeBlockKind) -> str:
        if kind is CodeBlockKind.CLASS:
            return "class"
        if kind is CodeBlockKind.METHOD:
            return "method"
        return "function"

    def _task_fit_label(self, fit: AgentTaskSuitability) -> str:
        if fit is AgentTaskSuitability.GOOD:
            return "Agent fit: good"
        if fit is AgentTaskSuitability.AVOID:
            return "Agent fit: avoid"
        return "Agent fit: caution"

    def _task_fit_tone(self, fit: AgentTaskSuitability) -> str:
        if fit is AgentTaskSuitability.GOOD:
            return "good"
        if fit is AgentTaskSuitability.AVOID:
            return "avoid"
        return "caution"

    def _return_label(self, block: CodeBlockSummary) -> str:
        if block.kind is CodeBlockKind.CLASS:
            return "n/a for class block"
        return block.return_summary or "Not declared"

    def _call_display(
        self,
        call: CodeBlockCall,
        *,
        direction: str,
    ) -> str:
        related_block_id = call.target_id if direction == "out" else call.source_id
        related_block = self._global_blocks_by_id.get(related_block_id)
        related_owner = self._owner_details_by_block_id.get(related_block_id)
        label = related_block.signature if related_block is not None and related_block.signature else (
            related_block.name if related_block is not None else related_block_id
        )
        owner_path = related_owner.path if related_owner is not None else "-"
        scope_label = "cross-file" if call.is_cross_file else "same-file"
        if direction == "out":
            return f"{label} [{owner_path}] ({scope_label}, L{call.line} via {call.expression})"
        return f"{label} [{owner_path}] ({scope_label}, L{call.line} via {call.expression})"

    def _build_summary_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dialogPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._section_label("Block Analysis"))
        chip_row = QWidget()
        chip_layout = QHBoxLayout(chip_row)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setSpacing(8)
        for chip in [self._kind_chip, self._fit_chip]:
            chip.setObjectName("dialogChip")
            chip.setAlignment(Qt.AlignCenter)
            chip_layout.addWidget(chip)
        chip_layout.addStretch(1)
        layout.addWidget(chip_row)
        layout.addWidget(self._signature)
        layout.addWidget(self._lines)
        layout.addWidget(self._returns)
        layout.addWidget(self._stats)
        layout.addWidget(self._subsection_label("Parameters"))
        layout.addWidget(self._parameters)
        return frame

    def _build_section_card(self, title: str, widget: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dialogPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
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
        frame.setObjectName("dialogPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._section_label(title))
        layout.addWidget(self._subsection_label(first[0]))
        layout.addWidget(first[1])
        layout.addWidget(self._subsection_label(second[0]))
        layout.addWidget(second[1])
        return frame

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("dialogSectionTitle")
        return label

    def _subsection_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("dialogSubsectionTitle")
        return label

    def _create_list_widget(self, *, max_height: int) -> QListWidget:
        widget = QListWidget()
        widget.setMaximumHeight(max_height)
        return widget

    def _set_list_content(self, widget: QListWidget, items: list[str], placeholder: str) -> None:
        widget.clear()
        if not items:
            widget.addItem(QListWidgetItem(placeholder))
            return
        for item in items:
            widget.addItem(QListWidgetItem(item))

    def _apply_chip_style(self, label: QLabel, tone: str) -> None:
        styles = {
            "class": "background:#213a67;color:#d4e1ff;border:1px solid #517ae8;",
            "function": "background:#154368;color:#bce6ff;border:1px solid #3ea0e5;",
            "method": "background:#18473f;color:#b9f4dd;border:1px solid #34c38f;",
            "good": "background:#103629;color:#9ef0c8;border:1px solid #34c38f;",
            "caution": "background:#4b3512;color:#ffdca8;border:1px solid #f2a93b;",
            "avoid": "background:#4a1820;color:#ffc3cb;border:1px solid #ff6b78;",
        }
        label.setStyleSheet(styles[tone])
