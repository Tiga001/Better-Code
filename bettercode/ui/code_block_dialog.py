from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bettercode.i18n import LanguageCode, tr
from bettercode.models import (
    AgentTaskSuitability,
    CodeBlockCall,
    CodeBlockKind,
    CodeBlockSummary,
    FileDetail,
    GraphNode,
    ProjectGraph,
    SymbolUsage,
    UsageConfidence,
    UsageKind,
)


class CodeBlockDialog(QDialog):
    def __init__(
        self,
        *,
        project_root: Path,
        graph: ProjectGraph | None,
        node: GraphNode,
        detail: FileDetail,
        language: LanguageCode = "en",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._language = language
        self._node = node
        self._detail = detail
        self._source_lines = self._load_source_lines(project_root / detail.path)
        self._blocks_by_id = {block.id: block for block in detail.code_blocks}
        self._graph = graph
        self._global_blocks_by_id: dict[str, CodeBlockSummary] = {}
        self._owner_details_by_block_id: dict[str, FileDetail] = {}
        self._details_by_node_id: dict[str, FileDetail] = {}
        self._calls_by_source: dict[str, list[CodeBlockCall]] = {}
        self._calls_by_target: dict[str, list[CodeBlockCall]] = {}
        self._usages_by_target: dict[str, list[SymbolUsage]] = {}
        if graph is not None:
            for file_detail in graph.file_details.values():
                self._details_by_node_id[file_detail.node_id] = file_detail
                for block in file_detail.code_blocks:
                    self._global_blocks_by_id[block.id] = block
                    self._owner_details_by_block_id[block.id] = file_detail
                for call in file_detail.code_block_calls:
                    self._calls_by_source.setdefault(call.source_id, []).append(call)
                    self._calls_by_target.setdefault(call.target_id, []).append(call)
                for usage in file_detail.symbol_usages:
                    self._usages_by_target.setdefault(usage.target_id, []).append(usage)
        else:
            self._global_blocks_by_id = dict(self._blocks_by_id)
            self._details_by_node_id[detail.node_id] = detail
            for block in detail.code_blocks:
                self._owner_details_by_block_id[block.id] = detail
            for call in detail.code_block_calls:
                self._calls_by_source.setdefault(call.source_id, []).append(call)
                self._calls_by_target.setdefault(call.target_id, []).append(call)
            for usage in detail.symbol_usages:
                self._usages_by_target.setdefault(usage.target_id, []).append(usage)

        self.setWindowTitle(tr(self._language, "code_blocks.window_title", label=node.label))
        self.resize(1320, 760)
        self.setModal(True)

        self._title = QLabel()
        self._title.setObjectName("dialogTitle")
        self._meta = QLabel()
        self._meta.setObjectName("dialogMeta")
        self._status = QLabel()
        self._status.setObjectName("dialogStatus")
        self._tree = QTreeWidget()
        self._kind_chip = QLabel()
        self._fit_chip = QLabel()
        self._signature = QLabel("-")
        self._signature.setObjectName("dialogMeta")
        self._signature.setWordWrap(True)
        self._lines = QLabel()
        self._lines.setObjectName("dialogMeta")
        self._returns = QLabel()
        self._returns.setObjectName("dialogMeta")
        self._stats = QLabel()
        self._stats.setObjectName("dialogMeta")
        self._parameters = self._create_list_widget(max_height=110)
        self._outgoing_calls = self._create_list_widget(max_height=110)
        self._incoming_calls = self._create_list_widget(max_height=110)
        self._usages = self._create_list_widget(max_height=130)
        self._agent_notes = self._create_list_widget(max_height=110)
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setObjectName("dialogPreview")

        self._tree_title = QLabel()
        self._tree_title.setObjectName("dialogSectionTitle")
        self._analysis_title = self._section_label("")
        self._parameters_title = self._subsection_label("")
        self._call_links_title = self._section_label("")
        self._calls_out_title = self._subsection_label("")
        self._called_by_title = self._subsection_label("")
        self._usages_title = self._section_label("")
        self._agent_notes_title = self._section_label("")
        self._source_title = self._section_label("")
        self._inspector_mode_group = QButtonGroup(self)
        self._inspector_mode_group.setExclusive(True)
        self._call_links_button = self._create_mode_button()
        self._usages_button = self._create_mode_button()
        self._agent_notes_button = self._create_mode_button()
        self._inspector_mode_group.addButton(self._call_links_button)
        self._inspector_mode_group.addButton(self._usages_button)
        self._inspector_mode_group.addButton(self._agent_notes_button)
        self._inspector_stack = QStackedWidget()

        self._build_ui()
        self._apply_styles()
        self._apply_language()
        self._populate_tree()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        tree_panel = QFrame()
        tree_panel.setObjectName("dialogPanel")
        tree_panel.setMinimumWidth(560)
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(12, 12, 12, 12)
        tree_layout.setSpacing(8)
        tree_layout.addWidget(self._tree_title)
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self._tree.header().resizeSection(1, 96)
        self._tree.itemSelectionChanged.connect(self._handle_tree_selection_changed)
        tree_layout.addWidget(self._tree)

        analysis_panel = QWidget()
        analysis_layout = QVBoxLayout(analysis_panel)
        analysis_layout.setContentsMargins(0, 0, 0, 0)
        analysis_layout.setSpacing(10)
        analysis_layout.addWidget(self._build_summary_card())
        analysis_layout.addWidget(self._build_mode_switcher())
        self._inspector_stack.addWidget(
            self._build_two_section_card(
                self._call_links_title,
                (self._calls_out_title, self._outgoing_calls),
                (self._called_by_title, self._incoming_calls),
                include_title=False,
            )
        )
        self._inspector_stack.addWidget(self._build_section_card(self._usages_title, self._usages, include_title=False))
        self._inspector_stack.addWidget(
            self._build_section_card(self._agent_notes_title, self._agent_notes, include_title=False)
        )
        analysis_layout.addWidget(self._inspector_stack)
        analysis_layout.addWidget(self._build_section_card(self._source_title, self._preview), stretch=1)

        splitter.addWidget(tree_panel)
        splitter.addWidget(analysis_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([560, 760])
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
            QPushButton#dialogModeButton {
                background: #132030;
                color: #c1cee1;
                border: 1px solid #29405d;
                border-radius: 12px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#dialogModeButton:hover {
                border-color: #4872a4;
                color: #f4f7fd;
            }
            QPushButton#dialogModeButton:checked {
                background: #224468;
                color: #f8fbff;
                border: 1px solid #7bc5ff;
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

    def _apply_language(self) -> None:
        self.setWindowTitle(tr(self._language, "code_blocks.window_title", label=self._node.label))
        self._title.setText(self._node.label)
        self._meta.setText(tr(self._language, "code_blocks.meta", path=self._detail.path, module=self._detail.module))
        self._status.setText(tr(self._language, "code_blocks.status.default"))
        self._tree.setHeaderLabels(
            [
                tr(self._language, "code_blocks.tree_header.block"),
                tr(self._language, "code_blocks.tree_header.lines"),
            ]
        )
        self._kind_chip.setText(tr(self._language, "code_blocks.kind.placeholder"))
        self._fit_chip.setText(tr(self._language, "code_blocks.fit.placeholder"))
        self._lines.setText(tr(self._language, "code_blocks.lines.empty"))
        self._returns.setText(tr(self._language, "code_blocks.returns.empty"))
        self._stats.setText(tr(self._language, "code_blocks.stats.empty"))
        self._preview.setPlaceholderText(tr(self._language, "code_blocks.preview.placeholder"))
        self._tree_title.setText(tr(self._language, "code_blocks.section.file_blocks"))
        self._analysis_title.setText(tr(self._language, "code_blocks.section.block_analysis"))
        self._parameters_title.setText(tr(self._language, "code_blocks.section.parameters"))
        self._call_links_title.setText(tr(self._language, "code_blocks.section.block_call_links"))
        self._calls_out_title.setText(tr(self._language, "code_blocks.section.calls_out"))
        self._called_by_title.setText(tr(self._language, "code_blocks.section.called_by"))
        self._usages_title.setText(tr(self._language, "code_blocks.section.usages"))
        self._agent_notes_title.setText(tr(self._language, "code_blocks.section.agent_notes"))
        self._source_title.setText(tr(self._language, "code_blocks.section.block_source"))
        self._call_links_button.setText(tr(self._language, "code_blocks.section.block_call_links"))
        self._usages_button.setText(tr(self._language, "code_blocks.section.usages"))
        self._agent_notes_button.setText(tr(self._language, "code_blocks.section.agent_notes"))

    def _populate_tree(self) -> None:
        self._tree.clear()
        if not self._detail.code_blocks:
            item = QTreeWidgetItem([tr(self._language, "code_blocks.placeholder.no_extracted"), "-"])
            self._tree.addTopLevelItem(item)
            self._set_list_content(self._parameters, [], tr(self._language, "code_blocks.placeholder.no_parameters"))
            self._set_list_content(self._outgoing_calls, [], tr(self._language, "code_blocks.placeholder.no_block_calls"))
            self._set_list_content(
                self._incoming_calls,
                [],
                tr(self._language, "code_blocks.placeholder.no_block_callers"),
            )
            self._set_list_content(self._usages, [], tr(self._language, "code_blocks.placeholder.no_usages"))
            self._set_list_content(self._agent_notes, [], tr(self._language, "code_blocks.placeholder.no_agent_notes"))
            self._signature.setText(tr(self._language, "code_blocks.signature.value", signature="-"))
            self._lines.setText(tr(self._language, "code_blocks.lines.empty"))
            self._returns.setText(tr(self._language, "code_blocks.returns.empty"))
            self._stats.setText(tr(self._language, "code_blocks.stats.empty"))
            self._preview.setPlainText(tr(self._language, "code_blocks.placeholder.no_blocks_message"))
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
            self._status.setText(tr(self._language, "code_blocks.selection.none"))
            return

        block = self._blocks_by_id[block_id]
        self._status.setText(
            tr(
                self._language,
                "code_blocks.selection.status",
                kind=self._kind_label(block.kind),
                start=block.line,
                end=block.end_line,
            )
        )
        self._kind_chip.setText(self._kind_label(block.kind))
        self._apply_chip_style(self._kind_chip, self._kind_tone(block.kind))
        self._fit_chip.setText(self._task_fit_label(block.agent_task_fit))
        self._apply_chip_style(self._fit_chip, self._task_fit_tone(block.agent_task_fit))
        self._signature.setText(tr(self._language, "code_blocks.signature.value", signature=block.signature or block.name))
        self._lines.setText(tr(self._language, "code_blocks.lines.value", start=block.line, end=block.end_line))
        self._returns.setText(tr(self._language, "code_blocks.returns.value", value=self._return_label(block)))
        outgoing_calls = self._calls_by_source.get(block.id, [])
        incoming_calls = self._calls_by_target.get(block.id, [])
        usages = self._usages_by_target.get(block.id, [])
        child_count = sum(1 for candidate in self._detail.code_blocks if candidate.parent_id == block.id)
        self._stats.setText(
            tr(
                self._language,
                "code_blocks.stats.value",
                depth=block.depth,
                child_count=child_count,
                outgoing=len(outgoing_calls),
                incoming=len(incoming_calls),
                usages=len(usages),
            )
        )
        self._set_list_content(
            self._parameters,
            block.parameters,
            tr(self._language, "code_blocks.placeholder.no_parameters"),
        )
        self._set_list_content(
            self._outgoing_calls,
            [self._call_display(call, direction="out") for call in outgoing_calls],
            tr(self._language, "code_blocks.placeholder.no_block_calls"),
        )
        self._set_list_content(
            self._incoming_calls,
            [self._call_display(call, direction="in") for call in incoming_calls],
            tr(self._language, "code_blocks.placeholder.no_block_callers"),
        )
        self._set_list_content(
            self._usages,
            [self._usage_display(usage) for usage in usages],
            tr(self._language, "code_blocks.placeholder.no_usages"),
        )
        self._set_list_content(
            self._agent_notes,
            block.agent_task_reasons,
            tr(self._language, "code_blocks.placeholder.no_agent_notes"),
        )
        self._preview.setPlainText(self._source_excerpt(block))

    def _source_excerpt(self, block: CodeBlockSummary) -> str:
        start = max(block.line - 1, 0)
        end = min(block.end_line, len(self._source_lines))
        excerpt = self._source_lines[start:end]
        if not excerpt:
            return tr(self._language, "code_blocks.placeholder.no_source_excerpt")
        return "\n".join(excerpt)

    def _load_source_lines(self, file_path: Path) -> list[str]:
        try:
            return file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

    def _kind_label(self, kind: CodeBlockKind) -> str:
        if kind is CodeBlockKind.CLASS:
            return tr(self._language, "code_blocks.kind.class")
        if kind is CodeBlockKind.METHOD:
            return tr(self._language, "code_blocks.kind.method")
        return tr(self._language, "code_blocks.kind.function")

    def _kind_tone(self, kind: CodeBlockKind) -> str:
        if kind is CodeBlockKind.CLASS:
            return "class"
        if kind is CodeBlockKind.METHOD:
            return "method"
        return "function"

    def _task_fit_label(self, fit: AgentTaskSuitability) -> str:
        if fit is AgentTaskSuitability.GOOD:
            return tr(self._language, "code_blocks.fit.good")
        if fit is AgentTaskSuitability.AVOID:
            return tr(self._language, "code_blocks.fit.avoid")
        return tr(self._language, "code_blocks.fit.caution")

    def _task_fit_tone(self, fit: AgentTaskSuitability) -> str:
        if fit is AgentTaskSuitability.GOOD:
            return "good"
        if fit is AgentTaskSuitability.AVOID:
            return "avoid"
        return "caution"

    def _return_label(self, block: CodeBlockSummary) -> str:
        if block.kind is CodeBlockKind.CLASS:
            return tr(self._language, "code_blocks.returns.class_na")
        return block.return_summary or tr(self._language, "code_blocks.returns.not_declared")

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
        scope = tr(
            self._language,
            "code_blocks.call.cross_file" if call.is_cross_file else "code_blocks.call.same_file",
        )
        return tr(
            self._language,
            "code_blocks.call.value",
            label=label,
            owner_path=owner_path,
            scope=scope,
            line=call.line,
            expression=call.expression,
        )

    def _usage_display(self, usage: SymbolUsage) -> str:
        owner_label = tr(self._language, "code_blocks.usage.module_scope")
        if usage.owner_block_id is not None:
            owner_block = self._global_blocks_by_id.get(usage.owner_block_id)
            if owner_block is not None:
                owner_label = owner_block.signature or owner_block.name
            else:
                owner_label = usage.owner_block_id
        source_detail = self._details_by_node_id.get(usage.source_node_id)
        owner_path = source_detail.path if source_detail is not None else "-"
        return tr(
            self._language,
            "code_blocks.usage.value",
            kind=self._usage_kind_label(usage.usage_kind),
            owner_label=owner_label,
            owner_path=owner_path,
            confidence=self._usage_confidence_label(usage.confidence),
            line=usage.line,
            expression=usage.expression,
        )

    def _usage_kind_label(self, kind: UsageKind) -> str:
        return tr(self._language, f"usage_kind.{kind.value}")

    def _usage_confidence_label(self, confidence: UsageConfidence) -> str:
        return tr(self._language, f"usage_confidence.{confidence.value}")

    def _build_summary_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dialogPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._analysis_title)
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
        layout.addWidget(self._parameters_title)
        layout.addWidget(self._parameters)
        return frame

    def _build_mode_switcher(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._call_links_button.clicked.connect(lambda: self._set_inspector_mode(0))
        self._usages_button.clicked.connect(lambda: self._set_inspector_mode(1))
        self._agent_notes_button.clicked.connect(lambda: self._set_inspector_mode(2))
        for button in [self._call_links_button, self._usages_button, self._agent_notes_button]:
            layout.addWidget(button)
        layout.addStretch(1)
        self._set_inspector_mode(0)
        return row

    def _build_section_card(self, title_label: QLabel, widget: QWidget, *, include_title: bool = True) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dialogPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        if include_title:
            layout.addWidget(title_label)
        layout.addWidget(widget)
        return frame

    def _build_two_section_card(
        self,
        title_label: QLabel,
        first: tuple[QLabel, QWidget],
        second: tuple[QLabel, QWidget],
        *,
        include_title: bool = True,
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dialogPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        if include_title:
            layout.addWidget(title_label)
        layout.addWidget(first[0])
        layout.addWidget(first[1])
        layout.addWidget(second[0])
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

    def _create_mode_button(self) -> QPushButton:
        button = QPushButton()
        button.setObjectName("dialogModeButton")
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def _set_inspector_mode(self, index: int) -> None:
        self._inspector_stack.setCurrentIndex(index)
        for current_index, button in enumerate(
            [self._call_links_button, self._usages_button, self._agent_notes_button]
        ):
            button.setChecked(current_index == index)

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
