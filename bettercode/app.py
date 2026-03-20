from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from bettercode.ui.main_window import MainWindow


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("BetterCode")
    application.setOrganizationName("BetterCode")
    window = MainWindow()
    window.show()
    return application.exec()

