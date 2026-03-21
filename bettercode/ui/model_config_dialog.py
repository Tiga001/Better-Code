from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from bettercode.i18n import LanguageCode, tr
from bettercode.translation_executor import ModelConfig


class ModelConfigDialog(QDialog):
    def __init__(
        self,
        *,
        language: LanguageCode,
        initial_config: ModelConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._language = language
        self._initial_config = initial_config
        self._title = QLabel()
        self._title.setObjectName("dialogTitle")
        self._subtitle = QLabel()
        self._subtitle.setWordWrap(True)
        self._subtitle.setObjectName("dialogMeta")
        self._api_url_input = QLineEdit(initial_config.api_url)
        self._model_name_input = QLineEdit(initial_config.model_name)
        self._api_token_input = QLineEdit(initial_config.api_token)
        self._api_token_input.setEchoMode(QLineEdit.Password)
        self._timeout_input = QLineEdit(str(initial_config.timeout_seconds))
        self._buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self._handle_accept)
        self._buttons.rejected.connect(self.reject)

        self._build_ui()
        self._apply_style()
        self._apply_language()

    def model_config(self) -> ModelConfig:
        return ModelConfig(
            api_url=self._api_url_input.text().strip(),
            api_token=self._api_token_input.text().strip(),
            model_name=self._model_name_input.text().strip(),
            timeout_seconds=float(self._timeout_input.text().strip()),
        )

    def _build_ui(self) -> None:
        self.resize(680, 260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)

        form_container = QWidget()
        form = QFormLayout(form_container)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow(self._label("model_config.field.api_url"), self._api_url_input)
        form.addRow(self._label("model_config.field.model_name"), self._model_name_input)
        form.addRow(self._label("model_config.field.api_token"), self._api_token_input)
        form.addRow(self._label("model_config.field.timeout"), self._timeout_input)
        layout.addWidget(form_container)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addStretch(1)
        button_layout.addWidget(self._buttons)
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
            QLineEdit {
                background: #0d1521;
                border: 1px solid #29405d;
                border-radius: 10px;
                padding: 8px 10px;
            }
            QLineEdit:focus {
                border-color: #5fb5ff;
            }
            QPushButton {
                min-width: 90px;
            }
            """
        )

    def _apply_language(self) -> None:
        self.setWindowTitle(tr(self._language, "model_config.window_title"))
        self._title.setText(tr(self._language, "model_config.title"))
        self._subtitle.setText(tr(self._language, "model_config.subtitle"))
        self._api_url_input.setPlaceholderText(tr(self._language, "model_config.placeholder.api_url"))
        self._model_name_input.setPlaceholderText(tr(self._language, "model_config.placeholder.model_name"))
        self._api_token_input.setPlaceholderText(tr(self._language, "model_config.placeholder.api_token"))
        self._timeout_input.setPlaceholderText(tr(self._language, "model_config.placeholder.timeout"))
        self._buttons.button(QDialogButtonBox.Save).setText(tr(self._language, "model_config.button.save"))
        self._buttons.button(QDialogButtonBox.Cancel).setText(tr(self._language, "model_config.button.cancel"))

    def _label(self, key: str) -> QLabel:
        label = QLabel(tr(self._language, key))
        label.setObjectName("dialogMeta")
        return label

    def _handle_accept(self) -> None:
        timeout_raw = self._timeout_input.text().strip()
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = -1

        if (
            not self._api_url_input.text().strip()
            or not self._model_name_input.text().strip()
            or not self._api_token_input.text().strip()
            or timeout_seconds <= 0
        ):
            QMessageBox.warning(
                self,
                tr(self._language, "model_config.validation.title"),
                tr(self._language, "model_config.validation.body"),
            )
            return

        self.accept()
