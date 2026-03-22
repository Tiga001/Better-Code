from __future__ import annotations

import difflib
import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bettercode.i18n import LanguageCode, tr
from bettercode.optimize_executor import (
    OptimizedFile,
    OptimizationApplyResult,
    OriginalFileState,
    OptimizationResult,
    OptimizationRollbackResult,
)


class OptimizationReviewDialog(QDialog):
    apply_requested = Signal()
    rollback_requested = Signal()

    def __init__(
        self,
        *,
        language: LanguageCode,
        result: OptimizationResult,
        diff_text: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._language = language
        self._result = result
        self._raw_diff_text = diff_text
        self._applied_result: OptimizationApplyResult | None = None
        self._rollback_result: OptimizationRollbackResult | None = None
        self._original_by_path = {item.path: item for item in result.original_files}
        self._candidate_by_path = {item.path: item for item in result.changed_files}

        self._title = QLabel()
        self._title.setObjectName("dialogTitle")
        self._summary = QLabel()
        self._summary.setObjectName("dialogMeta")
        self._summary.setWordWrap(True)
        self._preview_validation = QLabel()
        self._preview_validation.setObjectName("dialogMeta")
        self._live_validation = QLabel()
        self._live_validation.setObjectName("dialogMeta")
        self._file_label = QLabel()
        self._file_label.setObjectName("dialogMeta")
        self._file_selector = QComboBox()
        self._file_selector.setObjectName("dialogCombo")
        for changed_file in result.changed_files:
            self._file_selector.addItem(changed_file.path, changed_file.path)
        if self._file_selector.count() == 0:
            self._file_selector.addItem("", "")
            self._file_selector.setEnabled(False)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("dialogTabs")
        self._diff_title = QLabel()
        self._diff_title.setObjectName("dialogSectionTitle")
        self._diff = QTextEdit()
        self._diff.setReadOnly(True)
        self._diff.setObjectName("dialogPreview")
        self._diff.setAcceptRichText(True)
        self._diff.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._original_view = QPlainTextEdit()
        self._original_view.setReadOnly(True)
        self._original_view.setObjectName("dialogCodeView")
        self._original_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._optimized_view = QPlainTextEdit()
        self._optimized_view.setReadOnly(True)
        self._optimized_view.setObjectName("dialogCodeView")
        self._optimized_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._apply_button = QPushButton()
        self._apply_button.setObjectName("dialogActionButton")
        self._rollback_button = QPushButton()
        self._rollback_button.setObjectName("dialogModeButton")
        self._close_button = QPushButton()
        self._close_button.setObjectName("dialogModeButton")

        self._apply_button.clicked.connect(self.apply_requested.emit)
        self._rollback_button.clicked.connect(self.rollback_requested.emit)
        self._close_button.clicked.connect(self.accept)
        self._file_selector.currentIndexChanged.connect(self._refresh_preview_pages)

        self._build_ui()
        self._apply_style()
        self._apply_language()
        self._refresh_preview_pages()
        self._sync_buttons()

    def set_applied_result(self, result: OptimizationApplyResult) -> None:
        self._applied_result = result
        self._rollback_result = None
        self._refresh_status_labels()
        self._sync_buttons()

    def set_rollback_result(self, result: OptimizationRollbackResult) -> None:
        self._rollback_result = result
        self._applied_result = None
        self._refresh_status_labels()
        self._sync_buttons()

    def _build_ui(self) -> None:
        self.resize(1080, 760)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("dialogPanel")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 12, 12, 12)
        header_layout.setSpacing(8)
        header_layout.addWidget(self._title)
        header_layout.addWidget(self._summary)
        header_layout.addWidget(self._preview_validation)
        header_layout.addWidget(self._live_validation)
        layout.addWidget(header)

        diff_panel = QFrame()
        diff_panel.setObjectName("dialogPanel")
        diff_layout = QVBoxLayout(diff_panel)
        diff_layout.setContentsMargins(12, 12, 12, 12)
        diff_layout.setSpacing(8)
        diff_layout.addWidget(self._diff_title)
        selector_row = QWidget()
        selector_layout = QHBoxLayout(selector_row)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(8)
        selector_layout.addWidget(self._file_label)
        selector_layout.addWidget(self._file_selector, stretch=1)
        diff_layout.addWidget(selector_row)

        self._tabs.addTab(self._diff, "")
        self._tabs.addTab(self._original_view, "")
        self._tabs.addTab(self._optimized_view, "")
        diff_layout.addWidget(self._tabs, stretch=1)
        layout.addWidget(diff_panel, stretch=1)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        button_layout.addStretch(1)
        button_layout.addWidget(self._apply_button)
        button_layout.addWidget(self._rollback_button)
        button_layout.addWidget(self._close_button)
        layout.addWidget(button_row)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog, QWidget {
                background: #101722;
                color: #e9eef7;
                font-family: Helvetica Neue, Arial, sans-serif;
                font-size: 13px;
            }
            QFrame#dialogPanel {
                background: #111a28;
                border: 1px solid #29405d;
                border-radius: 16px;
            }
            QLabel#dialogTitle {
                color: #f8fbff;
                font-size: 20px;
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
            QTextEdit#dialogPreview {
                background: #0d1521;
                border: 1px solid #29405d;
                border-radius: 12px;
            }
            QPlainTextEdit#dialogCodeView {
                background: #0d1521;
                color: #e9eef7;
                border: 1px solid #29405d;
                border-radius: 12px;
                font-family: Menlo, Monaco, Consolas, "Liberation Mono", monospace;
                font-size: 12px;
            }
            QComboBox#dialogCombo {
                background: #0d1521;
                color: #e9eef7;
                border: 1px solid #29405d;
                border-radius: 10px;
                padding: 6px 10px;
                min-width: 280px;
            }
            QTabWidget#dialogTabs::pane {
                border: none;
            }
            QTabWidget#dialogTabs QTabBar::tab {
                background: #132030;
                color: #c1cee1;
                border: 1px solid #29405d;
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                padding: 8px 14px;
                margin-right: 6px;
            }
            QTabWidget#dialogTabs QTabBar::tab:selected {
                background: #1b2a3d;
                color: #f8fbff;
            }
            QPushButton#dialogActionButton {
                background: #ff9640;
                color: #08111e;
                border: none;
                border-radius: 12px;
                padding: 9px 14px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#dialogActionButton:disabled {
                background: #283648;
                color: #8ea1ba;
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
            QPushButton#dialogModeButton:disabled {
                color: #728299;
                border-color: #233445;
            }
            """
        )

    def _apply_language(self) -> None:
        self.setWindowTitle(tr(self._language, "optimize_review.window_title"))
        self._title.setText(tr(self._language, "optimize_review.title"))
        self._diff_title.setText(tr(self._language, "optimize_review.diff_title"))
        self._file_label.setText(tr(self._language, "optimize_review.file_label"))
        self._tabs.setTabText(0, tr(self._language, "optimize_review.tab.diff"))
        self._tabs.setTabText(1, tr(self._language, "optimize_review.tab.original"))
        self._tabs.setTabText(2, tr(self._language, "optimize_review.tab.optimized"))
        self._apply_button.setText(tr(self._language, "optimize_review.button.apply"))
        self._rollback_button.setText(tr(self._language, "optimize_review.button.rollback"))
        self._close_button.setText(tr(self._language, "optimize_review.button.close"))
        self._refresh_status_labels()
        self._refresh_preview_pages()

    def _refresh_status_labels(self) -> None:
        summary_text = tr(
            self._language,
            "optimize_review.summary",
            status=self._result.status.value,
            output_dir=self._result.output_dir,
            summary=self._result.summary,
        )
        failure_category = getattr(self._result, "failure_category", None)
        if failure_category is not None:
            summary_text += "\n" + tr(
                self._language,
                "optimize_review.failure_category",
                category=tr(self._language, f"optimize_failure.{failure_category.value}"),
            )
        self._summary.setText(summary_text)
        self._preview_validation.setText(
            tr(
                self._language,
                "optimize_review.preview_validation",
                status=self._result.validation_report.status.value,
            )
        )
        if self._rollback_result is not None:
            self._live_validation.setText(
                tr(
                    self._language,
                    "optimize_review.rollback_validation",
                    status=self._rollback_result.validation_report.status.value,
                )
            )
            return
        if self._applied_result is not None:
            self._live_validation.setText(
                tr(
                    self._language,
                    "optimize_review.live_validation",
                    status=self._applied_result.validation_report.status.value,
                )
            )
            return
        self._live_validation.setText(tr(self._language, "optimize_review.live_validation.pending"))

    def _sync_buttons(self) -> None:
        has_changed_files = bool(self._result.changed_files)
        self._apply_button.setEnabled(has_changed_files and self._applied_result is None)
        self._rollback_button.setEnabled(has_changed_files and self._applied_result is not None)

    def _refresh_preview_pages(self) -> None:
        path = self._current_file_path()
        if path is None:
            self._diff.setHtml(self._build_diff_html(self._raw_diff_text))
            placeholder = tr(self._language, "optimize_review.placeholder.no_changed_files")
            self._original_view.setPlainText(placeholder)
            self._optimized_view.setPlainText(placeholder)
            return

        original_file = self._original_by_path.get(path)
        optimized_file = self._candidate_by_path.get(path)
        original_content = original_file.content if original_file is not None else ""
        optimized_content = optimized_file.content if optimized_file is not None else ""

        self._diff.setHtml(self._build_diff_html(self._build_file_diff_text(path, original_content, optimized_content)))
        self._original_view.setPlainText(self._build_original_text(path, original_file))
        self._optimized_view.setPlainText(self._build_optimized_text(path, optimized_file))

    def _current_file_path(self) -> str | None:
        if self._file_selector.count() == 0:
            return None
        path = self._file_selector.currentData()
        if not isinstance(path, str) or not path:
            return None
        return path

    def _build_file_diff_text(self, path: str, original_content: str, optimized_content: str) -> str:
        diff_lines = list(
            difflib.unified_diff(
                original_content.splitlines(),
                optimized_content.splitlines(),
                fromfile=path,
                tofile=path,
                lineterm="",
            )
        )
        return "\n".join(diff_lines)

    def _build_original_text(self, path: str, original_file: OriginalFileState | None) -> str:
        if original_file is None or not original_file.existed_before:
            return tr(self._language, "optimize_review.placeholder.no_original", path=path)
        return original_file.content

    def _build_optimized_text(self, path: str, optimized_file: OptimizedFile | None) -> str:
        if optimized_file is None:
            return tr(self._language, "optimize_review.placeholder.no_optimized", path=path)
        return optimized_file.content

    def _build_diff_html(self, diff_text: str) -> str:
        if not diff_text.strip():
            empty = html.escape(tr(self._language, "optimize_review.placeholder.no_changed_files"))
            return (
                "<html><body style='background:#0d1521; color:#e9eef7; "
                "font-family:Menlo, Monaco, Consolas, monospace; font-size:12px;'>"
                f"<pre>{empty}</pre></body></html>"
            )

        lines: list[str] = []
        for raw_line in diff_text.splitlines():
            style = "color:#dbe6f3;"
            if raw_line.startswith(("---", "+++")):
                style = "background-color:#1b2736; color:#a9c7ff;"
            elif raw_line.startswith("@@"):
                style = "background-color:#2b2240; color:#d7c0ff;"
            elif raw_line.startswith("+"):
                style = "background-color:#17361f; color:#c8f5d4;"
            elif raw_line.startswith("-"):
                style = "background-color:#3b1d22; color:#ffccd3;"
            escaped = html.escape(raw_line) or "&nbsp;"
            lines.append(
                "<div style=\"white-space:pre; padding:0 10px; "
                "font-family:Menlo, Monaco, Consolas, monospace; font-size:12px; "
                f"{style}\">{escaped}</div>"
            )
        return "<html><body style='margin:0; background:#0d1521;'>" + "".join(lines) + "</body></html>"
