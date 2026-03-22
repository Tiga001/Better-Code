from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from bettercode.optimize_executor import (
    OptimizationFailureCategory,
    OptimizedFile,
    OptimizationResult,
    OptimizationStatus,
    OptimizationValidationReport,
    OriginalFileState,
    ValidationCommandResult,
    ValidationStatus,
)
from bettercode.ui.optimization_review_dialog import OptimizationReviewDialog


def _validation_report(workspace_dir: str) -> OptimizationValidationReport:
    return OptimizationValidationReport(
        status=ValidationStatus.PASSED,
        workspace_dir=workspace_dir,
        compile_command=ValidationCommandResult(
            command="python3 -m compileall .",
            returncode=0,
            stdout="",
            stderr="",
            ok=True,
        ),
        test_command=None,
        notes=[],
    )


class OptimizationReviewDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_shows_tabs_and_switches_file_views(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = OptimizationResult(
                status=OptimizationStatus.OPTIMIZED,
                summary="done",
                assumptions=[],
                risks=[],
                validation_notes=[],
                suggested_tests=[],
                changed_files=[
                    OptimizedFile(path="service.py", content="def run():\n    return 'ok'\n", purpose="inline"),
                    OptimizedFile(path="worker.py", content="VALUE = 2\n", purpose="simplify"),
                ],
                original_files=[
                    OriginalFileState(path="service.py", existed_before=True, content="def run():\n    value = 'ok'\n    return value\n"),
                    OriginalFileState(path="worker.py", existed_before=True, content="VALUE = 1\n"),
                ],
                raw_model_content="{}",
                output_dir=str(root / "generated" / "optimizations" / "service"),
                diff_path=str(root / "generated" / "optimizations" / "service" / "optimization.patch"),
                validation_report=_validation_report(str(root / "generated" / "optimizations" / "service" / "validation_workspace")),
            )
            dialog = OptimizationReviewDialog(language="zh", result=result, diff_text="--- full\n+++ full\n")
            self.addCleanup(dialog.close)

            self.assertEqual(dialog._tabs.tabText(0), "Diff")
            self.assertEqual(dialog._tabs.tabText(1), "原始版本")
            self.assertEqual(dialog._tabs.tabText(2), "优化结果")
            self.assertEqual(dialog._file_label.text(), "变更文件")
            self.assertEqual(dialog._original_view.toPlainText(), "def run():\n    value = 'ok'\n    return value\n")
            self.assertEqual(dialog._optimized_view.toPlainText(), "def run():\n    return 'ok'\n")

            dialog._file_selector.setCurrentIndex(1)

            self.assertEqual(dialog._original_view.toPlainText(), "VALUE = 1\n")
            self.assertEqual(dialog._optimized_view.toPlainText(), "VALUE = 2\n")

    def test_diff_html_contains_add_remove_highlight_styles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = OptimizationResult(
                status=OptimizationStatus.OPTIMIZED,
                summary="done",
                assumptions=[],
                risks=[],
                validation_notes=[],
                suggested_tests=[],
                changed_files=[
                    OptimizedFile(path="service.py", content="def run():\n    return value.strip()\n", purpose="inline"),
                ],
                original_files=[
                    OriginalFileState(path="service.py", existed_before=True, content="def run():\n    text = value.strip()\n    return text\n"),
                ],
                raw_model_content="{}",
                output_dir=str(root / "generated" / "optimizations" / "service"),
                diff_path=str(root / "generated" / "optimizations" / "service" / "optimization.patch"),
                validation_report=_validation_report(str(root / "generated" / "optimizations" / "service" / "validation_workspace")),
            )
            dialog = OptimizationReviewDialog(language="en", result=result, diff_text="")
            self.addCleanup(dialog.close)

            html = dialog._build_diff_html(
                dialog._build_file_diff_text(
                    "service.py",
                    "def run():\n    text = value.strip()\n    return text\n",
                    "def run():\n    return value.strip()\n",
                )
            )
            self.assertIn("background-color:#17361f", html)
            self.assertIn("background-color:#3b1d22", html)
            self.assertIn("service.py", html)

    def test_dialog_shows_failure_category_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = OptimizationResult(
                status=OptimizationStatus.BLOCKED,
                summary="invalid json",
                assumptions=[],
                risks=[],
                validation_notes=[],
                suggested_tests=[],
                changed_files=[],
                original_files=[],
                raw_model_content="{}",
                output_dir=str(root / "generated" / "optimizations" / "service"),
                diff_path=str(root / "generated" / "optimizations" / "service" / "optimization.patch"),
                validation_report=_validation_report(str(root / "generated" / "optimizations" / "service" / "validation_workspace")),
                failure_category=OptimizationFailureCategory.BAD_MODEL_OUTPUT,
            )
            dialog = OptimizationReviewDialog(language="zh", result=result, diff_text="")
            self.addCleanup(dialog.close)

            self.assertIn("失败分类：模型输出异常", dialog._summary.text())


if __name__ == "__main__":
    unittest.main()
