from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from bettercode.models import AgentTaskSuitability, DependencyMappingStatus, TaskMode
from bettercode.parser import ProjectAnalyzer
from bettercode.task_planner import build_task_bundle, build_task_candidates, task_bundle_to_dict


class TaskPlannerTests(unittest.TestCase):
    def test_builds_optimize_and_translate_candidates_for_top_level_function(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    def normalize(value: str) -> str:
                        return value.strip()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    import requests
                    from helper import normalize

                    def run(value: str) -> str:
                        return normalize(value)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:service.py"]
        run_block = next(block for block in detail.code_blocks if block.name == "run")
        candidates = {candidate.mode: candidate for candidate in build_task_candidates(graph)[run_block.id]}

        self.assertEqual(candidates[TaskMode.OPTIMIZE].suitability, AgentTaskSuitability.GOOD)
        self.assertEqual(candidates[TaskMode.TRANSLATE].target_language, "cpp")
        self.assertEqual(candidates[TaskMode.TRANSLATE].suitability, AgentTaskSuitability.CAUTION)
        self.assertEqual(
            candidates[TaskMode.TRANSLATE].dependency_mapping_status,
            DependencyMappingStatus.CANDIDATE,
        )
        self.assertIn("file:helper.py", candidates[TaskMode.TRANSLATE].related_node_ids)

        bundle = build_task_bundle(graph, candidates[TaskMode.TRANSLATE])
        self.assertIn("service.py", bundle.related_files)
        self.assertIn("helper.py", bundle.related_files)
        self.assertTrue(any("run(value" in snippet for snippet in bundle.source_snippets))
        self.assertTrue(any("Compile the generated C++20 target." in check for check in bundle.acceptance_checks))
        serialized = task_bundle_to_dict(bundle)
        self.assertEqual(serialized["task"]["mode"], "translate")
        self.assertEqual(serialized["task"]["target_language"], "cpp")
        self.assertEqual(serialized["task"]["dependency_mapping_status"], "candidate")
        json.dumps(serialized, ensure_ascii=False)

    def test_translation_candidate_avoids_methods_in_function_mvp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    class Worker:
                        def step(self, value: str) -> str:
                            return value.strip()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:service.py"]
        step_block = next(block for block in detail.code_blocks if block.name == "step")
        candidates = {candidate.mode: candidate for candidate in build_task_candidates(graph)[step_block.id]}

        self.assertEqual(candidates[TaskMode.TRANSLATE].suitability, AgentTaskSuitability.AVOID)
        self.assertTrue(
            any("top-level functions" in reason for reason in candidates[TaskMode.TRANSLATE].reasons)
        )


if __name__ == "__main__":
    unittest.main()
