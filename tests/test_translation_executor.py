from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from bettercode.models import TaskMode
from bettercode.parser import ProjectAnalyzer
from bettercode.task_planner import build_task_bundle, build_task_candidates
from bettercode.translation_executor import (
    ModelConfig,
    TranslationStatus,
    build_verification_plan,
    execute_translation,
)


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class TranslationExecutorTests(unittest.TestCase):
    def test_execute_translation_writes_generated_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "tests").mkdir()
            (root / "tests" / "test_smoke.py").write_text("import unittest\n", encoding="utf-8")
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    def run(value: str) -> str:
                        return value.strip().upper()
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
                if item.mode is TaskMode.TRANSLATE
            )
            bundle = build_task_bundle(graph, candidate)

            response_payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "translated",
                                    "summary": "Converted the function to a small C++20 workspace.",
                                    "assumptions": ["Input remains a Python string."],
                                    "risks": ["Whitespace handling should be rechecked."],
                                    "dependency_mapping_notes": ["Only Python stdlib behavior was used."],
                                    "verification_notes": ["Build the pybind11 module before comparison."],
                                    "comparison_cases": [
                                        {
                                            "label": "trim and uppercase",
                                            "python_expression": "run('  hello  ')",
                                            "notes": "Expect HELLO",
                                        }
                                    ],
                                    "generated_files": [
                                        {
                                            "path": "CMakeLists.txt",
                                            "purpose": "cmake project",
                                            "content": "cmake_minimum_required(VERSION 3.20)\nproject(run_translation LANGUAGES CXX)\n",
                                        },
                                        {
                                            "path": "include/run.hpp",
                                            "purpose": "header",
                                            "content": "#pragma once\n#include <string>\nstd::string run(const std::string& value);\n",
                                        },
                                        {
                                            "path": "src/run.cpp",
                                            "purpose": "implementation",
                                            "content": "#include \"run.hpp\"\nstd::string run(const std::string& value) { return value; }\n",
                                        },
                                        {
                                            "path": "src/bindings.cpp",
                                            "purpose": "pybind11 bridge",
                                            "content": "#include <pybind11/pybind11.h>\nPYBIND11_MODULE(run_translation, m) {}\n",
                                        },
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

            with patch(
                "bettercode.translation_executor.urlopen",
                return_value=_FakeHttpResponse(response_payload),
            ):
                result = execute_translation(
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
            self.assertEqual(result.status, TranslationStatus.TRANSLATED)
            self.assertTrue((output_dir / "task_bundle.json").is_file())
            self.assertTrue((output_dir / "translation_request.json").is_file())
            self.assertTrue((output_dir / "translation_response.json").is_file())
            self.assertTrue((output_dir / "translation_result.json").is_file())
            self.assertTrue((output_dir / "verification_plan.json").is_file())
            self.assertEqual((output_dir / "CMakeLists.txt").read_text(encoding="utf-8").splitlines()[0], "cmake_minimum_required(VERSION 3.20)")
            self.assertIn("std::string run", (output_dir / "include" / "run.hpp").read_text(encoding="utf-8"))
            self.assertIn("PYBIND11_MODULE", (output_dir / "src" / "bindings.cpp").read_text(encoding="utf-8"))

            verification_plan = json.loads((output_dir / "verification_plan.json").read_text(encoding="utf-8"))
            self.assertIn("python3 -m unittest discover -s tests", verification_plan["python_test_commands"])
            self.assertEqual(verification_plan["comparison_cases"][0]["label"], "trim and uppercase")

    def test_build_verification_plan_adds_manual_note_when_cases_missing(self) -> None:
        plan = build_verification_plan(
            project_root=Path("/tmp/project"),
            result=type(
                "Result",
                (),
                {
                    "comparison_cases": [],
                    "verification_notes": ["Extra note."],
                },
            )(),
        )

        self.assertIn("python3 -m compileall .", plan.python_test_commands)
        self.assertTrue(any("manual cases" in note for note in plan.notes))


if __name__ == "__main__":
    unittest.main()
