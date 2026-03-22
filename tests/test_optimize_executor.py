from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from bettercode.models import TaskMode
from bettercode.optimize_executor import (
    ModelConfig,
    OptimizationFailureCategory,
    OptimizationStatus,
    ValidationStatus,
    apply_optimization_result,
    execute_optimization,
    rollback_optimization_result,
)
from bettercode.parser import ProjectAnalyzer
from bettercode.task_planner import build_task_bundle, build_task_candidates


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class OptimizeExecutorTests(unittest.TestCase):
    def test_execute_optimization_writes_candidate_files_and_validation_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "tests").mkdir()
            (root / "tests" / "test_service.py").write_text(
                textwrap.dedent(
                    """
                    import unittest

                    from service import run


                    class ServiceTests(unittest.TestCase):
                        def test_run_trims_text(self) -> None:
                            self.assertEqual(run("  ok  "), "ok")


                    if __name__ == "__main__":
                        unittest.main()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    def run(value: str) -> str:
                        text = value.strip()
                        return text
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)
            detail = graph.file_details["file:service.py"]
            run_block = next(block for block in detail.code_blocks if block.name == "run")
            candidate = next(
                item
                for item in build_task_candidates(graph)[run_block.id]
                if item.mode is TaskMode.OPTIMIZE
            )
            bundle = build_task_bundle(graph, candidate)

            response_payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "optimized",
                                    "summary": "Simplified the function while preserving behavior.",
                                    "assumptions": ["Input remains a string."],
                                    "risks": ["None for the covered test case."],
                                    "validation_notes": ["Compile and unit tests should still pass."],
                                    "suggested_tests": ["python3 -m unittest discover -s tests"],
                                    "changed_files": [
                                        {
                                            "path": "service.py",
                                            "purpose": "Reduce temporary variables.",
                                            "content": textwrap.dedent(
                                                """
                                                def run(value: str) -> str:
                                                    return value.strip()
                                                """
                                            ).strip()
                                            + "\n",
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

            with patch(
                "bettercode.optimize_executor.urlopen",
                return_value=_FakeHttpResponse(response_payload),
            ):
                result = execute_optimization(
                    bundle,
                    project_root=root,
                    config=ModelConfig(
                        api_url="https://example.invalid/v1/chat/completions",
                        api_token="token",
                        model_name="model",
                        timeout_seconds=15.0,
                    ),
                )

            output_dir = Path(result.output_dir)
            self.assertEqual(result.status, OptimizationStatus.OPTIMIZED)
            self.assertEqual(result.validation_report.status, ValidationStatus.PASSED)
            self.assertTrue((output_dir / "task_bundle.json").is_file())
            self.assertTrue((output_dir / "optimization_request.json").is_file())
            self.assertTrue((output_dir / "optimization_response.json").is_file())
            self.assertTrue((output_dir / "optimization_result.json").is_file())
            self.assertTrue((output_dir / "validation_report.json").is_file())
            self.assertTrue((output_dir / "optimization.patch").is_file())
            self.assertEqual(
                (output_dir / "candidate_files" / "service.py").read_text(encoding="utf-8"),
                "def run(value: str) -> str:\n    return value.strip()\n",
            )
            patch_text = (output_dir / "optimization.patch").read_text(encoding="utf-8")
            self.assertIn("--- service.py", patch_text)
            self.assertIn("+++ service.py", patch_text)
            self.assertIn("+    return value.strip()", patch_text)

            validation_report = json.loads((output_dir / "validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(validation_report["status"], "passed")
            self.assertEqual(validation_report["compile_command"]["returncode"], 0)
            self.assertEqual(validation_report["test_command"]["returncode"], 0)

            request_payload = json.loads((output_dir / "optimization_request.json").read_text(encoding="utf-8"))
            self.assertEqual(request_payload["user_payload"]["editable_files"][0]["path"], "service.py")
            self.assertEqual(request_payload["user_payload"]["target_blocks"][0]["id"], run_block.id)
            self.assertIn(
                "def run(value: str) -> str:\n    text = value.strip()\n    return text\n",
                request_payload["user_payload"]["editable_files"][0]["content"],
            )
            self.assertTrue((output_dir / "raw_model_content.txt").is_file())

    def test_execute_optimization_supports_structured_replace_block_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "service.py").write_text(
                "def run(value: str) -> str:\n"
                "    text = value.strip()\n"
                "    return text\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)
            detail = graph.file_details["file:service.py"]
            run_block = next(block for block in detail.code_blocks if block.name == "run")
            candidate = next(
                item
                for item in build_task_candidates(graph)[run_block.id]
                if item.mode is TaskMode.OPTIMIZE
            )
            bundle = build_task_bundle(graph, candidate)

            response_payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "optimized",
                                    "summary": "Inline the temporary variable using structured edits.",
                                    "assumptions": [],
                                    "risks": [],
                                    "validation_notes": [],
                                    "suggested_tests": [],
                                    "edits": [
                                        {
                                            "path": "service.py",
                                            "kind": "replace_block",
                                            "target_block_id": run_block.id,
                                            "start_line": run_block.line,
                                            "end_line": run_block.end_line,
                                            "old_text": "def run(value: str) -> str:\n    text = value.strip()\n    return text",
                                            "new_text": "def run(value: str) -> str:\n    return value.strip()",
                                            "purpose": "Inline the temporary variable.",
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

            with patch(
                "bettercode.optimize_executor.urlopen",
                return_value=_FakeHttpResponse(response_payload),
            ):
                result = execute_optimization(
                    bundle,
                    project_root=root,
                    config=ModelConfig(
                        api_url="https://example.invalid/v1/chat/completions",
                        api_token="token",
                        model_name="model",
                        timeout_seconds=15.0,
                    ),
                )

            self.assertEqual(result.status, OptimizationStatus.OPTIMIZED)
            self.assertEqual(len(result.edits), 1)
            self.assertEqual(result.edits[0].target_block_id, run_block.id)
            self.assertEqual(result.changed_files[0].path, "service.py")
            self.assertEqual(
                result.changed_files[0].content,
                "def run(value: str) -> str:\n    return value.strip()\n",
            )

    def test_execute_optimization_normalizes_method_indent_for_structured_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "widget_module.py").write_text(
                textwrap.dedent(
                    """
                    class Widget:
                        def render(self) -> str:
                            value = "ok"
                            return value
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)
            detail = graph.file_details["file:widget_module.py"]
            render_summary = next(block for block in detail.code_blocks if block.name == "render")
            candidate = next(
                item
                for item in build_task_candidates(graph)[render_summary.id]
                if item.mode is TaskMode.OPTIMIZE
            )
            package = build_task_bundle(graph, candidate)
            render_block = package.target_blocks[0]

            response_payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "optimized",
                                    "summary": "Inline the temporary variable inside the method.",
                                    "assumptions": [],
                                    "risks": [],
                                    "validation_notes": [],
                                    "suggested_tests": [],
                                    "edits": [
                                        {
                                            "path": "widget_module.py",
                                            "kind": "replace_block",
                                            "target_block_id": render_block.id,
                                            "start_line": render_block.start_line,
                                            "end_line": render_block.end_line,
                                            "old_text": "def render(self) -> str:\n        value = \"ok\"\n        return value",
                                            "new_text": "def render(self) -> str:\n        return \"ok\"",
                                            "purpose": "Inline the temporary variable inside the method.",
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

            with patch(
                "bettercode.optimize_executor.urlopen",
                return_value=_FakeHttpResponse(response_payload),
            ):
                result = execute_optimization(
                    package,
                    project_root=root,
                    config=ModelConfig(
                        api_url="https://example.invalid/v1/chat/completions",
                        api_token="token",
                        model_name="model",
                        timeout_seconds=15.0,
                    ),
                )

            self.assertEqual(result.status, OptimizationStatus.OPTIMIZED)
            self.assertEqual(
                result.changed_files[0].content,
                "class Widget:\n"
                "    def render(self) -> str:\n"
                "        return \"ok\"\n",
            )

    def test_apply_and_rollback_restore_live_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "tests").mkdir()
            original_source = (
                "def run(value: str) -> str:\n"
                "    text = value.strip()\n"
                "    return text\n"
            )
            optimized_source = "def run(value: str) -> str:\n    return value.strip()\n"
            (root / "tests" / "test_service.py").write_text(
                textwrap.dedent(
                    """
                    import unittest

                    from service import run


                    class ServiceTests(unittest.TestCase):
                        def test_run_trims_text(self) -> None:
                            self.assertEqual(run("  ok  "), "ok")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "service.py").write_text(original_source, encoding="utf-8")

            graph = ProjectAnalyzer().analyze(root)
            detail = graph.file_details["file:service.py"]
            run_block = next(block for block in detail.code_blocks if block.name == "run")
            candidate = next(
                item
                for item in build_task_candidates(graph)[run_block.id]
                if item.mode is TaskMode.OPTIMIZE
            )
            bundle = build_task_bundle(graph, candidate)

            response_payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "optimized",
                                    "summary": "Simplified the function while preserving behavior.",
                                    "assumptions": [],
                                    "risks": [],
                                    "validation_notes": [],
                                    "suggested_tests": ["python3 -m unittest discover -s tests"],
                                    "changed_files": [
                                        {
                                            "path": "service.py",
                                            "purpose": "Inline the temporary variable.",
                                            "content": optimized_source,
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

            with patch(
                "bettercode.optimize_executor.urlopen",
                return_value=_FakeHttpResponse(response_payload),
            ):
                result = execute_optimization(
                    bundle,
                    project_root=root,
                    config=ModelConfig(
                        api_url="https://example.invalid/v1/chat/completions",
                        api_token="token",
                        model_name="model",
                        timeout_seconds=15.0,
                    ),
                )

            apply_result = apply_optimization_result(result, project_root=root)
            self.assertEqual(apply_result.validation_report.status, ValidationStatus.PASSED)
            self.assertEqual((root / "service.py").read_text(encoding="utf-8"), optimized_source)
            self.assertTrue((Path(result.output_dir) / "apply_validation_report.json").is_file())

            rollback_result = rollback_optimization_result(result, project_root=root)
            self.assertEqual(rollback_result.validation_report.status, ValidationStatus.PASSED)
            self.assertEqual((root / "service.py").read_text(encoding="utf-8"), original_source)
            self.assertTrue((Path(result.output_dir) / "rollback_validation_report.json").is_file())

    def test_execute_optimization_blocks_destructive_top_level_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "widget_module.py").write_text(
                textwrap.dedent(
                    """
                    class Preserved:
                        pass

                    class Target:
                        def render(self) -> str:
                            return "ok"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)
            detail = graph.file_details["file:widget_module.py"]
            target_block = next(block for block in detail.code_blocks if block.name == "Target")
            candidate = next(
                item
                for item in build_task_candidates(graph)[target_block.id]
                if item.mode is TaskMode.OPTIMIZE
            )
            bundle = build_task_bundle(graph, candidate)

            response_payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "optimized",
                                    "summary": "Simplified Target.",
                                    "assumptions": [],
                                    "risks": [],
                                    "validation_notes": [],
                                    "suggested_tests": [],
                                    "changed_files": [
                                        {
                                            "path": "widget_module.py",
                                            "purpose": "Rewrite target class.",
                                            "content": textwrap.dedent(
                                                """
                                                class Target:
                                                    def render(self) -> str:
                                                        return "ok"
                                                """
                                            ).strip()
                                            + "\n",
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

            with patch(
                "bettercode.optimize_executor.urlopen",
                return_value=_FakeHttpResponse(response_payload),
            ):
                result = execute_optimization(
                    bundle,
                    project_root=root,
                    config=ModelConfig(
                        api_url="https://example.invalid/v1/chat/completions",
                        api_token="token",
                        model_name="model",
                        timeout_seconds=15.0,
                    ),
                )

            self.assertEqual(result.status, OptimizationStatus.BLOCKED)
            self.assertEqual(result.failure_category, OptimizationFailureCategory.SAFETY_BLOCKED)
            self.assertEqual(result.changed_files, [])
            self.assertTrue(any("Preserved" in risk for risk in result.risks))

    def test_execute_optimization_retries_once_after_bad_model_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "service.py").write_text(
                "def run(value: str) -> str:\n    return value.strip()\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)
            detail = graph.file_details["file:service.py"]
            run_block = next(block for block in detail.code_blocks if block.name == "run")
            candidate = next(
                item
                for item in build_task_candidates(graph)[run_block.id]
                if item.mode is TaskMode.OPTIMIZE
            )
            bundle = build_task_bundle(graph, candidate)

            bad_response = {"choices": [{"message": {"content": "{\"status\": "}}]}
            good_response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "optimized",
                                    "summary": "No-op normalization.",
                                    "assumptions": [],
                                    "risks": [],
                                    "validation_notes": [],
                                    "suggested_tests": [],
                                    "changed_files": [
                                        {
                                            "path": "service.py",
                                            "purpose": "Keep behavior the same.",
                                            "content": "def run(value: str) -> str:\n    return value.strip()\n",
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

            with patch(
                "bettercode.optimize_executor.urlopen",
                side_effect=[_FakeHttpResponse(bad_response), _FakeHttpResponse(good_response)],
            ):
                result = execute_optimization(
                    bundle,
                    project_root=root,
                    config=ModelConfig(
                        api_url="https://example.invalid/v1/chat/completions",
                        api_token="token",
                        model_name="model",
                        timeout_seconds=15.0,
                    ),
                )

            output_dir = Path(result.output_dir)
            self.assertEqual(result.status, OptimizationStatus.OPTIMIZED)
            self.assertIsNone(result.failure_category)
            self.assertTrue((output_dir / "optimization_response_attempt_1.json").is_file())
            self.assertTrue((output_dir / "optimization_response_attempt_2.json").is_file())
            self.assertTrue((output_dir / "raw_model_content_attempt_1.txt").is_file())
            self.assertTrue((output_dir / "raw_model_content_attempt_2.txt").is_file())
            self.assertTrue((output_dir / "raw_model_content.txt").is_file())
            self.assertTrue(any("retry attempt succeeded" in note for note in result.validation_notes))

    def test_execute_optimization_returns_bad_model_output_after_two_invalid_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "service.py").write_text(
                "def run(value: str) -> str:\n    return value.strip()\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)
            detail = graph.file_details["file:service.py"]
            run_block = next(block for block in detail.code_blocks if block.name == "run")
            candidate = next(
                item
                for item in build_task_candidates(graph)[run_block.id]
                if item.mode is TaskMode.OPTIMIZE
            )
            bundle = build_task_bundle(graph, candidate)

            bad_response_1 = {"choices": [{"message": {"content": "{\"status\": "}}]}
            bad_response_2 = {"choices": [{"message": {"content": "not-json-at-all"}}]}

            with patch(
                "bettercode.optimize_executor.urlopen",
                side_effect=[_FakeHttpResponse(bad_response_1), _FakeHttpResponse(bad_response_2)],
            ):
                result = execute_optimization(
                    bundle,
                    project_root=root,
                    config=ModelConfig(
                        api_url="https://example.invalid/v1/chat/completions",
                        api_token="token",
                        model_name="model",
                        timeout_seconds=15.0,
                    ),
                )

            output_dir = Path(result.output_dir)
            self.assertEqual(result.status, OptimizationStatus.BLOCKED)
            self.assertEqual(result.failure_category, OptimizationFailureCategory.BAD_MODEL_OUTPUT)
            self.assertEqual(result.validation_report.status, ValidationStatus.BLOCKED)
            self.assertTrue((output_dir / "optimization_result.json").is_file())
            self.assertTrue((output_dir / "raw_model_content.txt").is_file())
            self.assertEqual((output_dir / "optimization.patch").read_text(encoding="utf-8"), "")

    def test_execute_optimization_marks_validation_failed_when_candidate_breaks_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "service.py").write_text(
                "def run(value: str) -> str:\n    return value.strip()\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)
            detail = graph.file_details["file:service.py"]
            run_block = next(block for block in detail.code_blocks if block.name == "run")
            candidate = next(
                item
                for item in build_task_candidates(graph)[run_block.id]
                if item.mode is TaskMode.OPTIMIZE
            )
            bundle = build_task_bundle(graph, candidate)

            response_payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "optimized",
                                    "summary": "Broke syntax on purpose.",
                                    "assumptions": [],
                                    "risks": [],
                                    "validation_notes": [],
                                    "suggested_tests": [],
                                    "changed_files": [
                                        {
                                            "path": "service.py",
                                            "purpose": "Introduce a syntax error.",
                                            "content": "def run(value: str) -> str\n    return value.strip()\n",
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

            with patch(
                "bettercode.optimize_executor.urlopen",
                return_value=_FakeHttpResponse(response_payload),
            ):
                result = execute_optimization(
                    bundle,
                    project_root=root,
                    config=ModelConfig(
                        api_url="https://example.invalid/v1/chat/completions",
                        api_token="token",
                        model_name="model",
                        timeout_seconds=15.0,
                    ),
                )

            self.assertEqual(result.failure_category, OptimizationFailureCategory.VALIDATION_FAILED)
            self.assertEqual(result.validation_report.status, ValidationStatus.BLOCKED)
            self.assertEqual(result.status, OptimizationStatus.BLOCKED)


if __name__ == "__main__":
    unittest.main()
