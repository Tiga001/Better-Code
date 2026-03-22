from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from bettercode.batch_optimize_executor import BatchRunReport, summarize_batch_run
from bettercode.i18n import LanguageCode, tr


class BatchRunReportDialog(QDialog):
    def __init__(self, *, language: LanguageCode, report: BatchRunReport, parent=None) -> None:
        super().__init__(parent)
        self._language = language
        self._report = report

        self._title = QLabel()
        self._title.setObjectName("dialogTitle")
        self._summary = QLabel()
        self._summary.setObjectName("dialogMeta")
        self._summary.setWordWrap(True)
        self._items = QListWidget()
        self._items.setObjectName("detailList")
        self._close_button = QPushButton()
        self._close_button.setObjectName("dialogModeButton")
        self._close_button.clicked.connect(self.accept)

        self._build_ui()
        self._apply_style()
        self._apply_language()

    def _build_ui(self) -> None:
        self.resize(920, 680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        header_layout.addWidget(self._title)
        header_layout.addWidget(self._summary)
        layout.addWidget(header)
        layout.addWidget(self._items, stretch=1)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addStretch(1)
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
            QLabel#dialogTitle {
                color: #f8fbff;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#dialogMeta {
                color: #c1cee1;
                font-size: 12px;
            }
            QListWidget#detailList {
                background: #111a28;
                border: 1px solid #29405d;
                border-radius: 12px;
                padding: 6px;
            }
            QListWidget#detailList::item {
                padding: 8px 10px;
                border-radius: 8px;
            }
            QListWidget#detailList::item:selected {
                background: #173152;
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
            """
        )

    def _apply_language(self) -> None:
        self.setWindowTitle(tr(self._language, "batch_run_report.window_title"))
        self._title.setText(tr(self._language, "batch_run_report.title"))
        counts = summarize_batch_run(self._report)
        self._summary.setText(
            tr(
                self._language,
                "batch_run_report.summary",
                status=tr(self._language, f"batch_run.status.{self._report.status.value}"),
                total=len(self._report.items),
                passed=counts.get("passed", 0),
                failed=counts.get("failed", 0),
                blocked=counts.get("blocked", 0),
                output_dir=self._report.output_dir,
            )
        )
        self._items.clear()
        for item in sorted(self._report.items, key=lambda candidate: (candidate.phase_index, candidate.order_index)):
            text = tr(
                self._language,
                "batch_run_report.item",
                phase=item.phase_index,
                index=item.order_index,
                status=tr(self._language, f"batch_run.status.{item.status.value}"),
                label=item.label,
            )
            if item.failure_category:
                text += "\n" + tr(
                    self._language,
                    "batch_run_report.failure",
                    category=tr(self._language, f"optimize_failure.{item.failure_category}"),
                )
            elif item.error:
                text += "\n" + item.error
            self._items.addItem(QListWidgetItem(text))
        self._close_button.setText(tr(self._language, "batch_run_report.button.close"))
